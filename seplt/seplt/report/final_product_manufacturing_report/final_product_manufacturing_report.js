// Copyright (c) 2026, Erpera and contributors
// For license information, please see license.txt

frappe.query_reports["Final Product Manufacturing Report"] = {
	"filters": [
		{
			"fieldname": "production_plan",
			"label": __("Production Plan"),
			"fieldtype": "Link",
			"options": "Production Plan",
			"reqd": 1
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today()
		},
		{
			"fieldname": "fg_item",
			"label": __("Finished Item Code"),
			"fieldtype": "MultiSelectList",
			"get_data": function (txt) {
				return frappe.db.get_link_options("Item", txt, { is_stock_item: 1 });
			}
		},
		{
			"fieldname": "item_group",
			"label": __("Item Group"),
			"fieldtype": "Link",
			"options": "Item Group"
		},
		{
			"fieldname": "warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse"
		},
		{
			"fieldname": "wo_status",
			"label": __("Work Order Status"),
			"fieldtype": "Select",
			"options": "\nDraft\nNot Started\nIn Process\nCompleted\nStopped\nClosed\nCancelled"
		},
		{
			"fieldname": "show_zero_qty",
			"label": __("Show Zero Qty Rows"),
			"fieldtype": "Check",
			"default": 1
		}
	],

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (data && data.is_group) {
			value = `<span style="font-weight:bold;">${value}</span>`;
		}

		if (column.fieldname === "scrap_pct" && data && !data.is_group) {
			let pct = parseFloat(data.scrap_pct);
			if (!isNaN(pct) && pct > 5) {
				value = `<span style="color:#c0392b; font-weight:bold;">${value}</span>`;
			}
		}

		if (column.fieldname === "pending_qty" && data && !data.is_group) {
			let pending = parseFloat(data.pending_qty);
			if (!isNaN(pending) && pending < 0) {
				value = `<span style="color:#e67e22; font-weight:bold;">${value}</span>`;
			}
		}

		if (data && data.wo_status === "Completed" && data.pending_qty > 0 && column.fieldname === "wo_status") {
			value = `<span style="color:#c0392b; font-weight:bold;" title="Discrepancy: Completed with Pending Qty">${value} ⚠</span>`;
		}

		return value;
	}
};
