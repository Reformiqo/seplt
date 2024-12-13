frappe.ui.form.on("PMC", {
	// refresh(frm) {

	// },
    // sales_order: function(frm) {
    //     console.log("sales_order");
    //     frappe.call({
    //         method: 'Seplt.api.get_sales_order_items',
    //         args: {
    //             sales_order: frm.doc.sales_order
    //         },
    //         callback: function(r) {
    //             if (r.message) {
    //                 var itemShow = [];
    //                 for (var i = 0; i < r.message.length; i++) {
    //                     itemShow.push(r.message[i]);
    //                 }
    //                 frm.set_df_property('product_name', 'options', ["", ...itemShow]);
    //                 console.log(itemShow);
    //             }
    //         }
    //     });
    // },
    product_name: function(frm) {
        console.log("product_name");
        frappe.call({

            method: 'Seplt.api.get_item_details',
            args: {
                item: frm.doc.product_name
            },
            callback: function(r) {
                console.log(r.message);
                if (r.message) {
                    frm.set_value('tube_dia', r.message.tube_dia);
                    frm.set_value('wall_thickness', r.message.wall_thickness);
                    frm.set_value('body_length', r.message.body_length);
                    frm.set_value('nozzle_type', r.message.nozzle_type);
                    frm.set_value('nozzle_length', r.message.nozzle_length);
                    frm.set_value('nozzle_dia', r.message.nozzle_dia);
                    frm.set_value('orifice_dia', r.message.orifice_dia);
                    frm.set_value('collapsibility', r.message.collapsibility);
                    frm.set_value('shoulder_thickness', r.message.shoulder_thickness);
                    frm.set_value('lacquer_porosity', r.message.lacquer_porosity);
                    frm.set_value('custom_knurling_dia', r.message.custom_knurling_dia);
                    frm.set_value('custom_thread_height', r.message.custom_thread_height);

                    // refreshfields
                    frm.refresh_fields();

                }
            }
        });
    }
});

frappe.ui.form.on("Aluminium Slug", {
    raw_material_name: function(frm, cdt, cdn) {
        console.log("raw_material_name");
        var d = locals[cdt][cdn];
        frappe.call({
            method: 'Seplt.api.get_item_suppliers',
            args: {
                item_code: d.raw_material_name
            },
            callback: function(r) {
                if (r.message) {
                    var itemShow = [];
                    for (var i = 0; i < r.message.length; i++) {
                        itemShow.push(r.message[i]);
                    }
                    frm.fields_dict['aluminium_slug'].grid.update_docfield_property('supplier_name', 'options', ["", ...itemShow]);
                    console.log(itemShow);
                }
            }
        });
    }
});

frappe.ui.form.on("Lacquer Requirement", {
    raw_material_name: function(frm, cdt, cdn) {
        console.log("raw_material_name");
        var d = locals[cdt][cdn];
        frappe.call({
            method: 'Seplt.api.get_item_suppliers',
            args: {
                item_code: d.raw_material_name
            },
            callback: function(r) {
                if (r.message) {
                    var itemShow = [];
                    for (var i = 0; i < r.message.length; i++) {
                        itemShow.push(r.message[i]);
                    }
                    frm.fields_dict['lacquer_requirement'].grid.update_docfield_property('supplier_name', 'options', ["", ...itemShow]);
                    console.log(itemShow);
                }
            }
        });
    }
});

frappe.ui.form.on("Coating Requirement", {
    raw_material_name: function(frm, cdt, cdn) {
        console.log("raw_material_name");
        var d = locals[cdt][cdn];
        frappe.call({
            method: 'Seplt.api.get_item_suppliers',
            args: {
                item_code: d.raw_material_name
            },
            callback: function(r) {
                if (r.message) {
                    var itemShow = [];
                    for (var i = 0; i < r.message.length; i++) {
                        itemShow.push(r.message[i]);
                    }
                    frm.fields_dict['coating_requirement'].grid.update_docfield_property('supplier_name', 'options', ["", ...itemShow]);
                    console.log(itemShow);
                }
            }
        });
    }
});

frappe.ui.form.on("Printing Requirement ", {
    raw_material_name: function(frm, cdt, cdn) {
        console.log("raw_material_name");
        var d = locals[cdt][cdn];
        frappe.call({
            method: 'Seplt.api.get_item_suppliers',
            args: {
                item_code: d.raw_material_name
            },
            callback: function(r) {
                if (r.message) {
                    var itemShow = [];
                    for (var i = 0; i < r.message.length; i++) {
                        itemShow.push(r.message[i]);
                    }
                    frm.fields_dict['printing_requirement'].grid.update_docfield_property('supplier_name', 'options', ["", ...itemShow]);
                    console.log(itemShow);
                }
            }
        });
    }
});

frappe.ui.form.on("Latex Requirement", {
    raw_material_name: function(frm, cdt, cdn) {
        console.log("raw_material_name");
        var d = locals[cdt][cdn];
        frappe.call({
            method: 'Seplt.api.get_item_suppliers',
            args: {
                item_code: d.raw_material_name
            },
            callback: function(r) {
                if (r.message) {
                    var itemShow = [];
                    for (var i = 0; i < r.message.length; i++) {
                        itemShow.push(r.message[i]);
                    }
                    frm.fields_dict['latex_requirement'].grid.update_docfield_property('supplier_name', 'options', ["", ...itemShow]);
                    console.log(itemShow);
                }
            }
        });
    }
});

frappe.ui.form.on("Cap Requirement", {
    raw_material_name: function(frm, cdt, cdn) {
        console.log("raw_material_name");
        var d = locals[cdt][cdn];
        frappe.call({
            method: 'Seplt.api.get_item_suppliers',
            args: {
                item_code: d.raw_material_name
            },
            callback: function(r) {
                if (r.message) {
                    var itemShow = [];
                    for (var i = 0; i < r.message.length; i++) {
                        itemShow.push(r.message[i]);
                    }
                    frm.fields_dict['cap_requirement'].grid.update_docfield_property('supplier_name', 'options', ["", ...itemShow]);
                    console.log(itemShow);
                }
            }
        });
    }
});

frappe.ui.form.on("Packaging Requirement", {
    raw_material_name: function(frm, cdt, cdn) {
        console.log("raw_material_name");
        var d = locals[cdt][cdn];
        frappe.call({
            method: 'Seplt.api.get_item_suppliers',
            args: {
                item_code: d.raw_material_name
            },
            callback: function(r) {
                if (r.message) {
                    var itemShow = [];
                    for (var i = 0; i < r.message.length; i++) {
                        itemShow.push(r.message[i]);
                    }
                    frm.fields_dict['packaging_requirement'].grid.update_docfield_property('supplier_name', 'options', ["", ...itemShow]);
                    console.log(itemShow);
                }
            }
        });
    }
});

frappe.ui.form.on("Outer Packaging Requirement", {
    raw_material_name: function(frm, cdt, cdn) {
        console.log("raw_material_name");
        var d = locals[cdt][cdn];
        frappe.call({
            method: 'Seplt.api.get_item_suppliers',
            args: {
                item_code: d.raw_material_name
            },
            callback: function(r) {
                if (r.message) {
                    var itemShow = [];
                    for (var i = 0; i < r.message.length; i++) {
                        itemShow.push(r.message[i]);
                    }
                    frm.fields_dict['outer_packaging_requirement'].grid.update_docfield_property('supplier_name', 'options', ["", ...itemShow]);
                    console.log(itemShow);
                }
            }
        });
    }
});
