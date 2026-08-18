# Copyright (c) 2026, Erpera and contributors
# For license information, please see license.txt

"""Purchase Receipt Trends Including Subcontracting -- SO1-I134.

Why this report exists
----------------------
The standard "Purchase Receipt Trends" report is a two-liner that delegates to
the shared trends engine (erpnext/stock/report/purchase_receipt_trends/
purchase_receipt_trends.py:14-15).  That engine builds its SQL from a single
hard-coded transaction pair -- ``tab{trans}`` / ``tab{trans} Item``
(erpnext/controllers/trends.py:107-218) -- so it can only ever read one
doctype.

In ERPNext v16 subcontracted material is *not* received on a Purchase Receipt;
it is received on the separate ``Subcontracting Receipt`` doctype with its own
``Subcontracting Receipt Item`` child table.  There is therefore no filter or
setting that can make the standard report show subcontracting receipts -- the
data is in tables the query never touches.  That is the defect Raj reported.

Approach
--------
Core is left untouched (``erpnext.controllers.trends`` is shared by seven
standard reports and by every other site on this bench).  Instead this report
reuses the core engine wholesale -- ``get_columns`` for the columns and the
based-on/period SQL fragments, ``calculate_total_row`` for the total row and
the standard report's own ``get_chart_data`` for the chart -- and replaces only
the two base tables with UNION ALL views over Purchase Receipt +
Subcontracting Receipt.  Filters, period bucketing, total row and chart shape
are therefore identical to the standard report by construction, and cannot
drift when ERPNext changes.

Field mapping (the two doctypes are not column-compatible)
----------------------------------------------------------
``Subcontracting Receipt Item`` has no ``stock_qty``, no ``base_net_amount``
and no ``item_group`` column, so:

* qty          -> ``qty * conversion_factor``  (accepted qty in stock UOM;
                  ``Subcontracting Receipt Item`` carries ``qty`` +
                  ``conversion_factor`` instead of a stored ``stock_qty``)
* amount       -> see "Amount Basis" below.
* item_group   -> resolved from ``tabItem`` (Purchase Receipt Item denormalises
                  it, Subcontracting Receipt Item does not).  Only the
                  subcontracting side is resolved this way; the purchase side
                  keeps its stored ``item_group`` so no quantity ever moves
                  between rows relative to the standard report.
* project      -> ``Subcontracting Receipt Item.project``, falling back to
                  the parent ``Subcontracting Receipt.project`` when the item
                  row leaves it blank (FRD FB-09; Purchase Receipt Item is
                  left as-is -- core already reads it directly and any
                  fallback behaviour there is out of scope for this report).

Amount Basis (SO1-I134 FRD, OP-01 / BR-03)
-------------------------------------------
``Subcontracting Receipt Item.rate`` is the full inward valuation rate --
``rm_cost_per_qty + service_cost_per_qty + additional_cost_per_qty +
secondary_items_cost_per_qty`` -- so ``amount`` (``qty * rate``) already
includes SEPL's own raw material cost.  That is not what a Purchase Receipt's
``base_net_amount`` represents, and summing it directly distorts the trend:
the FRD's own live-data example shows one receipt at Rs. 8,000 for 2,50,000
qty next to another at Rs. 12,00,000 for 4,00,000 qty, purely because raw
material cost was loaded into one and not the other.

The "Subcontracting Amount Basis" filter exposes both readings:

* Job Work / Service Value (default) -- ``service_cost_per_qty * qty``, the
  like-for-like equivalent of a Purchase Receipt net amount and the FRD's
  recommended default.
* Total Receipt Value -- ``amount``, the full inward stock valuation, for
  users who want that figure instead.

Receipt Type (SO1-I134 FRD, FR-02)
-----------------------------------
"All" (default) unions both doctypes, exactly as before.  "Purchase Receipt
Only" / "Subcontracting Receipt Only" isolate one side so the two can be
reconciled against each other (FRD TC-02/TC-03/TC-04) -- something the old
``include_subcontracting`` checkbox could not do, since switching it off only
ever produced the purchase-only view.

Permission handling (SO1-I134 FRD, FR-15)
--------------------------------------------
This report reads Subcontracting Receipt through raw SQL, which bypasses
Frappe's row-level permission framework entirely -- a user with no read
access on Subcontracting Receipt would otherwise see its figures regardless.
``resolve_doctypes`` checks report-level permission explicitly and drops the
subcontracting side (falling back to Purchase Receipt alone, never an empty
query) when it is missing, whatever Receipt Type was requested.

One deliberate deviation
------------------------
``item_name`` is read from the Item master (falling back to the stored value
for deleted items) on *both* sides.  The standard report selects the child
row's ``item_name`` while grouping on ``item_code``, so MariaDB returns an
arbitrary one of the historical names -- 13 item codes on this site have more
than one.  Which name wins then depends on scan order, so the standard report
and this one could disagree on a label for the same item.  Resolving it from
the master makes the column deterministic and keeps purchase and
subcontracting rows consistent with each other.  No figure is affected.
"""

