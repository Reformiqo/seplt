// Copyright (c) 2026, Erpera and contributors
// For license information, please see license.txt

// Same filter set as the standard "Purchase Receipt Trends" report
// (erpnext/public/js/purchase_trends_filters.js), plus the two SO1-I134 FRD
// filters: Receipt Type (FR-02) to isolate either side for reconciliation,
// and Subcontracting Amount Basis (OP-01/FR-09) to choose which value a
// subcontracting row contributes. The filter dicts are copied rather than
// shared, so nothing the query report writes back onto them can leak into
// the standard report.
frappe.query_reports["Purchase Receipt Trends Including Subcontracting"] = {
	filters: ((erpnext.purchase_trends_filters || {}).filters || [])
		.map((f) => Object.assign({}, f))
		.concat([
			{
				fieldname: "receipt_type",
				label: __("Receipt Type"),
				fieldtype: "Select",
				options: ["All", "Purchase Receipt Only", "Subcontracting Receipt Only"],
				default: "All",
			},
			{
				fieldname: "sco_amount_basis",
				label: __("Subcontracting Amount Basis"),
				fieldtype: "Select",
				options: ["Job Work / Service Value", "Total Receipt Value"],
				default: "Job Work / Service Value",
				description: __("Ignored when Receipt Type is Purchase Receipt Only"),
			},
		]),
};
