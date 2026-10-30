"""SEPL additions to ERPNext's Production Planning Report (SO1-I148).

  * an "Actual Qty" column, and
  * From Date / To Date / Customer filters.

The report is ERPNext's own (erpnext/manufacturing/report/production_planning_report),
so it cannot be edited in place, and Frappe has no hook for overriding a report's
code. Instead this module wraps two methods of ``ProductionPlanReport``:
``execute_report`` (adds the column to what it returns) and ``get_open_orders``
(drops the orders the new filters exclude). The filters themselves are added to
the report's form by get_script() below.

What the column shows: the physical stock -- ``Bin.actual_qty`` -- of the row's
*raw material* (Raw Material Code) in the row's raw-material Warehouse, i.e. the
item and warehouse printed on the same row.

Why it is read from Bin again instead of reusing what the report already loaded:

  * The report hands out its Bin balances as it allots them --
    ``bin_data["actual_qty"] -= allotted_qty`` in prepare_data() and
    pick_materials_from_warehouses() -- so the ``actual_qty`` it copies onto a
    row is a running remainder, not the stock in the warehouse. Two orders using
    the same raw material would show different "stock" for the same item.
  * It only loads Bin rows for the order and filter warehouses, not for an
    item's Item Default warehouse, which is often the one shown on the row.

When the Raw Material Warehouse filter is a group warehouse, the report can put
that group on a row (for the quantity no child warehouse could cover); Bins only
exist for leaf warehouses, so such a row shows the total of its children.

The filters:

  * From Date / To Date apply to the date the report already shows and sorts by
    for each Based On: Delivery Date (Sales Order), Required Date (Material
    Request), Planned Start Date (Work Order). Either may be left empty.
  * Customer applies to Sales Orders only -- Material Requests and Work Orders
    have no customer -- and is hidden for the other two.

They are applied to the orders the report has already loaded, before it works
out raw materials, so allotment and every later step only see the orders kept.

Installed from hooks.py on every request and background job; see apply().
Nothing changes for any other site on the bench -- see _is_enabled().
"""

from importlib import import_module

import frappe
from frappe import _
from frappe.utils import flt, getdate

REPORT_MODULE = "erpnext.manufacturing.report.production_planning_report.production_planning_report"
REPORT_NAME = "Production Planning Report"
REPORT_CLASS = "ProductionPlanReport"
TARGET_METHODS = ("execute_report", "get_open_orders")

# The order date each Based On is filtered by -- the field the report already
# loads, shows in its date column and offers as Order By.
DATE_FIELDS = {
	"Sales Order": "delivery_date",
	"Material Request": "schedule_date",
	"Work Order": "planned_start_date",
}

# Not "actual_qty": the report already copies the running Bin remainder onto
# rows under that name (see the module docstring).
FIELDNAME = "rm_actual_qty"
# The column goes after the raw material's Warehouse, before Required Qty.
INSERT_AFTER = "warehouse"

_PATCHED = False
_WARNED = False
_ORIGINALS = {}


def _is_enabled():
	"""Whether the column applies to the site serving the current request.

	The patch rebinds a method on ERPNext's class, and Python caches modules per
	*process*, not per site: one worker serves every site on the bench. Deciding
	per call keeps the column to sites that installed seplt.
	"""
	return "seplt" in frappe.get_installed_apps()


def _execute_report(self):
	"""Replaces ``ProductionPlanReport.execute_report``: the original, plus the column."""
	columns, data = _ORIGINALS["execute_report"](self)

	if _is_enabled():
		add_actual_qty(columns, data)

	return columns, data


def _get_open_orders(self):
	"""Replaces ``ProductionPlanReport.get_open_orders``: the original, minus filtered-out orders."""
	_ORIGINALS["get_open_orders"](self)

	if _is_enabled():
		self.orders = filter_orders(self.orders, self.filters)


def filter_orders(orders, filters):
	"""The rows of ``orders`` that pass the From Date / To Date / Customer filters."""
	based_on = filters.get("based_on")
	from_date = getdate(filters.get("from_date")) if filters.get("from_date") else None
	to_date = getdate(filters.get("to_date")) if filters.get("to_date") else None
	date_field = DATE_FIELDS.get(based_on)

	if date_field and (from_date or to_date):
		kept = []
		for order in orders:
			# An order with no date cannot be placed in the range, so a range drops it.
			if not order.get(date_field):
				continue
			date = getdate(order.get(date_field))
			if (from_date and date < from_date) or (to_date and date > to_date):
				continue
			kept.append(order)
		orders = kept

	customer = filters.get("customer")
	if customer and based_on == "Sales Order" and orders:
		names = set(
			frappe.get_all(
				"Sales Order",
				filters={"name": ("in", list({o.name for o in orders})), "customer": customer},
				pluck="name",
			)
		)
		orders = [o for o in orders if o.name in names]

	return orders


def add_actual_qty(columns, data):
	"""Insert the Actual Qty column and fill it on every row of ``data``, in place."""
	column = {
		"label": _("Actual Qty"),
		"fieldname": FIELDNAME,
		"fieldtype": "Float",
		"width": 100,
	}
	fieldnames = [c.get("fieldname") for c in columns]
	if FIELDNAME not in fieldnames:
		position = fieldnames.index(INSERT_AFTER) + 1 if INSERT_AFTER in fieldnames else len(columns)
		columns.insert(position, column)

	stock = get_actual_qty({(row.get("item_code"), row.get("warehouse")) for row in data})
	for row in data:
		row[FIELDNAME] = stock.get((row.get("item_code"), row.get("warehouse")), 0.0)


