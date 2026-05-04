# Copyright (c) 2024, Erpera and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, cint


def execute(filters=None):
	columns, data = get_columns(filters=filters), get_datas(filters=filters)
	return columns, data
def get_columns(filters=None):
		# 	Stock
		# Pending Po
		# Total
		# No of Slug Per Kg
		# Pending SO
		# Slug to be Needed
		# Balance Slug
		# Tube May Be Manufactured
		# Minimum Stock
		# Excess/Less Stock
		# Slug To Be orderd
		coloumns = [
			# item
			{
				"fieldname": "item",
				"label": "Item",
				"fieldtype": "Link",
				"options": "Item",
				"width": 200

			},
			{
				"fieldname": "stock",
				"label": "Stock",
				"fieldtype": "Data",
				"width": 100
			},
			{
				"fieldname": "pending_po",
				"label": "Pending Po",
				"fieldtype": "Data",
				"width": 100
			},
			{
				"fieldname": "total",
				"label": "Total",
				"fieldtype": "Data",
				"width": 100
			},
			{
				"fieldname": "no_of_slug_per_kg",
				"label": "No of Slug Per Kg",
				"fieldtype": "Data",
				"width": 100
			},
			{
				"fieldname": "pending_so",
				"label": "Pending SO",
				"fieldtype": "Data",
				"width": 100
			},
			{
				"fieldname": "slug_to_be_needed",
				"label": "Slug to be Needed",
				"fieldtype": "Data",
				"width": 100
			},
			{
				"fieldname": "balance_slug",
				"label": "Balance Slug",
				"fieldtype": "Data",
				"width": 100
			},
			{
				"fieldname": "tube_may_be_manufactured",
				"label": "Tube May Be Manufactured",
				"fieldtype": "Data",
				"width": 100
			},
			{
				"fieldname": "minimum_stock",
				"label": "Minimum Stock",
				"fieldtype": "Data",
				"width": 100
			},
			{
				"fieldname": "excess_less_stock",
				"label": "Excess/Less Stock",
				"fieldtype": "Data",
				"width": 100
			},
			{
				"fieldname": "slug_to_be_orderd",
				"label": "Slug To Be orderd",
				"fieldtype": "Data",
				"width": 100
			}
		]
		return coloumns
def get_datas(filters=None):
		# items in aluminium slug group
		items = frappe.get_all("Item", filters={"item_group": "Aluminum slug"})
		data = []
		for item in items:
			stock = flt(frappe.db.get_value("Bin", {"item_code": item.name}, "actual_qty"), 2)
			pending_po = flt(get_pending_po(item.name), 2)
			data.append({
				"item": item.name,
				"stock": stock,
				"pending_po": pending_po,
				"total": stock + pending_po,
				"no_of_slug_per_kg": 0,
				"pending_so": 0,
				"slug_to_be_needed": 0,
				"balance_slug": 0,
				"tube_may_be_manufactured": 0,
				"minimum_stock": frappe.db.get_value("Item", item.name, "min_order_qty") or 0,
				"excess_less_stock": 0,
				"slug_to_be_orderd": 0
			})
		return data
def get_pending_po(item):
		# get pending po for item where the parent is pending
		po = frappe.db.sql(
			"""
			SELECT SUM(qty)
			FROM `tabPurchase Order Item`
			WHERE item_code = %s
			  AND parent IN (
			      SELECT name FROM `tabPurchase Order`
			      WHERE status = 'To Receive and Bill'
			  )
			""",
			(item,),
		)
		return (po[0][0] if po and po[0] else 0) or 0