import frappe
from frappe import _

from erpnext.controllers.trends import calculate_total_row, get_columns
from erpnext.stock.report.purchase_receipt_trends.purchase_receipt_trends import get_chart_data

# The engine is asked for "Purchase Receipt" shaped columns: that is what keeps
# the column set, the posting_date bucketing and the chart identical to the
# standard report (erpnext/controllers/trends.py:65-70, 255-258).
TRANS = "Purchase Receipt"

# "Group By" options offered by the standard purchase trends filters
# (erpnext/public/js/purchase_trends_filters.js:63).  Whitelisted rather than
# interpolated blindly, because the value lands in the SELECT clause.
GROUP_BY_COLUMN = {"Item": "t2.item_code", "Supplier": "t1.supplier"}

# Number of leading columns already filled by ``based_on_select`` before the
# period columns start -- copied from erpnext/controllers/trends.py:100-105 so
# the group-by row layout matches the standard report exactly.
BASED_ON_OFFSET = {"Customer": 3, "Supplier": 3, "Item": 2}

# FR-02: which parent doctypes "Receipt Type" unions. Whitelisted for the same
# reason as GROUP_BY_COLUMN -- the value only ever selects a dict key, never
# lands in SQL directly.
RECEIPT_TYPE_DOCTYPES = {
	"All": ["Purchase Receipt", "Subcontracting Receipt"],
	"Purchase Receipt Only": ["Purchase Receipt"],
	"Subcontracting Receipt Only": ["Subcontracting Receipt"],
}

# OP-01/BR-03/FR-09: how a subcontracting row's amount is read. Both sides are
# `qty`-adjacent expressions on `sri`, never raw filter input.
AMOUNT_BASIS_EXPR = {
	"Job Work / Service Value": "sri.service_cost_per_qty * sri.qty",
	"Total Receipt Value": "sri.amount",
}

# Every column is aliased: a UNION takes its column names from the first
# SELECT, so an unaliased expression there would be unaddressable downstream.
_PARENT_SOURCES = {
	"Purchase Receipt": """
		select name as name, company as company, posting_date as posting_date,
			docstatus as docstatus, supplier as supplier, supplier_name as supplier_name,
			'Purchase Receipt' as source_doctype
		from `tabPurchase Receipt` where docstatus = 1
	""",
	"Subcontracting Receipt": """
		select name as name, company as company, posting_date as posting_date,
			docstatus as docstatus, supplier as supplier, supplier_name as supplier_name,
			'Subcontracting Receipt' as source_doctype
		from `tabSubcontracting Receipt` where docstatus = 1
	""",
}

_PURCHASE_RECEIPT_ITEM_SOURCE = """
	select pri.parent as parent, pri.item_code as item_code,
		ifnull(itm.item_name, pri.item_name) as item_name,
		pri.item_group as item_group, pri.project as project,
		pri.stock_qty as stock_qty, pri.base_net_amount as base_net_amount,
		'Purchase Receipt' as source_doctype
	from `tabPurchase Receipt Item` pri
	left join `tabItem` itm on itm.name = pri.item_code
"""


def _subcontracting_receipt_item_source(amount_basis):
	"""FB-09: item-level project, falling back to the parent's when blank."""
	amount_expr = AMOUNT_BASIS_EXPR[amount_basis]
	return f"""
		select sri.parent as parent, sri.item_code as item_code,
			ifnull(itm.item_name, sri.item_name) as item_name,
			itm.item_group as item_group,
			ifnull(nullif(sri.project, ''), scr.project) as project,
			sri.qty * ifnull(sri.conversion_factor, 1) as stock_qty,
			{amount_expr} as base_net_amount,
			'Subcontracting Receipt' as source_doctype
		from `tabSubcontracting Receipt Item` sri
		left join `tabItem` itm on itm.name = sri.item_code
		left join `tabSubcontracting Receipt` scr on scr.name = sri.parent
	"""


def execute(filters=None):
	# The engine reads ``filters.period_based_on`` as an attribute
	# (erpnext/controllers/trends.py:72), so a plain dict would blow up when the
	# report is called from Python rather than from the desk.
	filters = frappe._dict(filters or {})

	conditions = get_columns(filters, TRANS)
	data = get_data(filters, conditions)

	return conditions["columns"], data, None, get_chart_data(data, filters)


def get_data(filters, conditions):
	group_by_column = None
	if filters.get("group_by"):
		group_by_column = GROUP_BY_COLUMN.get(filters.get("group_by"))
		if not group_by_column:
			frappe.throw(_("Group By {0} is not supported").format(filters.get("group_by")))

	doctypes = resolve_doctypes(filters)
	amount_basis = resolve_amount_basis(filters)
	parent_table, item_table = source_tables(doctypes, amount_basis)

	year_start_date, year_end_date = frappe.get_cached_value(
		"Fiscal Year", filters.get("fiscal_year"), ["year_start_date", "year_end_date"]
	)
	values = (filters.get("company"), year_start_date, year_end_date)

	parents = frappe.db.sql(
		build_query(
			conditions,
			parent_table,
			item_table,
			select=conditions["based_on_select"] + conditions["period_wise_select"],
			group_by=conditions["group_by"],
		),
		values,
		as_list=1,
	)

	if not group_by_column:
		parents.append(calculate_total_row(parents, conditions["columns"]))
		return parents

	return add_group_by_rows(
		filters, conditions, parent_table, item_table, values, parents, group_by_column
	)


