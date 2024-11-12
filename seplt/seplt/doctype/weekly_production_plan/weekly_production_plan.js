// Copyright (c) 2024, Erpera and contributors
// For license information, please see license.txt

frappe.ui.form.on("Weekly Production Plan", {
	// refresh(frm) {

	// },
    sales_order: function(frm) {
            frappe.call({
                method: 'sona.api.get_sales_order_items',
                args: {
                    sales_order: frm.doc.sales_order
                },
                callback: function(r) {
                    if (r.message) {
                        
                        frm.set_query('item_name', function() {
                            return {
                                filters: [
                                    ["Item", "name", "in", r.message]
                                ]
                            }
                        });
                        
                    }
                }
            });
        
        
        
    },
    item_name: function(frm) {
        frappe.call({
            method: 'sona.api.get_item_tube',
            args: {
                item: frm.doc.item_name
            },
            callback: function(r) {
                if (r.message) {
                    frm.set_value('tube', r.message);
                    frm.refresh_field('tube');
                }
            }
        });
        
        frm.set_value('tube', tube);
        frm.refresh_field('tube');
    },
});
