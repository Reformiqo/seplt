"""Tests for seplt's additions to ERPNext's Production Planning Report (SO1-I148).

seplt/overrides/production_planning_report.py wraps ERPNext's
ProductionPlanReport.execute_report and get_open_orders, and appends filters to
the report's script. These cover the Actual Qty column (placement and per-row
values), the stock lookup against the real Bins on this site, the From Date /
To Date / Customer filters, and the patch: installed by apply(), limited to
seplt sites, and guarded on migrate.
"""

import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, get_datetime

from seplt.overrides import production_planning_report as override
from seplt.overrides.production_planning_report import (
	FIELDNAME,
	REPORT_NAME,
	add_actual_qty,
	apply,
	assert_patch_targets,
	filter_orders,
	get_actual_qty,
	get_script,
)

REPORT_FILTERS = {
	"company": None,  # filled in setUpClass
	"based_on": "Sales Order",
	"order_by": "Delivery Date",
}


def report_columns():
	"""The raw-material end of the report's column list, as ERPNext builds it."""
	return [
		{"fieldname": "name"},
		{"fieldname": "production_item"},
		{"fieldname": "item_code"},
		{"fieldname": "raw_material_name"},
		{"fieldname": "warehouse"},
		{"fieldname": "required_qty"},
		{"fieldname": "allotted_qty"},
	]


class TestAddActualQty(IntegrationTestCase):
	"""Column placement and per-row values, with the stock lookup stubbed out."""

	def _run(self, columns, data):
		stock = {("RM-1", "Stores - X"): 120.0, ("RM-2", "Stores - X"): -5.0}
		with patch.object(override, "get_actual_qty", return_value=stock):
			add_actual_qty(columns, data)

	def test_column_goes_after_the_raw_material_warehouse(self):
		columns = report_columns()
		self._run(columns, [])
		fieldnames = [c["fieldname"] for c in columns]
		self.assertEqual(fieldnames.index(FIELDNAME), fieldnames.index("warehouse") + 1)
		self.assertEqual(fieldnames[fieldnames.index(FIELDNAME) + 1], "required_qty")

		column = columns[fieldnames.index(FIELDNAME)]
		self.assertEqual(column["label"], "Actual Qty")
		self.assertEqual(column["fieldtype"], "Float")

	def test_column_is_appended_when_warehouse_column_is_absent(self):
		columns = [{"fieldname": "name"}, {"fieldname": "item_code"}]
		self._run(columns, [])
		self.assertEqual(columns[-1]["fieldname"], FIELDNAME)

	def test_column_is_not_added_twice(self):
		columns = report_columns()
		self._run(columns, [])
		self._run(columns, [])
		self.assertEqual([c["fieldname"] for c in columns].count(FIELDNAME), 1)

	def test_each_row_shows_its_own_item_and_warehouse_stock(self):
		data = [
			frappe._dict(item_code="RM-1", warehouse="Stores - X"),
			frappe._dict(item_code="RM-2", warehouse="Stores - X"),
			frappe._dict(item_code="RM-1", warehouse="Stores - X"),  # same RM, later order
		]
		self._run(report_columns(), data)
		self.assertEqual([row[FIELDNAME] for row in data], [120.0, -5.0, 120.0])

	def test_row_without_a_bin_shows_zero(self):
		data = [frappe._dict(item_code="RM-3", warehouse="Stores - X"), frappe._dict(item_code="", warehouse="")]
		self._run(report_columns(), data)
		self.assertEqual([row[FIELDNAME] for row in data], [0.0, 0.0])

	def test_actual_qty_is_not_the_reports_running_remainder(self):
		"""The report copies a decremented Bin balance onto rows as `actual_qty`; ours must ignore it."""
		data = [frappe._dict(item_code="RM-1", warehouse="Stores - X", actual_qty=7.0)]
		self._run(report_columns(), data)
		self.assertEqual(data[0][FIELDNAME], 120.0)
		self.assertEqual(data[0].actual_qty, 7.0, "the report's own field is left alone")


