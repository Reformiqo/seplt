import frappe
from frappe import _
from frappe.utils import flt

from erpnext.buying.utils import check_on_hold_or_closed_status
from erpnext.controllers.subcontracting_inward_controller import SubcontractingInwardController
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


class NoSubcontractingInward(SubcontractingInwardController):
	"""Core StockEntry calls these as ``super().<method>()`` from inside StockEntry, so an
	override on CustomStockEntry is skipped by the MRO. Sitting between the StockController
	chain and SubcontractingInwardController, this shim is what that super() call resolves to.
	"""

	def validate_subcontracting_inward(self):
		# Every other step core runs here is gated on `subcontracting_inward_order`, which the
		# entries on this site never carry, so skipping them is a no-op. The cost update is the
		# exception — it is keyed on purpose alone, and it is what keeps "Receive from Customer"
		# out of the ledger. Dropping it left customer material valued at the item's own rate.
		self.update_customer_provided_item_cost()

	def update_customer_provided_item_cost(self):
		"""Zero the valuation of customer-owned material, parking its cost on the row.

		The incoming SLE takes its rate from ``valuation_rate`` (StockEntry.get_sle_for_target_warehouse),
		so zeroing it is what stops the receipt posting Stock In Hand against Stock Adjustment for
		stock the company does not own. Runs last in StockEntry.validate(), after
		calculate_rate_and_amount(), so nothing recomputes the rate afterwards.

		Core's version is not reused because it divides by ``transfer_qty``: "Receive from Customer"
		is one of the two purposes that keeps zero-qty rows (see StockEntry.set_items_for_stock_in),
		so that divisor can be zero here.
		"""
		if self.purpose != "Receive from Customer":
			return

		for item in self.items:
			item.valuation_rate = 0
			item.allow_zero_valuation_rate = 1

			per_unit_additional_cost = (
				flt(item.additional_cost) / flt(item.transfer_qty) if flt(item.transfer_qty) else 0.0
			)
			item.customer_provided_item_cost = flt(
				flt(item.basic_rate) + per_unit_additional_cost, item.precision("basic_rate")
			)


class CustomStockEntry(StockEntry, NoSubcontractingInward):
	def create_stock_reservation_entries_for_inward(self):
		return

	def cancel_stock_reservation_entries_for_inward(self):
		return

	def validate_receive_from_customer_cancel(self):
		# Keyed on purpose, not on the order link, so it also fires for "Receive from Customer"
		# entries made without a Subcontracting Inward Order — where scio_detail is empty and
		# core dereferences a None row.
		if not self.subcontracting_inward_order:
			return

		super().validate_receive_from_customer_cancel()

	def set_rate_for_outgoing_items(self, reset_outgoing_rate=True, raise_error_if_no_rate=True):
		"""Keep the customer's declared rate on "Subcontracting Delivery" rows.

		The rate typed into these rows is the value of the goods being sent back to the
		customer — it is what the e-Waybill has to declare. Core would replace it with
		``get_incoming_rate()`` off the source warehouse, which is 0 because the material was
		received under "Receive from Customer" at zero valuation, leaving the e-Waybill with
		``taxableAmount: 0``.

		``reset_outgoing_rate=False`` suppresses only that lookup. Core still derives
		``basic_amount`` from the rate, ``update_valuation_rate()`` still rolls it into
		``amount``, and india_compliance reads ``amount`` as the taxable value
		(CustomTaxController.update_item_taxable_value -> Stock Entry Detail.taxable_value ->
		GSTTransactionData.get_all_item_details).

		Ledger-neutral: the outgoing SLE is written with ``incoming_rate`` 0
		(StockEntry.get_sle_for_source_warehouse) and stock_ledger values the issue from the
		warehouse, so the rate on the row never reaches the GL.

		Stands down when india_compliance can already derive the value itself — see
		``has_scio_declared_value()``. Doing both would count the customer material twice.
		"""
		if self.purpose == "Subcontracting Delivery" and not self.has_scio_declared_value():
			reset_outgoing_rate = False

		return super().set_rate_for_outgoing_items(reset_outgoing_rate, raise_error_if_no_rate)

	def has_scio_declared_value(self):
		"""Whether india_compliance will price the customer material from the linked order.

		Mirrors the lookup in india_compliance's ``_set_subcontracting_delivery_additional_value``:
		it prices the row from ``Subcontracting Inward Order Received Item.rate``. That rate is
		only ever written by core's raw-material receipt flow, which needs the receipt Stock
		Entry to carry ``subcontracting_inward_order`` — receipts here are standalone, so it
		stays 0 and india_compliance contributes nothing.

		Checked against the data rather than against the order link, so this keeps working if
		those rates are populated later: the moment they are, the typed rate stands down and
		india_compliance takes over, instead of the two stacking.
		"""
		scio_details = {item.scio_detail for item in self.items if item.get("scio_detail")}
		if not scio_details:
			return False

		return bool(
			frappe.db.exists(
				"Subcontracting Inward Order Received Item",
				{
					"reference_name": ("in", list(scio_details)),
					"is_customer_provided_item": 1,
					"rate": (">", 0),
				},
			)
		)

	def before_submit(self):
		self.validate_declared_rate_for_delivery()

	def validate_declared_rate_for_delivery(self):
		# An e-Waybill is mandatory for "Subcontracting Delivery" and cannot be raised for a
		# nil consignment value. The rate is easy to lose without noticing: the client refetches
		# it from the warehouse whenever the item, warehouse, batch or UOM on a row changes
		# (erpnext's set_basic_rate / get_warehouse_details), so a row edited after the rate was
		# typed silently falls back to 0. Catch that here rather than at the NIC portal.
		if self.purpose != "Subcontracting Delivery" or self.has_scio_declared_value():
			return

		for item in self.items:
			if not flt(item.basic_rate):
				frappe.throw(
					_("Row #{0}: Please enter Basic Rate for Item {1}. It is the declared value of the consignment and is required for the e-Waybill.").format(
						item.idx, frappe.bold(item.item_code)
					),
					title=_("Missing Declared Value"),
				)
