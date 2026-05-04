// Copyright (c) 2024, Erpera and contributors
// For license information, please see license.txt

frappe.ui.form.on("Weekly Production Plan", {
    sales_order: function (frm) {
        if (!frm.doc.sales_order) return;
        frappe.call({
            method: "seplt.api.get_sales_order_items",
            args: {
                sales_order: frm.doc.sales_order,
            },
            callback: function (r) {
                if (r.message) {
                    frm.set_query("item_name", function () {
                        return {
                            filters: [["Item", "name", "in", r.message]],
                        };
                    });
                }
            },
        });
    },
    item_name: function (frm) {
        if (!frm.doc.item_name) return;
        frappe.call({
            method: "seplt.api.get_item_tube",
            args: {
                item: frm.doc.item_name,
            },
            callback: function (r) {
                if (r.message) {
                    frm.set_value("tube", r.message);
                }
            },
        });
    },
});