class TestGetActualQtyAgainstRealBins(IntegrationTestCase):
	"""No stubs: the lookup has to agree with tabBin on this site."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		row = frappe.db.sql(
			"""SELECT b.item_code, b.warehouse, b.actual_qty, w.parent_warehouse
			FROM `tabBin` b JOIN `tabWarehouse` w ON w.name = b.warehouse
			WHERE b.actual_qty != 0 AND IFNULL(w.parent_warehouse, '') != ''
			ORDER BY b.modified DESC LIMIT 1""",
			as_dict=True,
		)
		cls.bin = row[0] if row else None

	def setUp(self):
		if not self.bin:
			self.skipTest("no Bin with stock under a group warehouse on this site")

	def test_leaf_warehouse_returns_bin_actual_qty(self):
		key = (self.bin.item_code, self.bin.warehouse)
		self.assertAlmostEqual(get_actual_qty([key])[key], flt(self.bin.actual_qty))

	def test_group_warehouse_returns_the_sum_of_its_children(self):
		group = self.bin.parent_warehouse
		expected = frappe.db.sql(
			"""SELECT SUM(b.actual_qty) FROM `tabBin` b
			JOIN `tabWarehouse` w ON w.name = b.warehouse
			JOIN `tabWarehouse` g ON g.name = %s
			WHERE b.item_code = %s AND w.lft >= g.lft AND w.rgt <= g.rgt""",
			(group, self.bin.item_code),
		)[0][0]
		key = (self.bin.item_code, group)
		self.assertAlmostEqual(get_actual_qty([key])[key], flt(expected))

	def test_item_without_a_bin_is_left_out(self):
		key = ("__no_such_item__", self.bin.warehouse)
		self.assertNotIn(key, get_actual_qty([key]))

	def test_empty_and_blank_pairs(self):
		self.assertEqual(get_actual_qty([]), {})
		self.assertEqual(get_actual_qty([(None, None), ("", self.bin.warehouse)]), {})


class TestPatchOnInstalledERPNext(IntegrationTestCase):
	"""The patch against the ERPNext actually installed on this bench."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		apply()
		cls.module = frappe.get_module(override.REPORT_MODULE)
		cls.filters = dict(REPORT_FILTERS, company=frappe.db.get_value("Company", {}, "name"))

	def test_patch_target_exists_in_the_installed_version(self):
		assert_patch_targets()  # must not raise

	def test_apply_installs_and_is_idempotent(self):
		apply()
		apply()
		klass = self.module.ProductionPlanReport
		self.assertIs(klass.execute_report, override._execute_report)
		self.assertIs(klass.get_open_orders, override._get_open_orders)
		for name in ("execute_report", "get_open_orders"):
			original = override._ORIGINALS[name]
			self.assertNotEqual(original.__module__, override.__name__, "the original, not our own wrapper")

	def test_report_has_the_column_on_a_seplt_site(self):
		columns, data = self.module.execute(self.filters)
		self.assertIn(FIELDNAME, [c["fieldname"] for c in columns])

		expected = get_actual_qty({(row.get("item_code"), row.get("warehouse")) for row in data})
		for row in data:
			self.assertEqual(row[FIELDNAME], expected.get((row.get("item_code"), row.get("warehouse")), 0.0))

	def test_other_sites_get_the_report_unchanged(self):
		with patch.object(override, "_is_enabled", return_value=False):
			columns, data = self.module.execute(self.filters)
		self.assertNotIn(FIELDNAME, [c["fieldname"] for c in columns])
		self.assertTrue(all(FIELDNAME not in row for row in data))

	def test_is_enabled_follows_the_sites_installed_apps(self):
		with patch("frappe.get_installed_apps", return_value=["frappe", "erpnext", "seplt"]):
			self.assertTrue(override._is_enabled())
		with patch("frappe.get_installed_apps", return_value=["frappe", "erpnext"]):
			self.assertFalse(override._is_enabled())


class TestMissingTarget(IntegrationTestCase):
	"""An ERPNext that moved the report class: migrate refuses, requests carry on."""

	def test_assert_patch_targets_fails_the_migrate(self):
		with patch.object(override, "_load_target", return_value=None), self.assertRaises(frappe.ValidationError):
			assert_patch_targets()

	def test_apply_does_not_raise_and_retries_later(self):
		with (
			patch.object(override, "_PATCHED", False),
			patch.object(override, "_WARNED", True),
			patch.object(override, "_load_target", return_value=None),
		):
			apply()  # must not raise
			self.assertFalse(override._PATCHED)


def order(name, **dates):
	return frappe._dict(name=name, **dates)


