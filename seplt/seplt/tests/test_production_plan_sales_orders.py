"""Tests for SO1-I150: no fully delivered Sales Orders in a Production Plan.

seplt/overrides/production_plan.py filters both ways a Sales Order reaches a
Production Plan -- the "Get Sales Orders" button (CustomProductionPlan) and the
Sales Order picker in the Sales Orders table (sales_order_query). These cover
the filter on its own, both entry points against this site's Sales Orders, and
the hooks that wire them in.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from seplt.overrides import production_plan as override
from seplt.overrides.production_plan import (
	DELIVERED_STATUSES,
	CustomProductionPlan,
	pending_delivery,
	sales_order_query,
)


def is_fully_delivered(name):
	status, per_delivered = frappe.db.get_value("Sales Order", name, ["status", "per_delivered"])
	return status in DELIVERED_STATUSES or per_delivered >= 100


class TestPendingDelivery(IntegrationTestCase):
	"""The filter itself, against the real Sales Orders on this site."""

	def test_empty_and_blank_names(self):
		self.assertEqual(pending_delivery([]), set())
		self.assertEqual(pending_delivery([None, ""]), set())

	def test_fully_delivered_orders_are_dropped(self):
		names = frappe.get_all(
			"Sales Order",
			filters={"docstatus": 1, "status": ("in", DELIVERED_STATUSES)},
			pluck="name",
			limit=50,
		)
		if not names:
			self.skipTest("no Completed / To Bill / Closed Sales Orders on this site")
		self.assertEqual(pending_delivery(names), set())

	def test_orders_still_to_deliver_are_kept(self):
		names = frappe.get_all(
			"Sales Order",
			filters={"docstatus": 1, "status": ("in", ("To Deliver and Bill", "To Deliver")), "per_delivered": ("<", 100)},
			pluck="name",
			limit=50,
		)
		if not names:
			self.skipTest("no Sales Orders still to deliver on this site")
		self.assertEqual(pending_delivery(names), set(names))


class TestGetSalesOrdersButton(IntegrationTestCase):
	"""CustomProductionPlan.get_open_sales_orders against this site's Sales Orders."""

	def make_plan(self, **values):
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("no Company on this site")
		return frappe.get_doc(
			{"doctype": "Production Plan", "company": company, "get_items_from": "Sales Order", **values}
		)

	def test_production_plan_uses_the_seplt_class(self):
		self.assertIsInstance(frappe.new_doc("Production Plan"), CustomProductionPlan)

	def test_no_fully_delivered_order_is_fetched(self):
		plan = self.make_plan()
		plan.get_open_sales_orders()
		fetched = [row.sales_order for row in plan.sales_orders]
		if not fetched:
			self.skipTest("no Sales Orders available for production on this site")
		self.assertEqual([so for so in fetched if is_fully_delivered(so)], [])

	def test_only_fully_delivered_orders_are_removed(self):
		"""What ERPNext would fetch, minus exactly the fully delivered orders -- nothing else changes."""
		from erpnext.manufacturing.doctype.production_plan.production_plan import get_sales_orders

		plan = self.make_plan()
		erpnext_fetch = [so.name for so in get_sales_orders(plan)]
		plan.get_open_sales_orders()
		fetched = [row.sales_order for row in plan.sales_orders]

		self.assertEqual(fetched, [so for so in erpnext_fetch if not is_fully_delivered(so)])

	def test_message_when_nothing_is_left(self):
		plan = self.make_plan()
		with patch.object(override, "pending_delivery", return_value=set()), patch("frappe.msgprint") as msgprint:
			plan.get_open_sales_orders()
		self.assertEqual(plan.sales_orders, [])
		msgprint.assert_called_once()


class TestSalesOrderPicker(IntegrationTestCase):
	"""sales_order_query: ERPNext's picker query, minus fully delivered orders, paged afterwards."""

	def test_no_fully_delivered_order_is_offered(self):
		rows = sales_order_query("Sales Order", "", "name", 0, 0, {})
		if not rows:
			self.skipTest("no Sales Orders available for production on this site")
		self.assertEqual([row[0] for row in rows if is_fully_delivered(row[0])], [])

	def test_paging_is_applied_after_the_filter(self):
		rows = [("SO-1",), ("SO-2",), ("SO-3",), ("SO-4",), ("SO-5",)]
		with (
			patch.object(override, "erpnext_sales_order_query", return_value=rows) as core,
			patch.object(override, "pending_delivery", return_value={"SO-2", "SO-3", "SO-4", "SO-5"}),
		):
			self.assertEqual(sales_order_query("Sales Order", "", "name", 0, 2, {}), [("SO-2",), ("SO-3",)])
			self.assertEqual(sales_order_query("Sales Order", "", "name", 2, 2, {}), [("SO-4",), ("SO-5",)])
			self.assertEqual(sales_order_query("Sales Order", "", "name", None, None, {}), rows[1:])

		# ERPNext's query is always asked for everything, unpaged.
		self.assertEqual(core.call_args.args[3:5], (None, None))

	def test_filters_and_text_are_passed_to_erpnexts_query(self):
		filters = {"company": "X", "item_code": "Y"}
		with (
			patch.object(override, "erpnext_sales_order_query", return_value=[]) as core,
			patch.object(override, "pending_delivery", return_value=set()),
		):
			sales_order_query("Sales Order", "SAL-ORD", "name", 0, 10, filters)
		self.assertEqual(core.call_args.args, ("Sales Order", "SAL-ORD", "name", None, None, filters))

	def test_hooks_wire_in_the_class_and_the_form_script(self):
		self.assertEqual(
			frappe.get_hooks("override_doctype_class", {}).get("Production Plan", [])[-1:],
			["seplt.overrides.production_plan.CustomProductionPlan"],
		)
		self.assertIn("public/js/production_plan.js", frappe.get_hooks("doctype_js", {}).get("Production Plan", []))
