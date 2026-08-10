frappe.ui.form.on("Subcontracting Inward Order", {
	refresh(frm) {
		frm.remove_custom_button(__("Material from Customer"), __("Receive"));
	},
});
