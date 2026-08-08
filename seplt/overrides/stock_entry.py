from erpnext.buying.utils import check_on_hold_or_closed_status
from erpnext.controllers.subcontracting_inward_controller import SubcontractingInwardController
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


class NoSubcontractingInward(SubcontractingInwardController):
	"""Core StockEntry calls these as ``super().<method>()`` from inside StockEntry, so an
	override on CustomStockEntry is skipped by the MRO. Sitting between the StockController
	chain and SubcontractingInwardController, this shim is what that super() call resolves to.
	"""

	def validate_subcontracting_inward(self):
		return


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