def get_actual_qty(pairs):
	"""``{(item_code, warehouse): Bin.actual_qty}`` for each pair; a group warehouse sums its children.

	Pairs with no Bin are left out -- the caller shows 0 for them.
	"""
	from erpnext.stock.doctype.warehouse.warehouse import get_child_warehouses

	pairs = {(item, warehouse) for item, warehouse in pairs if item and warehouse}
	if not pairs:
		return {}

	# Bins only exist for leaf warehouses; map each requested warehouse to the
	# leaves whose stock it stands for (a leaf maps to itself).
	group_warehouses = set(
		frappe.get_all(
			"Warehouse",
			filters={"name": ("in", list({w for _i, w in pairs})), "is_group": 1},
			pluck="name",
		)
	)
	leaves = {
		warehouse: (get_child_warehouses(warehouse) if warehouse in group_warehouses else [warehouse])
		for _item, warehouse in pairs
	}

	bins = frappe.get_all(
		"Bin",
		fields=["item_code", "warehouse", "actual_qty"],
		filters={
			"item_code": ("in", list({i for i, _w in pairs})),
			"warehouse": ("in", list({leaf for ws in leaves.values() for leaf in ws})),
		},
	)
	by_leaf = {(b.item_code, b.warehouse): flt(b.actual_qty) for b in bins}

	result = {}
	for item, warehouse in pairs:
		found = [(item, leaf) for leaf in leaves[warehouse] if (item, leaf) in by_leaf]
		if found:
			result[(item, warehouse)] = sum(by_leaf[key] for key in found)
	return result


# Appended to ERPNext's report script by get_script(). Inserted after the
# report's own "Document Name" filter; skipped if already there, so loading the
# script twice does not duplicate them.
FILTERS_JS = """
(function () {
	const report = frappe.query_reports[%(report)s];
	if (!report || !report.filters) return;

	const fieldnames = report.filters.map((f) => f.fieldname);
	const added = [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			description: __("On Delivery Date / Required Date / Planned Start Date, per Based On"),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
			depends_on: "eval: doc.based_on == 'Sales Order'",
		},
	].filter((f) => !fieldnames.includes(f.fieldname));

	const position = fieldnames.indexOf("docnames") + 1 || report.filters.length;
	report.filters.splice(position, 0, ...added);
})();
"""


@frappe.whitelist()
def get_script(report_name: str):
	"""Replaces ``frappe.desk.query_report.get_script`` (override_whitelisted_methods).

	Returns Frappe's own result, with the SEPL filters appended to the script of
	this one report. Every other report is passed through untouched. Whitelisted
	because Frappe's API handler checks the override, not the method it replaces.
	"""
	from frappe.desk.query_report import get_script as frappe_get_script

	result = frappe_get_script(report_name)
	if report_name == REPORT_NAME and result.get("script"):
		result["script"] += FILTERS_JS % {"report": frappe.as_json(REPORT_NAME)}
	return result


def _load_target():
	"""ERPNext's report class, or None when it is not where we expect it."""
	try:
		module = import_module(REPORT_MODULE)
	except ImportError:
		return None

	klass = getattr(module, REPORT_CLASS, None)
	if klass is None or not all(callable(getattr(klass, name, None)) for name in TARGET_METHODS):
		return None
	return klass


def _install(klass):
	"""Rebind ``execute_report`` and ``get_open_orders`` on ``klass``. Idempotent.

	Each original is captured only from a method that is not already ours, so a
	second import or reload cannot capture the patch and recurse.
	"""
	replacements = {"execute_report": _execute_report, "get_open_orders": _get_open_orders}

	for name, replacement in replacements.items():
		original = getattr(klass, name)
		if original.__module__ != __name__:
			_ORIGINALS[name] = original

		setattr(klass, name, replacement)


def apply(*args, **kwargs):
	"""Install the patch. Idempotent; runs before every request and background job.

	Arguments are ignored -- before_request and before_job hooks are called with
	different ones. ``execute`` builds a fresh ProductionPlanReport per run and
	looks both methods up on the class, so rebinding them is enough.

	A missing target does not raise here, since this runs on every request; the
	report just shows without the column. assert_patch_targets() is what
	refuses, on migrate.
	"""
	global _PATCHED, _WARNED

	if _PATCHED:
		return

	klass = _load_target()
	if klass is None:
		if not _WARNED:
			_WARNED = True
			frappe.log_error(
				title="seplt: Production Planning Report additions NOT applied",
				message=(
					f"{REPORT_MODULE}.{REPORT_CLASS} or one of {', '.join(TARGET_METHODS)} was not found. "
					"Review seplt/overrides/production_planning_report.py."
				),
			)
		return  # not marked patched, so a later call re-checks

	_install(klass)
	_PATCHED = True


def assert_patch_targets():
	"""Fail the migrate if ERPNext moved what we patch.

	Without this, an ERPNext upgrade that renames the class would make the
	column and filters stop working without anyone being told. Called from hooks.after_migrate.
	"""
	if _load_target() is not None:
		return

	frappe.throw(
		_(
			"seplt adds the Actual Qty column and the From Date / To Date / Customer filters to the"
			" Production Planning Report by patching {0}.{1} ({2}), which no longer exists. Review"
			" seplt/overrides/production_planning_report.py against the installed ERPNext version."
		).format(REPORT_MODULE, REPORT_CLASS, ", ".join(TARGET_METHODS))
	)
