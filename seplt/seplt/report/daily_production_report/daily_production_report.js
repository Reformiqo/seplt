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
	// SO1-I132 (reopened): the datatable's default columnTotal hook averages
	// Percent-column values row-by-row (frappe.utils.report_column_total),
	// which is wrong for Rej % -- it weighs a 2-piece job the same as a
	// 45,000-piece job. Override just this column with the qty-weighted
	// ratio: total rejected / total handled, where handled is production
	// (finished) + rejected, matching how each row's own Rej % is computed
	// in daily_production_report.py.
	get_datatable_options(datatable_options) {
		const rows = datatable_options.data || [];
		const default_total = (datatable_options.hooks && datatable_options.hooks.columnTotal) || frappe.utils.report_column_total;

		datatable_options.hooks = datatable_options.hooks || {};
		datatable_options.hooks.columnTotal = function (values, column, type) {
			if (column.column.fieldname === "rej_") {
				let total_rejected = 0;
				let total_handled = 0;
				rows.forEach((row) => {
					total_rejected += flt(row.qty_rejected);
					total_handled += flt(row.production_quantity) + flt(row.qty_rejected);
				});
				return total_handled ? (total_rejected / total_handled) * 100 : 0;
			}
			return default_total(values, column, type);
		};

		return datatable_options;
	},
};
