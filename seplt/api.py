import frappe
from frappe.utils import flt, cint


@frappe.whitelist()
def check_production_qc(work_order_id):
    work_order = frappe.get_doc("Work Order", work_order_id)
    item = work_order.production_item
    pc = frappe.get_all(
        "Production QC",
        {"reference_name": work_order_id, "item_code": item, "docstatus": 1},
    )

    if not pc:
        frappe.throw("Production QC not created or submitted")

    return {"status": "success"}


@frappe.whitelist()
def get_work_order_item(work_order_id):
    work_order = frappe.get_doc("Work Order", work_order_id)
    return work_order.production_item


@frappe.whitelist()
def get_item_details(item):
    item_doc = frappe.get_doc("Item", item)
    return {
        "tube_dia": item_doc.custom_tube_dia,
        "wall_thickness": item_doc.custom_wall_thickness,
        "body_length": item_doc.custom_body_length,
        "nozzle_type": item_doc.custom_nozzle_type,
        "nozzle_length": item_doc.custom_nozzle_length,
        "nozzle_dia": item_doc.custom_nozzle_dia,
        "orifice_dia": item_doc.custom_orifice_dia,
        "collapsibility": item_doc.custom_collapsibility,
        "shoulder_thickness": item_doc.custom_shoulder_thickness,
        "lacquer_porosity": item_doc.custom_lacquer_porosity,
        "knurling_dia": item_doc.custom_knurling_dia,
        "thread_height": item_doc.custom_thread_height,
    }


@frappe.whitelist()
def get_so_item(item, so):
    so = frappe.get_doc("Sales Order", so)
    for i in so.items:
        if i.item_code == item:
            return i.qty
    return None


@frappe.whitelist()
def get_item_tube(item):
    return frappe.db.get_value("Item", item, "custom_tube_dia")


@frappe.whitelist()
def get_sales_order_items(sales_order):
    return [
        row.item_code
        for row in frappe.get_all(
            "Sales Order Item",
            filters={"parent": sales_order},
            fields=["item_code"],
        )
    ]


@frappe.whitelist()
def get_total_po_quantity(supplier, item):
    return frappe.db.sql(
        """
        SELECT SUM(qty)
        FROM `tabPurchase Order Item`
        WHERE item_code = %s
          AND parent IN (
              SELECT name FROM `tabPurchase Order` WHERE supplier = %s
          )
        """,
        (item, supplier),
    )


@frappe.whitelist()
def update_item_price(supplier, price_list, amount, valid_from):
    items = get_supplier_items(supplier, price_list)
    updated = []
    for item in items:
        price = frappe.db.get_value(
            "Item Price",
            {"item_code": item, "price_list": price_list},
            "price_list_rate",
        )
        if price:
            new_value = flt(price) + flt(amount)
            frappe.db.set_value(
                "Item Price",
                {"item_code": item, "price_list": price_list},
                {"price_list_rate": new_value, "valid_from": valid_from},
            )
            updated.append({"item_code": item, "price_list_rate": new_value})
    return updated


@frappe.whitelist()
def get_supplier_items(supplier, price_list):
    items = frappe.get_all(
        "Item Price",
        filters={"price_list": price_list},
        fields=["item_code"],
    )
    if not items:
        return []

    item_codes = [i.item_code for i in items]
    defaults = frappe.get_all(
        "Item Default",
        filters={"parent": ["in", item_codes], "default_supplier": supplier},
        fields=["parent"],
    )
    return [d.parent for d in defaults]


@frappe.whitelist()
def get_suppliers(item_code):
    item = frappe.get_doc("Item", item_code)
    suppliers = []
    for d in item.get("item_defaults") or []:
        if d.default_supplier:
            suppliers.append(d.default_supplier)
    return suppliers


