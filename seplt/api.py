import frappe
from frappe.utils import flt
from frappe import _
from frappe.utils import today, getdate
from frappe.utils import cint


@frappe.whitelist()
def check_production_qc(work_order_id):
    # Fetch Production QC records with the given work_order_id that are submitted
    work_order = frappe.get_doc("Work Order", work_order_id)
    item = work_order.production_item
    pc = frappe.get_all("Production QC", {"reference_name": work_order_id, "item_code": item, "docstatus": 1}) 
    
    # If no Production QC is found, throw an error
    if not pc:
        frappe.throw("Production QC not created or submitted")
    
    # Return success if Production QC is found
    return {"status": "success"}

@frappe.whitelist()
def get_work_order_item(work_order_id):
    # Fetch the work order item
    work_order = frappe.get_doc("Work Order", work_order_id)
    return work_order.production_item
# in pmc if item is set ge thte tiem detail
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
    so = frappe.get_doc("Sales Order", sales_order)
    data = []
    for item in so.items:
        data.append(item.item_code)
    return data

@frappe.whitelist()
def get_total_po_quantity(supplier, item):
    po_qty = frappe.db.sql(f"SELECT SUM(qty) FROM `tabPurchase Order Item` WHERE item_code='{item}' AND parent IN (SELECT name FROM `tabPurchase Order` WHERE supplier='{supplier}')")
    return po_qty

@frappe.whitelist()
def update_item_price(supplier, price_list, amount, valid_from):
    items = get_supplier_items(supplier, price_list)
    prices = [] 
    for item in items:
        price = frappe.db.get_value("Item Price", {"item_code": item, "price_list": price_list}, "price_list_rate")
        if price:
            value = flt(price) + flt(amount)
            frappe.db.set_value("Item Price", {"item_code": item, "price_list": price_list}, "price_list_rate", value)
            frappe.db.set_value("Item Price", {"item_code": item, "price_list": price_list}, "valid_from", valid_from)
            frappe.db.commit()
    return prices
@frappe.whitelist()
def get_supplier_items(supplier, price_list):
    items = frappe.get_all("Item Price", filters={"price_list": price_list}, fields=["item_code"])
    item_list = []

    for item in items:
        suppliers = get_suppliers(item.item_code)
        if supplier in suppliers:
            item_list.append(item.item_code)
        
    return item_list

@frappe.whitelist()
def get_suppliers(item_code):
    item = frappe.get_doc("Item", item_code)
    defaults =item.get('item_defaults')
    suppliers = []
    if defaults:
        for d in defaults:
            if d.default_supplier:
                suppliers.append(d.default_supplier)
    return suppliers

@frappe.whitelist()
def create_checklist_transaction(doc, method=None):
    # Create a new Checklist Transaction document    
    for item in doc.items:
        item_checlist = frappe.db.get_value("Item", item.item_code, "custom_checklist")
        if not item_checlist:
            frappe.throw(f"No checklist found for Item {item.item_code}, please set a checklist for this Item")
        else:
            checklist = frappe.new_doc("Checklist Transaction")
            checklist.total_qty = item.qty
            if doc.doctype == "Purchase Receipt":
                checklist.supplier_or_customer = frappe.db.get_value("Supplier", doc.supplier, "supplier_name")
                checklist.purchase_date = doc.posting_date
                checklist.lot_no = item.lot_no
                checklist.box_no = item.custom_box_no
                checklist.transaction_type = "Inward"
            elif doc.doctype == "Delivery Note":
                checklist.transaction_type = "Outward"
                checklist.supplier_or_customer = frappe.db.get_value("Customer", doc.customer, "customer_name")
            elif doc.doctype == "Subcontracting Receipt":
                checklist.supplier_or_customer = frappe.db.get_value("Supplier", doc.supplier, "supplier_name")
                checklist.transaction_type = "Subcontracting"
                checklist.purchase_date = doc.posting_date
                checklist.total_qty = item.custom_actual_consumed_qty

            checklist.product = item.item_code
            checklist.custom_batch_no = item.batch_no
            
            
            checklist.grb_nomrn_no_date = doc.name
            #the reference will be what type of document is being referred to, eg sales invoice or delivery note etc
            checklist.reference = doc.doctype
            item_group = frappe.db.get_value("Item", item.item_code, "item_group")

            for ch in get_item_checklist(item.item_code):

                if item_checlist == "Raw Material" or item_checlist == "Packing Material":
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
                    checklist.append("checklist", {
                        "parameters": ch.parameters,
                        "specification": ch.specification,
                        "observation": ch.observation
                    })
                
            checklist.save()
            if doc.doctype == "Purchase Receipt":
                frappe.db.set_value("Checklist Transaction", checklist.name, "custom_batch_no", item.custom_supplier_batch_no)
            frappe.db.commit()
    