class TestFilterOrders(IntegrationTestCase):
	"""From Date / To Date / Customer on the orders the report loaded."""

	SO_ORDERS = (
		order("SO-1", delivery_date=datetime.date(2026, 10, 1)),
		order("SO-2", delivery_date=datetime.date(2026, 10, 15)),
		order("SO-3", delivery_date=datetime.date(2026, 10, 31)),
		order("SO-4", delivery_date=None),
	)

	def names(self, orders):
		return [o.name for o in orders]

	def test_no_filters_keeps_every_order(self):
		kept = filter_orders(list(self.SO_ORDERS), frappe._dict(based_on="Sales Order"))
		self.assertEqual(self.names(kept), ["SO-1", "SO-2", "SO-3", "SO-4"])

	def test_date_range_is_inclusive_on_both_ends(self):
		filters = frappe._dict(based_on="Sales Order", from_date="2026-10-01", to_date="2026-10-15")
		self.assertEqual(self.names(filter_orders(list(self.SO_ORDERS), filters)), ["SO-1", "SO-2"])

	def test_open_ended_ranges(self):
		after = frappe._dict(based_on="Sales Order", from_date="2026-10-15")
		before = frappe._dict(based_on="Sales Order", to_date="2026-10-14")
		self.assertEqual(self.names(filter_orders(list(self.SO_ORDERS), after)), ["SO-2", "SO-3"])
		self.assertEqual(self.names(filter_orders(list(self.SO_ORDERS), before)), ["SO-1"])

	def test_order_without_a_date_is_dropped_by_a_range(self):
		filters = frappe._dict(based_on="Sales Order", from_date="2026-01-01")
		self.assertNotIn("SO-4", self.names(filter_orders(list(self.SO_ORDERS), filters)))

	def test_material_request_uses_required_date(self):
		orders = [
			order("MR-1", schedule_date=datetime.date(2026, 10, 5)),
			order("MR-2", schedule_date=datetime.date(2026, 11, 5)),
		]
		filters = frappe._dict(based_on="Material Request", to_date="2026-10-31")
		self.assertEqual(self.names(filter_orders(orders, filters)), ["MR-1"])

	def test_work_order_uses_planned_start_date_including_its_time(self):
		orders = [
			order("WO-1", planned_start_date=get_datetime("2026-10-31 23:30:00")),
			order("WO-2", planned_start_date=get_datetime("2026-11-01 00:00:00")),
		]
		filters = frappe._dict(based_on="Work Order", to_date="2026-10-31")
		self.assertEqual(self.names(filter_orders(orders, filters)), ["WO-1"])

	def test_customer_keeps_only_that_customers_sales_orders(self):
		filters = frappe._dict(based_on="Sales Order", customer="CUST-A")
		with patch("frappe.get_all", return_value=["SO-2"]) as get_all:
			kept = filter_orders(list(self.SO_ORDERS), filters)
		self.assertEqual(self.names(kept), ["SO-2"])
		self.assertEqual(get_all.call_args.kwargs["filters"]["customer"], "CUST-A")

	def test_customer_is_ignored_for_material_request_and_work_order(self):
		orders = [order("MR-1", schedule_date=datetime.date(2026, 10, 5))]
		for based_on in ("Material Request", "Work Order"):
			with patch("frappe.get_all") as get_all:
				kept = filter_orders(list(orders), frappe._dict(based_on=based_on, customer="CUST-A"))
			self.assertEqual(self.names(kept), ["MR-1"])
			get_all.assert_not_called()


class TestFiltersOnInstalledERPNext(IntegrationTestCase):
	"""The filters through the real report, against this site's Sales Orders."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		apply()
		cls.module = frappe.get_module(override.REPORT_MODULE)
		cls.company = frappe.db.get_value("Company", {}, "name")

	def run_report(self, **filters):
		_columns, data = self.module.execute(dict(REPORT_FILTERS, company=self.company, **filters))
		return data

	def test_date_range_keeps_only_orders_delivering_in_it(self):
		dates = [row.delivery_date for row in self.run_report() if row.get("name")]
		if not dates:
			self.skipTest("no open Sales Orders on this site")
		middle = sorted(dates)[len(dates) // 2]

		data = self.run_report(from_date=str(middle), to_date=str(middle))
		self.assertTrue(data, "the middle delivery date's own orders must stay")
		for row in data:
			if row.get("name"):
				self.assertEqual(frappe.utils.getdate(row.delivery_date), frappe.utils.getdate(middle))

	def test_customer_keeps_only_that_customers_orders(self):
		names = {row.name for row in self.run_report() if row.get("name")}
		if not names:
			self.skipTest("no open Sales Orders on this site")
		customer = frappe.db.get_value("Sales Order", min(names), "customer")

		kept = {row.name for row in self.run_report(customer=customer) if row.get("name")}
		self.assertTrue(kept)
		expected = set(frappe.get_all("Sales Order", {"name": ("in", list(names)), "customer": customer}, pluck="name"))
		self.assertEqual(kept, expected & names)


class TestGetScript(IntegrationTestCase):
	"""The filters are added to this report's form, and only to it."""

	def test_filters_are_appended_to_the_report_script(self):
		script = get_script(REPORT_NAME)["script"]
		for fieldname in ("from_date", "to_date", "customer"):
			self.assertIn(f'fieldname: "{fieldname}"', script)
		self.assertIn("eval: doc.based_on == 'Sales Order'", script)

	def test_other_reports_are_untouched(self):
		from frappe.desk.query_report import get_script as frappe_get_script

		other = "Stock Ledger"
		self.assertEqual(get_script(other), frappe_get_script(other))

	def test_hook_points_frappes_method_at_ours(self):
		self.assertEqual(
			frappe.override_whitelisted_method("frappe.desk.query_report.get_script"),
			"seplt.overrides.production_planning_report.get_script",
		)
