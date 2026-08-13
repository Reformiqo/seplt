const CUSTOMER_OWNED_PURPOSES = ['Receive from Customer', 'Subcontracting Delivery'];

frappe.ui.form.on('Stock Entry', {
	refresh(frm) {
		frm.set_query('stock_entry_type', function() {
            return {}; // no filters, shows all
        });
		frm.trigger('unlock_basic_rate_for_customer_owned_stock');
	},

	stock_entry_type(frm) {
		frm.trigger('unlock_basic_rate_for_customer_owned_stock');
	},

	// Core locks Basic Rate for every purpose but "Material Receipt". On these two the rate
	// has to be typed in, and neither can reach the ledger:
	//
	//   Receive from Customer  — incoming; seplt.overrides.stock_entry zeroes valuation_rate,
	//                            and the rate is kept as Customer Provided Item Cost.
	//   Subcontracting Delivery — outgoing; ERPNext values outgoing stock from the warehouse,
	//                            not from the row (get_sle_for_source_warehouse passes
	//                            incoming_rate 0), so the rate is display only.
	//
	// Only ever unlocks — core re-locks the field itself on any switch to another purpose.
	unlock_basic_rate_for_customer_owned_stock(frm) {
		if (!CUSTOMER_OWNED_PURPOSES.includes(frm.doc.purpose)) {
			return;
		}

		frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'read_only', 0);
	},
})
