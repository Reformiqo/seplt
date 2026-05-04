frappe.ui.form.on("PMC", {
    product_name: function (frm) {
        if (!frm.doc.product_name) return;
        frappe.call({
            method: "seplt.api.get_item_details",
            args: {
                item: frm.doc.product_name,
            },
            callback: function (r) {
                if (!r.message) return;
                const fields = [
                    "tube_dia",
                    "wall_thickness",
                    "body_length",
                    "nozzle_type",
                    "nozzle_length",
                    "nozzle_dia",
                    "orifice_dia",
                    "collapsibility",
                    "shoulder_thickness",
                    "lacquer_porosity",
                    "knurling_dia",
                    "thread_height",
                ];
                fields.forEach(function (f) {
                    frm.set_value(f, r.message[f]);
                });
                frm.refresh_fields();
            },
        });
    },
});

function bind_supplier_options(child_doctype, grid_fieldname) {
    frappe.ui.form.on(child_doctype, {
        raw_material_name: function (frm, cdt, cdn) {
            const d = locals[cdt][cdn];
            if (!d.raw_material_name) return;
            frappe.call({
                method: "seplt.api.get_item_suppliers",
                args: {
                    item_code: d.raw_material_name,
                },
                callback: function (r) {
                    if (!r.message) return;
                    frm.fields_dict[grid_fieldname].grid.update_docfield_property(
                        "supplier_name",
                        "options",
                        ["", ...r.message]
                    );
                },
            });
        },
    });
}

bind_supplier_options("Aluminium Slug", "aluminium_slug");
bind_supplier_options("Lacquer Requirement", "lacquer_requirement");
bind_supplier_options("Coating Requirement", "coating_requirement");
bind_supplier_options("Printing Requirement ", "printing_requirement");
bind_supplier_options("Latex Requirement", "latex_requirement");
bind_supplier_options("Cap Requirement", "cap_requirement");
bind_supplier_options("Packaging Requirement", "packaging_requirement");
bind_supplier_options("Outer Packaging Requirement", "outer_packaging_requirement");
