frappe.ui.form.on("Production Plan", {
	// ERPNext sets this picker in its own "setup_queries" handler, which it
	// triggers from setup. This handler runs after ERPNext's, so the query below
	// replaces ERPNext's: same filters, minus the fully delivered Sales Orders
	// (SO1-I150 -- see seplt/overrides/production_plan.py).
	setup_queries(frm) {
		frm.set_query("sales_order", "sales_orders", () => {
			return {
				query: "seplt.overrides.production_plan.sales_order_query",
				filters: {
					company: frm.doc.company,
					item_code: frm.doc.item_code,
				},
			};
		});
	},
});
