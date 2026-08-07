from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


class CustomStockEntry(StockEntry):
	def create_stock_reservation_entries_for_inward(self):
		# Skip creating Stock Reservation Entries when a "Receive from
		# Customer" Stock Entry is submitted.
		pass

	def cancel_stock_reservation_entries_for_inward(self):
		# No reservation entries are created on submit, so nothing to cancel.
		pass
