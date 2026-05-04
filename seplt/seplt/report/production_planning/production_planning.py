# Copyright (c) 2024, Erpera and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate, today, cint


def execute(filters=None):
	columns, data = get_columns(), get_data(filters)
	return columns, data
def get_columns():
	return [

		# Customer Name
		{
			"fieldname": "customer_name",
			"label": "Customer Name",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "product_code",
			"label": "Product Code",
			"fieldtype": "Data",	
			"width": 150
		},
		# PO Date
		{
			"fieldname": "po_date",
			"label": "PO Date",
			"fieldtype": "Date",
			"width": 150
		},

		# delivery date
		{
			"fieldname": "delivery_date",
			"label": "Delivery Date",
			"fieldtype": "Date",
			"width": 150
		},
		

		
		
		# Tube Size
		{
			"fieldname": "tube_size",
			"label": "Tube Size",
			"fieldtype": "Data",
			"width": 150
		},
		# Lac/Un
		{
			"fieldname": "lac_un",
			"label": "Lac/Un",
			"fieldtype": "Data",
			"width": 150
		},
		# Slug Size
		{
			"fieldname": "slug_size",
			"label": "Slug Size",
			"fieldtype": "Data",
			"width": 150
		},
		# Latex
		{
			"fieldname": "latex",
			"label": "Latex",
			"fieldtype": "Data",
			"width": 150
		},
		# Product Name
		{
			"fieldname": "product_name",
			"label": "Product Name",
			"fieldtype": "Data",
			"width": 150
		},
		# Tube Gms
		{
			"fieldname": "tube_gms",
			"label": "Tube Gms",
			"fieldtype": "Data",
			"width": 150
		},
		# PO Qty
		{
			"fieldname": "po_qty",
			"label": "PO Qty",
			"fieldtype": "Data",
			"width": 150
		},
		# Excess Add 5%
		{
			"fieldname": "excess_add_5",
			"label": "Excess Add 5%",
			"fieldtype": "Data",
			"width": 150
		},
		# Customer Total Qty
		{
			"fieldname": "customer_total_qty",
			"label": "Customer Total Qty",
			"fieldtype": "Data",
			"width": 150
		},
		# Printed Qty
		{
			"fieldname": "printed_qty",
			"label": "Printed Qty",
			"fieldtype": "Data",
			"width": 150
		},
		# Pending
		{
			"fieldname": "pending",
			"label": "Pending",
			"fieldtype": "Data",
			"width": 150
		},
		# Customer Total Balance
		{
			"fieldname": "customer_total_balance",
			"label": "Customer Total Balance",
			"fieldtype": "Data",
			"width": 150
		},
		# Days Left
		{
			"fieldname": "days_left",
			"label": "Days Left",
			"fieldtype": "Data",
			"width": 150
		},

	
		
	]
@frappe.whitelist()
def get_sales_orders(filters=None):
    # submitted sales orders only
    sales_orders = frappe.get_all("Sales Order", filters={"docstatus": 1})
    data = []
    for so in sales_orders:
        so_doc = frappe.get_doc("Sales Order", so.name)
        days_left = cint((getdate(so_doc.delivery_date) - getdate(today())).days)
        customer_total_qty = 0
        items = list(so_doc.items)
        for idx, item in enumerate(items):
            qty = flt(item.qty)
            excess = qty * 0.05 + qty
            customer_total_qty += excess
            is_last = idx == len(items) - 1
            data.append({
                "customer_name": so_doc.customer if idx == 0 else "",
                "product_code": item.item_code,
                "po_date": so_doc.transaction_date,
                "delivery_date": so_doc.delivery_date,
                "tube_size": frappe.db.get_value("Item", item.item_code, "custom_tube_dia"),
                "lac_un": frappe.db.get_value("Item", item.item_code, "custom_lacquer_porosity"),
                "slug_size": "",
                "latex": "",
                "product_name": item.item_name,
                "tube_gms": "",
                "po_qty": qty,
                "excess_add_5": excess,
                "customer_total_qty": customer_total_qty if is_last else "",
                "printed_qty": "",
                "pending": "",
                "customer_total_balance": "",
                "days_left": max(days_left, 0),
            })
    return data
def get_total_po_quantity(supplier, item):
    # fetch submitted sales orders only
    po_qty = frappe.db.sql(
        """
        SELECT SUM(qty)
        FROM `tabSales Order Item`
        WHERE parent IN (
            SELECT name FROM `tabSales Order`
            WHERE docstatus = 1 AND customer = %s
        )
          AND item_code = %s
        """,
        (supplier, item),
    )
    return po_qty[0][0] if po_qty else 0
@frappe.whitelist()
def get_so_items(so_name):
    items = frappe.db.sql(
        "SELECT item_code, qty, rate, amount FROM `tabSales Order Item` WHERE parent = %s",
        (so_name,),
    )
    return items

def get_data(filters=None):
	return get_sales_orders(filters=filters)

