// Copyright (c) 2026, Erpera and contributors
// For license information, please see license.txt

// SO1-I133 -- Raj asked for the Workstation filter on "JOB CARD SUMMARY V2" to
// accept more than one workstation.
//
// Every filter below is copied verbatim from
// erpnext/manufacturing/report/job_card_summary/job_card_summary.js so the two
// reports stay interchangeable.  The ONE deliberate difference is Workstation:
// core declares it `fieldtype: "Link"` (single value); here it is a
// MultiSelectList built the same way core builds "Work Orders" and
// "Production Item" (job_card_summary.js:55-72), i.e. a `get_data` that
// delegates to `frappe.db.get_link_options`.
//
// Operation and Status are left as-is on purpose -- SO1-I133 only asks for
// Workstation.  Operation would be the same two-line change here plus its
// fieldname in MULTI_SELECT_FILTERS; Status would not, see the note on that
// constant in the .py.

frappe.query_reports["Job Card Summary Multi Workstation"] = {
	filters: [
		{
			label: __("Company"),
			fieldname: "company",
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			reqd: 1,
			on_change: function (query_report) {
				var fiscal_year = query_report.get_values().fiscal_year;
				if (!fiscal_year) {
					return;
				}
				frappe.model.with_doc("Fiscal Year", fiscal_year, function (r) {
					var fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
					frappe.query_report.set_filter_value({
						from_date: fy.year_start_date,
						to_date: fy.year_end_date,
					});
				});
			},
		},
		{
			label: __("From Posting Date"),
			fieldname: "from_date",
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
			reqd: 1,
		},
		{
			label: __("To Posting Date"),
			fieldname: "to_date",
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[2],
			reqd: 1,
		},
		{
			label: __("Status"),
			fieldname: "status",
			fieldtype: "Select",
			options: ["", "Open", "Work In Progress", "Completed", "On Hold"],
		},
		{
			label: __("Work Orders"),
			fieldname: "work_order",
			fieldtype: "MultiSelectList",
			options: "Work Order",
			get_data: function (txt) {
				return frappe.db.get_link_options("Work Order", txt);
			},
		},
		{
			label: __("Production Item"),
			fieldname: "production_item",
			fieldtype: "MultiSelectList",
			options: "Item",
			get_data: function (txt) {
				return frappe.db.get_link_options("Item", txt);
			},
		},
		{
			// SO1-I133: the only departure from core -- Link -> MultiSelectList.
			label: __("Workstation"),
			fieldname: "workstation",
			fieldtype: "MultiSelectList",
			options: "Workstation",
			get_data: function (txt) {
				return frappe.db.get_link_options("Workstation", txt);
			},
		},
		{
			label: __("Operation"),
			fieldname: "operation",
			fieldtype: "Link",
			options: "Operation",
		},
	],
};
