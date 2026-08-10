# Copyright (c) 2024, Erpera and contributors
# For license information, please see license.txt

"""Daily Production Report (SO1-I132).

Raj Tiwari asked for a daily production view carrying Item, Batch, Machine No.,
Employee Name, Finished Quantity and Scrap Quantity. This report already
existed and already named four of those six, so it is enhanced rather than
replaced -- a second Report cannot be called "Daily Production Report" anyway,
since report_name is the primary key.

What was wrong with it
----------------------
* Machine No. and Employee Name did not exist.
* Qty. Rejected, Rej %, Final Product Batch no and Lot No were hard-coded
  to ``0``.
* Opration Name returned ``Work Order.transfer_material_against``, a Select of
  "Work Order" / "Job Card", into a column linked to Operation.
* It had no filters and called ``frappe.get_doc`` on every Stock Entry that
  had a work order -- 29,404 of them -- emitting a row per line item,
  raw materials and scrap included, each labelled Product Name.
* It could not run at all: the Report record pointed at a module named "Sona"
  that is not in ``seplt/modules.txt``, so it raised ``KeyError: 'sona'``.
  Re-syncing this file's JSON on migrate puts it back on "Seplt".

Why the Job Card is the spine
-----------------------------
Machine No. and Employee Name live only on the Job Card. Measured on the SEPL
data (selp.erpera.io, 2026-08-10):

* ``Stock Entry.job_card``                  -> 0 of 14,282 Manufacture entries
* ``Stock Entry.custom_job_card_reference`` -> 0 of 14,282 Manufacture entries
* ``Stock Entry Detail.custom_job_card_id`` -> 0 of 84,818 rows
* ``Work Order Operation.custom_employee``  -> 0 of 8,765 rows
* ``Job Card.workstation``                  -> 13,831 of 13,831 submitted cards
* ``Job Card Time Log.employee``            -> 10,769 of 13,831 submitted cards

So there is no foreign key from a Manufacture Stock Entry to its Job Card.
Matching from the Stock Entry side on (work order, posting date) resolves to a
single Job Card for only 10,895 of 14,282 entries (76%), which would make
Machine No. a guess on one row in four. Anchoring on the Job Card makes those
two columns exact and moves the ambiguity onto the batch columns instead, where
the same style of lookup resolves uniquely for 12,310 of 13,831 cards (89%).

Batch numbers are the one thing a Job Card does not carry -- ``Job Card.batch_no``
is empty on all 13,831 submitted cards -- so they are read from the Manufacture
Stock Entries of the same Work Order on the same day.

Field choices
-------------
* Finished Quantity is ``total_completed_qty``, not ``custom_production_qty``.
  It is the figure that reaches stock: it equals the finished-item quantity on
  the matching Manufacture Stock Entry wherever that entry is unambiguous.
* Scrap Quantity is ``process_loss_qty``, not the ``scrap_items`` child table.
  process_loss_qty is what ERPNext carries through to the Stock Entry's scrap
  rows; the scrap_items table disagrees with it on half the cards and is empty
  on 3,604 of them.
* Lot No reads ``Batch.custom_lot_no``. That field is currently empty for every
  Batch on the site, so the column renders blank until SEPL start filling it --
  which is still better than the literal 0 it used to print.

This is the same shape as ERPNext's own Job Card Summary report
(``erpnext/manufacturing/report/job_card_summary``), which also reads
posting_date / workstation / operation / total_completed_qty off the Job Card.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

# Job Card stores its operators in two child tables that share the
# `tabJob Card Time Log` table: `time_logs` (the ERPNext standard one) and
# `employee` (a Table MultiSelect). SEPL populates both, and not always with
# the same rows, so the report reads the table without filtering on
# parentfield and de-duplicates by employee id.
LIST_SEPARATOR = ", "


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	return get_columns(), get_data(filters)


def validate_filters(filters):
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are mandatory"))

	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))


def get_columns():
	"""Every fieldname that existed before SO1-I132 is kept, so saved column
	widths and pinned columns survive. machine_no / employee_name are the two
	Raj asked for; job_card / work_order are drill-down links."""
	return [
		{
			"fieldname": "date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"fieldname": "product_name",
			"label": _("Product Name"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 240,
		},
		{
			"fieldname": "opration_name",
			"label": _("Opration Name"),
			"fieldtype": "Link",
			"options": "Operation",
			"width": 150,
		},
		{
			"fieldname": "machine_no",
			"label": _("Machine No."),
			"fieldtype": "Link",
			"options": "Workstation",
			"width": 130,
		},
		{
			"fieldname": "employee_name",
			"label": _("Employee Name"),
			"fieldtype": "Data",
			"width": 260,
		},
		{
			"fieldname": "rm_batch_no",
			"label": _("RM Batch No."),
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"fieldname": "production_quantity",
			"label": _("Production Quantity"),
			"fieldtype": "Float",
			"width": 140,
		},
		{
			"fieldname": "qty_rejected",
			"label": _("Qty. Rejected"),
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"fieldname": "rej_",
			"label": _("Rej %"),
			"fieldtype": "Percent",
			"width": 80,
		},
		{
			"fieldname": "final_product_batch_no",
			"label": _("Final Product Batch no"),
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"fieldname": "lot_no",
			"label": _("Lot No"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "work_order",
			"label": _("Work Order"),
			"fieldtype": "Link",
			"options": "Work Order",
			"width": 160,
		},
		{
			"fieldname": "job_card",
			"label": _("Job Card"),
			"fieldtype": "Link",
			"options": "Job Card",
			"width": 130,
		},
	]


def get_job_card_conditions(filters):
	"""Shared WHERE clause so the job-card query and the operator query select
	exactly the same set of cards. Everything is bound, never interpolated."""
	conditions = [
		"jc.docstatus = 1",
		"jc.posting_date between %(from_date)s and %(to_date)s",
	]
	values = {"from_date": filters.from_date, "to_date": filters.to_date}

	for fieldname, column in (
		("company", "jc.company"),
		("item", "jc.production_item"),
		("operation", "jc.operation"),
		("workstation", "jc.workstation"),
		("work_order", "jc.work_order"),
	):
		if filters.get(fieldname):
			conditions.append(f"{column} = %({fieldname})s")
			values[fieldname] = filters.get(fieldname)

	if filters.get("employee"):
		# match the card if the operator appears in either operator table
		conditions.append(
			"""exists (
				select 1 from `tabJob Card Time Log` f
				where f.parent = jc.name and f.parenttype = 'Job Card'
					and f.employee = %(employee)s
			)"""
		)
		values["employee"] = filters.get("employee")

	return " and ".join(conditions), values


def get_job_cards(filters):
	conditions, values = get_job_card_conditions(filters)
	return frappe.db.sql(
		f"""
		select
			jc.name as job_card,
			jc.posting_date as date,
			jc.work_order,
			jc.production_item as product_name,
			jc.operation as opration_name,
			jc.workstation as machine_no,
			jc.total_completed_qty as production_quantity,
			jc.process_loss_qty as qty_rejected
		from `tabJob Card` jc
		where {conditions}
		order by jc.posting_date desc, jc.workstation, jc.name
		""",
		values,
		as_dict=True,
	)


def get_employee_names(filters):
	"""{job card: "NAME A, NAME B"} for every card in the current selection.

	A Job Card can be worked by several operators -- of the 10,769 submitted
	cards that record one, 3,005 record more than one, up to 21. The names are
	joined into a single cell rather than exploded into one row per operator,
	because the report totals Production Quantity and Qty. Rejected
	(add_total_row) and repeating a card per operator would multiply those
	totals by the crew size. Use the Employee filter to narrow the report to
	one person's cards; the column still shows that card's whole crew.
	"""
	conditions, values = get_job_card_conditions(filters)
	rows = frappe.db.sql(
		f"""
		select tl.parent as job_card, tl.employee, e.employee_name
		from `tabJob Card Time Log` tl
		inner join `tabJob Card` jc on jc.name = tl.parent
		left join `tabEmployee` e on e.name = tl.employee
		where tl.parenttype = 'Job Card'
			and ifnull(tl.employee, '') != ''
			and {conditions}
		order by tl.parent, tl.parentfield, tl.idx
		""",
		values,
		as_dict=True,
	)

	names = {}
	seen = set()
	for row in rows:
		key = (row.job_card, row.employee)
		if key in seen:
			continue
		seen.add(key)
		# fall back to the employee id if the Employee record is gone
		names.setdefault(row.job_card, []).append(row.employee_name or row.employee)

	return {card: LIST_SEPARATOR.join(crew) for card, crew in names.items()}


def get_batches(filters):
	"""Batches off the Manufacture Stock Entries of the day.

	Returns ({(work order, date, item): [fg batch]}, {(work order, date): [rm batch]}).
	Consumed rows are the ones that are neither the finished item nor scrap;
	scrap rows never carry a batch on this data.
	"""
	conditions = [
		"se.docstatus = 1",
		"se.purpose = 'Manufacture'",
		"se.posting_date between %(from_date)s and %(to_date)s",
		"ifnull(se.work_order, '') != ''",
		"ifnull(sed.batch_no, '') != ''",
	]
	values = {"from_date": filters.from_date, "to_date": filters.to_date}

	if filters.get("company"):
		conditions.append("se.company = %(company)s")
		values["company"] = filters.get("company")

	if filters.get("work_order"):
		conditions.append("se.work_order = %(work_order)s")
		values["work_order"] = filters.get("work_order")

	rows = frappe.db.sql(
		f"""
		select
			se.work_order, se.posting_date, sed.item_code, sed.batch_no,
			sed.is_finished_item, sed.is_scrap_item
		from `tabStock Entry` se
		inner join `tabStock Entry Detail` sed on sed.parent = se.name
		where {" and ".join(conditions)}
		order by se.posting_date, se.name, sed.idx
		""",
		values,
		as_dict=True,
	)

	finished, consumed = {}, {}
	for row in rows:
		if row.is_finished_item:
			bucket = finished.setdefault((row.work_order, row.posting_date, row.item_code), [])
		elif row.is_scrap_item:
			continue
		else:
			bucket = consumed.setdefault((row.work_order, row.posting_date), [])

		if row.batch_no not in bucket:
			bucket.append(row.batch_no)

	return finished, consumed


def get_lot_numbers(finished_batches):
	"""Lot No comes off the finished batch (Batch.custom_lot_no, a Seplt custom
	field). Guarded because the column only exists where the Seplt fixtures are
	installed."""
	if not frappe.db.has_column("Batch", "custom_lot_no"):
		return {}

	batch_ids = {batch for batches in finished_batches.values() for batch in batches}
	if not batch_ids:
		return {}

	rows = frappe.db.get_all(
		"Batch",
		filters={"name": ("in", list(batch_ids))},
		fields=["name", "custom_lot_no"],
	)
	return {row.name: row.custom_lot_no for row in rows if row.custom_lot_no}


def get_data(filters):
	job_cards = get_job_cards(filters)
	if not job_cards:
		return []

	employee_names = get_employee_names(filters)
	finished_batches, consumed_batches = get_batches(filters)
	lot_numbers = get_lot_numbers(finished_batches)

	data = []
	for card in job_cards:
		produced = flt(card.production_quantity)
		rejected = flt(card.qty_rejected)
		handled = produced + rejected

		fg_batches = finished_batches.get((card.work_order, card.date, card.product_name), [])
		rm_batches = consumed_batches.get((card.work_order, card.date), [])
		lots = [lot_numbers[batch] for batch in fg_batches if batch in lot_numbers]

		data.append(
			{
				"date": card.date,
				"product_name": card.product_name,
				"opration_name": card.opration_name,
				"machine_no": card.machine_no,
				"employee_name": employee_names.get(card.job_card),
				"rm_batch_no": LIST_SEPARATOR.join(rm_batches),
				"production_quantity": produced,
				"qty_rejected": rejected,
				"rej_": (rejected / handled * 100) if handled else 0.0,
				"final_product_batch_no": LIST_SEPARATOR.join(fg_batches),
				"lot_no": LIST_SEPARATOR.join(lots),
				"work_order": card.work_order,
				"job_card": card.job_card,
			}
		)

	return data
