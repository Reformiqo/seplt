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
