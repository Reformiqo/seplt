"""Guards that stop a Manufacture Stock Entry from corrupting inventory valuation.

Background — the two defects these guards prevent, both found on the live SEPL
site on 09-08-2026:

1. ZERO-CONSUMPTION MANUFACTURE (410 entries, Rs 96.42 crore)
   A Manufacture entry produced finished stock while consuming nothing. ERPNext
   books the whole output as Dr Stock in Hand / Cr Stock Adjustment; because
   Stock Adjustment is mapped to the Balance Sheet the credit never reaches the
   P&L, so inventory is silently overstated.

2. AMOUNT-IN-RATE (MAT-STE-40604, Rs 93.92 crore = 97% of the above)
   The line *total* (Rs 20,085.76) was typed into the *rate* column for 46,760
   pcs, so ERPNext computed 46,760 x 20,085.76 = Rs 93.92 crore against a true
   rate of about Rs 0.43/pc — a ~28,000x error.

Neither entry could be corrected afterwards: the produced batch had already been
consumed downstream, so the document could not be cancelled, and a submitted
document's value cannot be edited in place. The only fix left was a journal
entry. Hence these guards — the errors have to be stopped at entry time.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

# A rate this many times the item's known rate is treated as a typo and blocked.
RATE_BLOCK_MULTIPLE = 100.0
# Between WARN and BLOCK the user is told, but the save proceeds.
RATE_WARN_MULTIPLE = 10.0
# Ignore reference rates at or below this — too small to compare meaningfully.
MIN_REFERENCE_RATE = 0.0001

OVERRIDE_FIELD = "custom_allow_manufacture_without_consumption"
OVERRIDE_ROLES = ("Stock Manager", "System Manager")


def _is_manufacture(doc) -> bool:
	"""True for Manufacture entries only — every other flow is left alone."""
	return (doc.get("purpose") or doc.get("stock_entry_type")) == "Manufacture"


def _source_rows(doc):
	"""Consumption rows: material leaving a warehouse."""
	return [d for d in (doc.get("items") or []) if d.get("s_warehouse")]


def _target_rows(doc):
	"""Production rows: material entering a warehouse and nothing leaving."""
	return [d for d in (doc.get("items") or []) if d.get("t_warehouse") and not d.get("s_warehouse")]


def _reference_rate(item_code: str, warehouse: str | None) -> float:
	"""Best known rate for an item, used as the sanity benchmark.

	Preference order: this warehouse's valuation, then any warehouse holding the
	item, then the Item master's own valuation / last purchase rate. Returns 0
	when the item has no history at all (a genuinely new item), in which case
	the caller skips the check rather than guessing.
	"""
	if warehouse:
		rate = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "valuation_rate")
		if flt(rate) > MIN_REFERENCE_RATE:
			return flt(rate)

	rate = frappe.db.sql(
		"""SELECT valuation_rate FROM `tabBin`
		WHERE item_code = %s AND valuation_rate > %s
		ORDER BY actual_qty DESC LIMIT 1""",
		(item_code, MIN_REFERENCE_RATE),
	)
	if rate and flt(rate[0][0]) > MIN_REFERENCE_RATE:
		return flt(rate[0][0])

	item = frappe.db.get_value("Item", item_code, ["valuation_rate", "last_purchase_rate"], as_dict=True)
	if item:
		for candidate in (item.valuation_rate, item.last_purchase_rate):
			if flt(candidate) > MIN_REFERENCE_RATE:
				return flt(candidate)
	return 0.0


def _override_allowed(doc) -> bool:
	"""The override checkbox only counts when set by someone entitled to set it."""
	if not doc.get(OVERRIDE_FIELD):
		return False
	roles = set(frappe.get_roles())
	if roles.isdisjoint(OVERRIDE_ROLES):
		frappe.throw(
			_("Only a {0} may tick '{1}'.").format(
				" or ".join(OVERRIDE_ROLES), _("Allow Manufacture Without Consumption")
			),
			title=_("Not Permitted"),
		)
	return True


def check_rate_sanity(doc, method=None):
	"""Block a rate that is wildly out of line with the item's known value.

	This is what catches a line total typed into the rate column. Runs on
	validate so the user is stopped at save, before anything is posted.
	"""
	if not _is_manufacture(doc):
		return

	blocked, warned = [], []
	for row in doc.get("items") or []:
		# ERPNext may clear basic_rate on a Manufacture roll-up before validate
		# runs, so fall back to the amount actually carried on the row.
		rate = flt(row.get("basic_rate"))
		if rate <= 0 and flt(row.get("qty")):
			rate = flt(row.get("basic_amount")) / flt(row.get("qty"))
		if rate <= 0:
			continue
		reference = _reference_rate(row.get("item_code"), row.get("t_warehouse") or row.get("s_warehouse"))
		if reference <= MIN_REFERENCE_RATE:
			continue  # no history to compare against — say nothing rather than guess

		multiple = rate / reference
		if multiple >= RATE_BLOCK_MULTIPLE:
			blocked.append(
				_("Row #{0}: {1} — rate {2} is {3:,.0f} times the known rate of {4}. "
				  "If you meant to enter a line total of {2}, put it in the Amount column instead; "
				  "the rate would be about {5}.").format(
					row.idx, row.get("item_code"), frappe.format_value(rate, {"fieldtype": "Currency"}),
					multiple, frappe.format_value(reference, {"fieldtype": "Currency"}),
					frappe.format_value(rate / flt(row.get("qty")) if flt(row.get("qty")) else 0,
										{"fieldtype": "Currency"}),
				)
			)
		elif multiple >= RATE_WARN_MULTIPLE:
			warned.append(
				_("Row #{0}: {1} — rate {2} is {3:,.1f} times the known rate of {4}. Please confirm.").format(
					row.idx, row.get("item_code"), frappe.format_value(rate, {"fieldtype": "Currency"}),
					multiple, frappe.format_value(reference, {"fieldtype": "Currency"}),
				)
			)

	if warned:
		frappe.msgprint(
			"<br>".join(warned), title=_("Unusually high rate"), indicator="orange"
		)
	if blocked:
		frappe.throw(
			"<br><br>".join(blocked),
			title=_("Rate looks like a data entry error"),
		)


def check_consumption(doc, method=None):
	"""Refuse a Manufacture entry that produces stock without consuming any.

	Such an entry creates inventory value out of nothing and posts the credit to
	Stock Adjustment on the Balance Sheet, so it never shows up in the P&L.
	Runs on submit — a draft may legitimately be half-built.
	"""
	if not _is_manufacture(doc):
		return

	# Use the header totals — these are the fields the defect actually shows up
	# in (total_outgoing_value = 0 while total_incoming_value > 0), and they
	# survive ERPNext's own rate roll-up. Fall back to the rows if absent.
	produced = flt(doc.get("total_incoming_value"))
	consumed = flt(doc.get("total_outgoing_value"))
	if not produced:
		produced = sum(flt(r.get("basic_amount")) for r in _target_rows(doc))
	if not consumed:
		consumed = sum(flt(r.get("basic_amount")) for r in _source_rows(doc))

	if produced <= 0:
		return  # nothing produced, nothing to fund

	if consumed > 0 or _source_rows(doc):
		return  # consumption present — normal entry

	if _override_allowed(doc):
		doc.add_comment(
			"Comment",
			text=_("Submitted without any consumption. Override ticked by {0}.").format(frappe.session.user),
		)
		return

	frappe.throw(
		_("This Manufacture entry produces {0} of stock but consumes no raw material.<br><br>"
		  "An entry like this creates inventory value from nothing and posts the credit to "
		  "Stock Adjustment on the Balance Sheet, so it never reaches the P&L.<br><br>"
		  "Add the raw material rows that were consumed. If this genuinely has no consumption, "
		  "a Stock Manager can tick 'Allow Manufacture Without Consumption'.").format(
			frappe.format_value(produced, {"fieldtype": "Currency"})
		),
		title=_("Missing consumption"),
	)


def install():
	"""Create the override checkbox. Idempotent; safe to run on every migrate."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Stock Entry": [
				{
					"fieldname": OVERRIDE_FIELD,
					"label": "Allow Manufacture Without Consumption",
					"fieldtype": "Check",
					"insert_after": "stock_entry_type",
					"default": "0",
					"depends_on": "eval:doc.stock_entry_type=='Manufacture'",
					"description": (
						"Permits submitting a Manufacture entry with no raw material consumed. "
						"Stock Manager only; the use is written to the timeline."
					),
					"module": "Seplt",
				}
			]
		},
		ignore_validate=True,
	)
	frappe.db.commit()
	print("seplt: manufacture_guard — override field installed")