def create_checklist_transaction(doc, method=None):
    for item in doc.items:
        item_checklist = frappe.db.get_value("Item", item.item_code, "custom_checklist")
        if not item_checklist:
            frappe.throw(
                f"No checklist found for Item {item.item_code}, please set a checklist for this Item"
            )

        checklist = frappe.new_doc("Checklist Transaction")
        checklist.total_qty = item.qty
        if doc.doctype == "Purchase Receipt":
            checklist.supplier_or_customer = frappe.db.get_value(
                "Supplier", doc.supplier, "supplier_name"
            )
            checklist.purchase_date = doc.posting_date
            checklist.lot_no = item.lot_no
            checklist.box_no = item.custom_box_no
            checklist.transaction_type = "Inward"
        elif doc.doctype == "Delivery Note":
            checklist.transaction_type = "Outward"
            checklist.supplier_or_customer = frappe.db.get_value(
                "Customer", doc.customer, "customer_name"
            )
        elif doc.doctype == "Subcontracting Receipt":
            checklist.supplier_or_customer = frappe.db.get_value(
                "Supplier", doc.supplier, "supplier_name"
            )
            checklist.transaction_type = "Subcontracting"
            checklist.purchase_date = doc.posting_date
            checklist.total_qty = item.custom_actual_consumed_qty

        checklist.product = item.item_code
        checklist.custom_batch_no = item.batch_no
        checklist.grb_nomrn_no_date = doc.name
        checklist.reference = doc.doctype

        item_group = frappe.db.get_value("Item", item.item_code, "item_group")

        for ch in get_item_checklist(item.item_code):
            if item_checklist in ("Raw Material", "Packing Material"):
                if doc.doctype == "Purchase Receipt" and ch.parameters == "Source & Grade":
                    ch.specification = item.item_name
                if doc.doctype == "Purchase Receipt" and ch.parameters == "Received Lot No.":
                    ch.observation = item.lot_no
                if ch.parameters == "Material":
                    ch.specification = item_group

            if ch.parameters == "Received Lot No.":
                checklist.received_lot_no = ch.observation
            elif ch.parameters == "Received Bags/ Cans (in No)":
                checklist.received_bags = ch.observation
            else:
                checklist.append(
                    "checklist",
                    {
                        "parameters": ch.parameters,
                        "specification": ch.specification,
                        "observation": ch.observation,
                    },
                )

        checklist.save()
        if doc.doctype == "Purchase Receipt":
            frappe.db.set_value(
                "Checklist Transaction",
                checklist.name,
                "custom_batch_no",
                item.custom_supplier_batch_no,
            )


@frappe.whitelist()
def get_item_checklist(item_code):
    data = []
    item_checklist = frappe.db.get_value("Item", item_code, "custom_checklist")
    if not item_checklist:
        return data
    checklist = frappe.get_doc("Checklist", item_checklist)
    for ch in checklist.checklist:
        data.append(
            frappe._dict(
                {
                    "parameters": ch.parameters,
                    "specification": ch.specification,
                    "observation": ch.observation,
                }
            )
        )
    return data


@frappe.whitelist()
def get_item_suppliers(item_code):
    item = frappe.get_doc("Item", item_code)
    if item.get("supplier_items"):
        return [i.supplier for i in item.supplier_items]
    return [s.name for s in frappe.get_list("Supplier", fields=["name"])]


def set_si_qrcode(doc, method=None):
    """Generate a QR code for the given doc and attach it via Frappe's file API."""
    import segno
    import io

    qr_payload = doc.name
    img = segno.make_qr(qr_payload)

    buffer = io.BytesIO()
    img.save(buffer, kind="png", scale=15)
    buffer.seek(0)

    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": f"{doc.name}.png",
            "is_private": 0,
            "content": buffer.getvalue(),
            "attached_to_doctype": doc.doctype,
            "attached_to_name": doc.name,
        }
    )
    file_doc.insert(ignore_permissions=True)

    doc.db_set("custom_qr_image", file_doc.file_url)
    return file_doc.file_url


def set_supplier_batch_no(doc, method=None):
    if not doc.reference_name:
        return
    ref_doc = frappe.get_doc("Purchase Receipt", doc.reference_name)
    for item in ref_doc.items:
        if item.item_code == doc.item:
            doc.db_set("custom_supplier_batch_no", item.custom_supplier_batch_no)
            doc.db_set("custom_box_no", item.custom_box_no)
            break


