
frappe.ui.form.on("Purchase Receipt", {
    refresh: function(frm) {
        // if the frm is new 
        if (frm.doc.__islocal && frm.doc.subcontracting_receipt) 
            {

    frappe.call({
        method: "seplt.api.get_transporter",
        args: {
            doc: rm.doc.subcontracting_receipt
        },
        callback: function(r) {
            console.log(r.message);
            // set the value of the field
            frm.set_value("custom_supplier_invoice_no", r.message.invoice_no);
            frm.set_value("custom_supplier_invoice_date", r.message.invoice_date);
            frm.set_value("custom_challan_no", r.message.challan_no);
            frm.set_value("custom_challan_date", r.message.challan_date);
        }
    });
        }
    }
    });
