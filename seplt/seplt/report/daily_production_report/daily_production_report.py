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
	rows = frappe.db.sql(
		"""
		SELECT
			se.posting_date,
			sed.item_code,
			wo.transfer_material_against,
			sed.batch_no,
			sed.qty
		FROM `tabStock Entry Detail` sed
		JOIN `tabStock Entry` se ON se.name = sed.parent
		LEFT JOIN `tabWork Order` wo ON wo.name = se.work_order
		WHERE se.work_order IS NOT NULL AND se.work_order != ''
		ORDER BY se.posting_date DESC
		""",
		as_dict=True,
	)
	return [
		{
			"date": r.posting_date,
			"product_name": r.item_code,
			"opration_name": r.transfer_material_against,
			"rm_batch_no": r.batch_no,
			"production_quantity": r.qty,
			"qty_rejected": 0,
			"rej_": 0,
			"final_product_batch_no": "",
			"lot_no": "",
		}
		for r in rows
	]