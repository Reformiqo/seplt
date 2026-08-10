// Copyright (c) 2026, Erpera and contributors
// For license information, please see license.txt

// Same filter set as the standard "Purchase Receipt Trends" report
// (erpnext/public/js/purchase_trends_filters.js), plus a switch to drop the
// subcontracting side so the output can be reconciled against that report.
// The filter dicts are copied rather than shared, so nothing the query report
// writes back onto them can leak into the standard report.
frappe.query_reports["Purchase Receipt Trends Including Subcontracting"] = {
	filters: ((erpnext.purchase_trends_filters || {}).filters || [])
		.map((f) => Object.assign({}, f))
		.concat([
			{
				fieldname: "include_subcontracting",
				label: __("Include Subcontracting Receipts"),
				fieldtype: "Check",
				default: 1,
			},
		]),
};