@frappe.whitelist()
def get_item_checklist(item_code):
    data = []
    item_checlist = frappe.db.get_value("Item", item_code, "custom_checklist")
    checklist = frappe.get_doc("Checklist", item_checlist)
    for ch in checklist.checklist:
        data.append(frappe._dict({
            "parameters": ch.parameters,
            "specification": ch.specification,
            "observation": ch.observation
        }))
    return data
@frappe.whitelist()
def check_if_checklist_exists(doc, method=None):
    pass
    # Check if a checklist transaction already exists for this document and make all checklist transactions are submitted before the document is submitted
    # docs = frappe.get_list("Checklist Transaction", filters={"grb_nomrn_no_date": doc.name, "reference": doc.doctype}, fields=["name", "docstatus"])
    # if docs:
    #     for d in docs:
    #         if d.docstatus == 0:
    #             frappe.throw("Please submit all checklist transactions before submitting this document")

@frappe.whitelist()
def get_item_suppliers(item_code):
    item = frappe.get_doc("Item", item_code)
    data = []
    if item.get('supplier_items'):
        for i in item.supplier_items:
            data.append(i.supplier)
    else:
       suppliers = frappe.get_list("Supplier", fields=["name"])
       for s in suppliers:
              data.append(s.name)
    return data

@frappe.whitelist()
def set_si_qrcode(doc, method=None):
    import segno
    img = segno.make_qr("Hello, World")
    
    # Define the file path
    file_path = f"/home/frappe/frappe-bench/sites/sona.erpera.io/public/files/{doc.name}.png"
    
    # Save the image to the file
    img.save(file_path, scale=15)  

    # Read the image file from the system
    with open(file_path, "rb") as file:
        file_content = file.read()


    # Create a new file document in Frappe
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": f"{doc.name}.png",
        "is_private": 0,  # 0 for public, 1 for private
        "content": file_content,
        
    })

    file_doc.insert()
    doc.custom_qr_image = file_doc.file_url
    doc.save()
    frappe.db.commit()
    return file_doc.file_url

@frappe.whitelist()
def set_supplier_batch_no(doc, method=None):
    # doc = frappe.get_doc("Purchase Receipt", "PR-24-00013")
    if doc.reference_name:
        ref_doc = frappe.get_doc("Purchase Receipt", doc.reference_name)
        for item in ref_doc.items:
            if item.item_code == doc.item:
                doc.custom_supplier_batch_no = item.custom_supplier_batch_no
                doc.custom_box_no = item.custom_box_no
                doc.save()
                frappe.db.commit()
                break
    
@frappe.whitelist()
def get_sales_orders():
    sales_orders = frappe.get_all("Sales Order")
    data = []
    customers = []
    for so in sales_orders:
        so_doc = frappe.get_doc("Sales Order", so.name)
        for item in so_doc.items:
            data.append({
                "so_name": so.name,
                "customer": so_doc.customer if so_doc.customer not in customers else "",
                "product_code": item.item_code,
                "delivery_date": so_doc.delivery_date,
                "po_date": so_doc.transaction_date,
                "tube_size": frappe.db.get_value("Item", item.item_code, "custom_tube_dia"),
                "lac_un": frappe.db.get_value("Item", item.item_code, "custom_lacquer_porosity"),
                "slug": "sample-slug"
            })
            customers.append(so_doc.customer) if so_doc.customer not in customers else ""
        # clear the customers list
        customers.clear()
    return data
@frappe.whitelist()
def get_so_items(so_name):
    items = frappe.db.sql(f"SELECT item_code, qty, rate, amount FROM `tabSales Order Item` WHERE parent='{so_name}'")
    return items

