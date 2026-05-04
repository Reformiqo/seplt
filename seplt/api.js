frappe.ui.form.on("Purchase Receipt", {
    refresh: function (frm) {
        if (frm.doc.__islocal && frm.doc.subcontracting_receipt) {
            frappe.call({
                method: "seplt.api.get_transporter",
                args: {
                    doc: frm.doc.subcontracting_receipt,
                },
                callback: function (r) {
                    if (!r.message) return;
                    frm.set_value("custom_supplier_invoice_no", r.message.invoice_no);
                    frm.set_value("custom_supplier_invoice_date", r.message.invoice_date);
                    frm.set_value("custom_challan_no", r.message.challan_no);
                    frm.set_value("custom_challan_date", r.message.challan_date);
                },
            });
        }
    },
});
