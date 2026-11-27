"""Keep fully delivered Sales Orders out of a Production Plan (SO1-I150).

ERPNext offers a Sales Order to a Production Plan -- through the "Get Sales
Orders" button and through the Sales Order picker in the Sales Orders table --
when any of its lines still has stock qty above what earlier plans covered:
``stock_qty - reserved qty > production_plan_qty``. That says nothing about
delivery. An order delivered straight from stock, without a Production Plan,
keeps ``production_plan_qty`` at 0, so it stays on offer for ever: status
Completed or To Bill, nothing left to make. The button's query only drops
Stopped and Closed orders; the picker's query looks at no status at all.

Here, both drop every Sales Order with nothing left to deliver: status
Completed or To Bill (the two statuses ERPNext gives a 100% delivered order),
Closed, or ``per_delivered`` at 100. Orders To Deliver and Bill, To Deliver,
partly delivered or On Hold are offered as before.
"""

import frappe
from frappe import _
from frappe.utils import cint

from erpnext.manufacturing.doctype.production_plan.production_plan import (
	ProductionPlan,
	get_sales_orders,
)
from erpnext.manufacturing.doctype.production_plan.production_plan import (
	sales_order_query as erpnext_sales_order_query,
)

# Statuses of a Sales Order with nothing left to deliver.
DELIVERED_STATUSES = ("Completed", "To Bill", "Closed")


def pending_delivery(names):
	"""The Sales Orders among ``names`` that still have something to deliver."""
	names = list({name for name in names if name})
	if not names:
		return set()

	return set(
		frappe.get_all(
			"Sales Order",
			filters={
				"name": ("in", names),
				"status": ("not in", DELIVERED_STATUSES),
				"per_delivered": ("<", 100),
			},
			pluck="name",
		)
	)


class CustomProductionPlan(ProductionPlan):
	@frappe.whitelist()
	def get_open_sales_orders(self):
		"""ERPNext's "Get Sales Orders", minus the fully delivered orders."""
		open_so = get_sales_orders(self)
		pending = pending_delivery(so.name for so in open_so)
		open_so = [so for so in open_so if so.name in pending]

		self.add_so_in_table(open_so)
		if not open_so:
			frappe.msgprint(_("Sales orders are not available for production"))


@frappe.whitelist()
def sales_order_query(doctype=None, txt=None, searchfield=None, start=None, page_len=None, filters=None):
	"""ERPNext's Sales Order picker query for the Sales Orders table, minus fully delivered orders.

	Set on the form by public/js/production_plan.js. ERPNext's query runs
	unpaged, with its own permission and user-permission checks, and the paging
	is applied after the filter here -- paging first would leave short pages.
	"""
	rows = erpnext_sales_order_query(doctype, txt, searchfield, None, None, filters)
	pending = pending_delivery(row[0] for row in rows)
	rows = [row for row in rows if row[0] in pending]

	start = cint(start)
	return rows[start : start + cint(page_len)] if cint(page_len) else rows[start:]
