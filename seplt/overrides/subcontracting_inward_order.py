def set_received_qty_on_submit(doc, method=None):
	"""Raw material arrives via standalone Stock Entries, so mark the full
	required qty as received on submit. This drives the standard status
	(Ongoing) and enables the Create / Return buttons."""
	for item in doc.received_items:
		if item.is_customer_provided_item:
			item.db_set("received_qty", item.required_qty, update_modified=False)

	doc.update_status()
