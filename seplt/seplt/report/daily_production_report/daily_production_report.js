// Copyright (c) 2024, Erpera and contributors
// For license information, please see license.txt

frappe.query_reports["Daily Production Report"] = {
	filters: [
		{
			// SO1-I132: the report had no filters at all and walked every Stock
			// Entry on the site. It is a *daily* report, so it opens on today.
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "operation",
			label: __("Operation"),
			fieldtype: "Link",
			options: "Operation",
		},
		{
			fieldname: "workstation",
			label: __("Machine No."),
			fieldtype: "Link",
			options: "Workstation",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "work_order",
			label: __("Work Order"),
			fieldtype: "Link",
			options: "Work Order",
		},
	],
};
