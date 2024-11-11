# Copyright (c) 2024, Erpera and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	columns, data = get_coloumn(), get_data(filters)
	return columns, data
def get_coloumn():
	# 	Line	Select
	# Item Name	Select
	# Tube	Fetch
	# Planned	Fetch
	# Printed 	Fetch
	# Over / Excess Production 	Printed-Planned
	# Work Day	Total planning (D) / Capacity per day
	# Setting	No. of products = 1 Setting
	# Setting Quantity	total setting * Total no. of Tubes in 1 setting
	# Set time	Total J / capacity per day
	# Total Days	E8 + E11 (Condition total is Not more than 6 Days)
	coloumns = [
		{
			"fieldname": "line",
			"label": "Line",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "item_name",
			"label": "Item Name",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "tube",
			"label": "Tube",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "planned",
			"label": "Planned",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "printed",
			"label": "Printed",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "over_excess_production",
			"label": "Over / Excess Production",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "work_day",
			"label": "Work Day",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "setting",
			"label": "Setting",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "setting_quantity",
			"label": "Setting Quantity",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "set_time",
			"label": "Set time",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "total_days",
			"label": "Total Days",
			"fieldtype": "Data",
			"width": 100
		}
	]
	return coloumns
def get_data(filters):
	data = []
	wpp = frappe.get_all("Weekly Production Plan", filters=filters, fields=["*"])
	for w in wpp:
		planned = float(float(get_sales_order_item(w.item_name, w.sales_order)) * 0.05) + float(get_sales_order_item(w.item_name, w.sales_order)) or 0
		printed = get_total_qty(w.item_name) or 0
		over_excess_production = float(printed) - float(planned)
		data.append({
			"line": w.line,
			"item_name": w.item_name,
			"tube": w.tube,
			"planned": planned,
			"printed": printed,
			"over_excess_production": over_excess_production,
			"work_day": 1,
			"setting": 1,
			"setting_quantity": 2,
			"set_time": "",
			"total_days": ""
		})
	return data
def get_sales_order_item(item_code, so):
	so = frappe.get_doc("Sales Order", so)
	for item in so.items:
		if item.item_code == item_code:
			return item.qty
	return 0

@frappe.whitelist()
def get_total_qty(item_code):
    qty = frappe.db.sql(f"""
        SELECT SUM(sed.qty)
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE sed.item_code = %s AND se.stock_entry_type = 'Material Transfer for Manufacture'
    """, (item_code,))
    
    return qty[0][0] if qty else 0