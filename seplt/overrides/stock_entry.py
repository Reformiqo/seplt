from erpnext.buying.utils import check_on_hold_or_closed_status
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


class CustomStockEntry(StockEntry):
    def create_stock_reservation_entries_for_inward(self):
        return

    def cancel_stock_reservation_entries_for_inward(self):
        return

    def validate_subcontracting_inward(self):
        return

    def on_submit_subcontracting_inward(self):
        return

    def on_cancel_subcontracting_inward(self):
        return
