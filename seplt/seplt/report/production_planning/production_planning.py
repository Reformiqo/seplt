# Copyright (c) 2024, Erpera and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate, add_days, today, date_diff, cint


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
    # submitted saels sales_orders
    sales_orders = frappe.get_all("Sales Order", filters={"docstatus": 1})
    data = []
    customers = []
    for so in sales_orders:
        so_doc = frappe.get_doc("Sales Order", so.name)
        days_left = cint((getdate(so_doc.delivery_date) - getdate(today())).days)
        customer_total_qty = 0
        for item in so_doc.items:
            customer_total_qty += float(float(item.qty) * 0.05) + float(item.qty)
            data.append({
                # only append the customer tota qty at the first item of the sales order
                "customer_name": so_doc.customer if item == so_doc.items[0] else "",
                "product_code": item.item_code,
                "po_date": so_doc.transaction_date,
                "delivery_date": so_doc.delivery_date,
                "tube_size": frappe.db.get_value("Item", item.item_code, "custom_tube_dia"),
                "lac_un": frappe.db.get_value("Item", item.item_code, "custom_lacquer_porosity"),
                "slug_size": "sample-slug",
                "latex": "sample-latex",
                "product_name": item.item_name,
                "tube_gms": "sample-tube-gms",
                "po_qty": item.qty,
                "excess_add_5": float(float(item.qty) * 0.05) + float(item.qty),
                "customer_total_qty": customer_total_qty if item == so_doc.items[-1] else "",
                "printed_qty": "sample-printed-qty",
                "pending": "sample-pending",
                "customer_total_balance": "sample-customer-total-balance",
                "days_left": days_left if days_left > 0 else 0
	
            })
            customers.append(so_doc.customer) if so_doc.customer not in customers else ""
        # clear the customers list
        customers.clear()
    return data
def get_total_po_quantity(supplier, item):
    # fetch submitte sales orders only
    po_qty = frappe.db.sql(f"SELECT SUM(qty) FROM `tabSales Order Item` WHERE parent IN (SELECT name FROM `tabSales Order` WHERE docstatus=1 AND customer='{supplier}') AND item_code='{item}'")
    return po_qty[0][0] if po_qty else 0
@frappe.whitelist()
def get_so_items(so_name):
    items = frappe.db.sql(f"SELECT item_code, qty, rate, amount FROM `tabSales Order Item` WHERE parent='{so_name}'")
    return items

def get_data(filters=None):
	return get_sales_orders(filters=filters)

