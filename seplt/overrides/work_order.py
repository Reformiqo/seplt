from erpnext.manufacturing.doctype.work_order.work_order import WorkOrder


class CustomWorkOrder(WorkOrder):
	def validate_subcontracting_inward_order(self):
		return
