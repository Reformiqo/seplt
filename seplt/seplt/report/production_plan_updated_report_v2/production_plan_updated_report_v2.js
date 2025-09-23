// Copyright (c) 2025, Erpera and contributors
// For license information, please see license.txt

frappe.query_reports["Production Plan Updated Report V2"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 1
		},
		{
			"fieldname": "production_plan",
			"label": __("Production Plan"),
			"fieldtype": "Link",
			"options": "Production Plan"
		},
		{
			"fieldname": "work_order_status",
			"label": __("Work Order Status"),
			"fieldtype": "Select",
			"options": "\nDraft\nNot Started\nIn Process\nCompleted\nStopped\nClosed\nCancelled",
			"default": ""
		},
		{
			"fieldname": "plan_status",
			"label": __("Plan Status"),
			"fieldtype": "Select",
			"options": "\nDraft\nSubmitted\nIn Process\nCompleted\nCancelled",
			"default": ""
		}
	]
};