def add_group_by_rows(filters, conditions, parent_table, item_table, values, parents, sel_col):
	"""Interleave one sub-row per Group By value under each Based On row.

	Same output shape as erpnext/controllers/trends.py:129-196, but resolved in
	a single grouped query instead of two queries per Based On value.
	"""
	children = frappe.db.sql(
		build_query(
			conditions,
			parent_table,
			item_table,
			# leading column is the Based On key, used only to attach the row to
			# its parent; the rest mirrors core's per-group query.
			select="{}, t4.default_currency as currency, {}, {}".format(
				conditions["group_by"], sel_col, conditions["period_wise_select"]
			),
			group_by=f"{conditions['group_by']}, {sel_col}",
		),
		values,
		as_list=1,
	)

	grouped = {}
	for child in children:
		grouped.setdefault(child[0], []).append(child[1:])

	columns = conditions["columns"]
	ind = columns.index(conditions["grbc"][0])
	inc = BASED_ON_OFFSET.get(filters.get("based_on"), 1)

	data = []
	for parent in parents:
		based_on_key = parent[0]
		# blank cell under the Group By column on the consolidated row
		parent.insert(ind, "")
		data.append(parent)

		for child in grouped.get(based_on_key, []):
			row = [""] * len(columns)
			row[ind - 1] = child[0]  # currency
			for j in range(1, len(columns) - inc):
				row[j + inc] = child[j]
			data.append(row)

	# total over the consolidated rows only, so group rows are not counted twice
	data.append(calculate_total_row(parents, columns))
	return data


def build_query(conditions, parent_table, item_table, select, group_by):
	"""Rebuild core's trends query against the union tables.

	Core's extra ``cond`` clauses (erpnext/controllers/trends.py:75-83) are all
	inert for Purchase Receipt: the project guard compares ``based_on_select``
	against ``"t2.project,"`` but the currency column is always appended to it
	(trends.py:423) so it never matches, and the closed-order / quotation guards
	only apply to Sales Order, Purchase Order and Quotation.
	"""
	return """
		select {select}
		from {parent_table}, {item_table} {addl_tables}
		where t2.parent = t1.name
			and t2.source_doctype = t1.source_doctype
			and t1.docstatus = 1
			and t1.company = %s
			and t1.posting_date between %s and %s
			{relational_cond}
		group by {group_by}
	""".format(
		select=select,
		parent_table=parent_table,
		item_table=item_table,
		addl_tables=conditions["addl_tables"],
		relational_cond=conditions.get("addl_tables_relational_cond", ""),
		group_by=group_by,
	)


def source_tables(doctypes, amount_basis):
	"""Return the ``t1`` (parent) and ``t2`` (item) derived tables.

	``source_doctype`` is carried on both sides and joined on, so a Purchase
	Receipt could never pick up a Subcontracting Receipt Item even if the two
	naming series ever produced the same document name.
	"""
	item_sources = {
		"Purchase Receipt": _PURCHASE_RECEIPT_ITEM_SOURCE,
		"Subcontracting Receipt": _subcontracting_receipt_item_source(amount_basis),
	}

	parent = " union all ".join(_PARENT_SOURCES[d] for d in doctypes)
	item = " union all ".join(item_sources[d] for d in doctypes)

	return f"({parent}) t1", f"({item}) t2"


def resolve_doctypes(filters):
	"""FR-02 (Receipt Type) narrowed by FR-15 (permission gating).

	A user without report-level read on Subcontracting Receipt must still get
	a working, error-free report -- scoped to Purchase Receipt only, whatever
	Receipt Type was requested. The union is never allowed to end up empty.
	"""
	receipt_type = filters.get("receipt_type") or "All"
	if receipt_type not in RECEIPT_TYPE_DOCTYPES:
		frappe.throw(_("Receipt Type {0} is not supported").format(receipt_type))

	doctypes = RECEIPT_TYPE_DOCTYPES[receipt_type]
	if "Subcontracting Receipt" in doctypes and not frappe.has_permission(
		"Subcontracting Receipt", "report"
	):
		doctypes = [d for d in doctypes if d != "Subcontracting Receipt"] or ["Purchase Receipt"]
	return doctypes


def resolve_amount_basis(filters):
	"""OP-01/FR-09. Meaningless (and ignored) once Subcontracting Receipt is
	excluded, since no subcontracting rows exist to apply it to."""
	amount_basis = filters.get("sco_amount_basis") or "Job Work / Service Value"
	if amount_basis not in AMOUNT_BASIS_EXPR:
		frappe.throw(_("Subcontracting Amount Basis {0} is not supported").format(amount_basis))
	return amount_basis