@frappe.whitelist()
def add_days(date, days):
    return frappe.utils.add_days(date, cint(days))

@frappe.whitelist()
def get_total_qty(item_code):
    qty = frappe.db.sql(f"""
        SELECT SUM(sed.qty)
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE sed.item_code = %s AND se.stock_entry_type = 'Material Transfer for Manufacture'
    """, (item_code,))
    
    return qty[0][0] if qty else 0

@frappe.whitelist()
def get_transporter(doc):
    transporter = frappe.db.sql(f"""
                          SELECT custom_transporter, custom_transporter_name, custom_vehicle_no, custom_transport_receipt_no,  custom_transport_receipt_date,
                                custom_distance_in_km, custom_mode_of_transport, custom_gst_vehicle_type
                                FROM `tabPurchase Order` WHERE name = '{doc}'
                          """)
    
    data = {
        "transporter": transporter[0][0],
        "transporter_name": transporter[0][1],
        "vehicle_no": transporter[0][2],
        "transport_receipt_no": transporter[0][3],
        "transport_receipt_date": transporter[0][4],
        "distance_in_km": transporter[0][5],
        "mode_of_transport": transporter[0][6],
        "gst_vehicle_type": transporter[0][7]
        


    }
    return data

# @frappe.whitelist()
# def create_batch_on_submit(doc, method=None):
#     for item in doc.items:
#         if not frappe.db.exists("Batch", item.custom_supplier_batch_no):
#             batch = frappe.new_doc("Batch")
#             batch.batch_id = item.custom_supplier_batch_no
#             batch.batch_no = item.custom_supplier_batch_no
#             batch.item = item.item_code
#             batch.manufacturing_date = doc.posting_date
#             batch.custom_supplier_batch_no = item.custom_supplier_batch_no
#             batch.custom_box_no = item.custom_box_no
#             batch.custom_lot_no = item.lot_no
#             batch.batch_qty = item.qty
#             batch.save()
#             frappe.db.commit()

@frappe.whitelist()
def after_insert(doc, method=None):
    # if doc.doctype == "Purchase Receipt":
    #     create_batch_on_submit(doc)
    create_checklist_transaction(doc)
@frappe.whitelist()
def on_submit(doc, method=None):
    if doc.doctype == "Purchase Receipt":
        check_if_checklist_exists(doc)

@frappe.whitelist()
def validate(doc, method=None):
    if doc.doctype == "Subcontracting Receipt":
        update_consumed_qty(doc)
        set_document_reference(doc)
    
@frappe.whitelist()
def update_consumed_qty(doc, method=None):
    data = []
    if doc.supplied_items:
        for i in doc.custom_actual_consumed_items:
            data.append(i.item)
        for item in doc.supplied_items:
            if item.main_item_code not in data:
                doc.append("custom_actual_consumed_items", {
                    "item": item.main_item_code,
                    "actual_consumed_qty": round(item.consumed_qty, 3)
                })
        frappe.db.commit()
    
        for i in doc.custom_actual_consumed_items:
            for item in doc.supplied_items:
                if i.item == item.main_item_code:
                    item.consumed_qty = i.actual_consumed_qty
                    break
    frappe.db.commit()
@frappe.whitelist()
def reset_password(email):
    user = frappe.get_doc('User', email)
    return user.reset_password(send_email=True, password_expired=True)

@frappe.whitelist()
def set_document_reference(doc, method=None):
    if doc.custom_document_reference:
        doc.doc_references = []
        for ref in doc.custom_document_reference:
            doc.append("doc_references", {
                "link_doctype": ref.link_doctype,
                "link_name": ref.link_name
        })
        frappe.db.commit()
        
@frappe.whitelist()
def submit_scr(doc):
    doc = frappe.get_doc("Subcontracting Receipt", doc)
    doc.submit()
    frappe.db.commit()
    return "success"
@frappe.whitelist()
def submit_scr_v2(doc):
    try:
        doc = frappe.get_doc("Subcontracting Receipt", doc)
        doc.submit()
        frappe.db.commit()
        return "success"
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Error submitting Subcontracting Receipt {doc}")

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