@frappe.whitelist()
def get_sales_orders():
    sales_orders = frappe.get_all("Sales Order", fields=["name", "customer", "delivery_date", "transaction_date"])
    data = []
    for so in sales_orders:
        items = frappe.get_all(
            "Sales Order Item",
            filters={"parent": so.name},
            fields=["item_code"],
        )
        for idx, item in enumerate(items):
            data.append(
                {
                    "so_name": so.name,
                    "customer": so.customer if idx == 0 else "",
                    "product_code": item.item_code,
                    "delivery_date": so.delivery_date,
                    "po_date": so.transaction_date,
                    "tube_size": frappe.db.get_value("Item", item.item_code, "custom_tube_dia"),
                    "lac_un": frappe.db.get_value("Item", item.item_code, "custom_lacquer_porosity"),
                    "slug": "sample-slug",
                }
            )
    return data


@frappe.whitelist()
def get_so_items(so_name):
    return frappe.db.sql(
        "SELECT item_code, qty, rate, amount FROM `tabSales Order Item` WHERE parent = %s",
        (so_name,),
    )


@frappe.whitelist()
def add_days(date, days):
    return frappe.utils.add_days(date, cint(days))


@frappe.whitelist()
def get_total_qty(item_code):
    qty = frappe.db.sql(
        """
        SELECT SUM(sed.qty)
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE sed.item_code = %s
          AND se.stock_entry_type = 'Material Transfer for Manufacture'
        """,
        (item_code,),
    )
    return qty[0][0] if qty and qty[0][0] is not None else 0


@frappe.whitelist()
def get_transporter(doc):
    transporter = frappe.db.sql(
        """
        SELECT custom_transporter, custom_transporter_name, custom_vehicle_no,
               custom_transport_receipt_no, custom_transport_receipt_date,
               custom_distance_in_km, custom_mode_of_transport, custom_gst_vehicle_type
        FROM `tabPurchase Order`
        WHERE name = %s
        """,
        (doc,),
    )

    if not transporter:
        return {}

    row = transporter[0]
    return {
        "transporter": row[0],
        "transporter_name": row[1],
        "vehicle_no": row[2],
        "transport_receipt_no": row[3],
        "transport_receipt_date": row[4],
        "distance_in_km": row[5],
        "mode_of_transport": row[6],
        "gst_vehicle_type": row[7],
    }


def after_insert(doc, method=None):
    create_checklist_transaction(doc)


def on_submit(doc, method=None):
    # Hook reserved for Purchase Receipt submission checks.
    pass


def validate(doc, method=None):
    if doc.doctype == "Subcontracting Receipt":
        set_document_reference(doc)


@frappe.whitelist()
def reset_password(email):
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Not permitted", frappe.PermissionError)
    user = frappe.get_doc("User", email)
    return user.reset_password(send_email=True, password_expired=True)


def set_document_reference(doc, method=None):
    if not doc.get("custom_document_reference"):
        return
    doc.doc_references = []
    for ref in doc.custom_document_reference:
        doc.append(
            "doc_references",
            {"link_doctype": ref.link_doctype, "link_name": ref.link_name},
        )


@frappe.whitelist()
def submit_scr(doc):
    frappe.has_permission("Subcontracting Receipt", "submit", doc=doc, throw=True)
    scr = frappe.get_doc("Subcontracting Receipt", doc)
    scr.submit()
    return "success"


@frappe.whitelist()
def submit_scr_v2(doc):
    frappe.has_permission("Subcontracting Receipt", "submit", doc=doc, throw=True)
    try:
        scr = frappe.get_doc("Subcontracting Receipt", doc)
        scr.submit()
        return {"status": "success"}
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Error submitting Subcontracting Receipt {doc}",
        )
        return {"status": "error", "message": "Failed to submit Subcontracting Receipt"}


@frappe.whitelist()
def get_receipt_details(doc):
    doc = frappe.get_doc("Subcontracting Receipt", doc)
    return {
        "lot_no": doc.custom_lot_no,
        "challan_no": doc.custom_challan_no,
        "challan_date": doc.custom_challan_date,
        "invoice_no": doc.custom_invoice_no,
        "invoice_date": doc.custom_invoice_date,
    }
