# Copyright (c) 2024, Erpera and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	columns, data = get_columns(filters=filters), get_datas(filters=filters)
	return columns, data

def get_columns(filters=None):
		# 	Date
		# Product Name
		# Opration Name
		# RM Batch No.
		# Production Quantity
		# Qty. Rejected
		# Rej %
		# Final Product Batch no
		# Lot No
	columns = [
		{
			"fieldname": "date",
			"label": "Date",
			"fieldtype": "Date",
			"width": 100
		},

		{
			"fieldname": "product_name",
			"label": "Product Name",
			"fieldtype": "Link",
			"options": "Item",
			"width": 200
		},
		{
			"fieldname": "opration_name",
			"label": "Opration Name",
			"fieldtype": "Link",
			"options": "Operation",
			"width": 200
		},
		{
			"fieldname": "rm_batch_no",
			"label": "RM Batch No.",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "production_quantity",
			"label": "Production Quantity",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "qty_rejected",
			"label": "Qty. Rejected",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "rej_",
			"label": "Rej %",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "final_product_batch_no",
			"label": "Final Product Batch no",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "lot_no",
			"label": "Lot No",
			"fieldtype": "Data",
			"width": 100
		}
	]
	return columns
def get_datas(filters=None):
	# stock_entry that has work ordr selected
	stok_entry = frappe.get_all("Stock Entry", filters={"work_order": ["!=", ""]}, fields=["name"])
	data = []
	for entry in stok_entry:
		se = frappe.get_doc("Stock Entry", entry.name)
		for item in se.items:
			data.append({
				"date": se.posting_date,
				"product_name": item.item_code,
				"opration_name": frappe.db.get_value("Work Order", se.work_order, "transfer_material_against"),
				"rm_batch_no": item.batch_no,
				"production_quantity": item.qty,
				"qty_rejected": 0,
				"rej_": 0,
				"final_product_batch_no": 0,
				"lot_no": 0
			})
	return data