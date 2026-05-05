# Copyright (c) 2026, Erpera and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "production_plan",
            "label": _("Production Plan ID"),
            "fieldtype": "Link",
            "options": "Production Plan",
            "width": 150,
        },
        {
            "fieldname": "plan_date",
            "label": _("Plan Date"),
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "fieldname": "fg_item_code",
            "label": _("Finished Item Code"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 160,
        },
        {
            "fieldname": "fg_item_name",
            "label": _("Finished Item Name"),
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "fieldname": "item_group",
            "label": _("Item Group"),
            "fieldtype": "Link",
            "options": "Item Group",
            "width": 130,
        },
        {
            "fieldname": "uom",
            "label": _("UOM"),
            "fieldtype": "Link",
            "options": "UOM",
            "width": 70,
        },
        {
            "fieldname": "work_order",
            "label": _("Work Order #"),
            "fieldtype": "Link",
            "options": "Work Order",
            "width": 150,
        },
        {
            "fieldname": "wo_status",
            "label": _("WO Status"),
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "fieldname": "planned_qty",
            "label": _("Planned Qty"),
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "fieldname": "manufactured_qty",
            "label": _("Manufactured Qty"),
            "fieldtype": "Float",
            "width": 130,
        },
        {
            "fieldname": "scrap_qty",
            "label": _("Scrap Qty"),
            "fieldtype": "Float",
            "width": 100,
        },
        {
            "fieldname": "pending_qty",
            "label": _("Pending Qty"),
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "fieldname": "scrap_pct",
            "label": _("Scrap %"),
            "fieldtype": "Float",
            "precision": 2,
            "width": 90,
        },
        {
            "fieldname": "target_warehouse",
            "label": _("Target Warehouse"),
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 160,
        },
    ]


def get_sub_assembly_items(production_plan):
    """Items consumed as components in another WO under the same plan are sub-assemblies."""
    rows = frappe.db.sql(
        """
        SELECT DISTINCT sed.item_code
        FROM `tabWork Order` wo2
        INNER JOIN `tabStock Entry` se ON se.work_order = wo2.name
        INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
        WHERE wo2.production_plan = %(production_plan)s
          AND se.purpose = 'Manufacture'
          AND sed.is_scrap_item = 0
          AND sed.s_warehouse IS NOT NULL
          AND se.docstatus = 1
        """,
        {"production_plan": production_plan},
        as_dict=False,
    )
    return [r[0] for r in rows] if rows else []


def get_data(filters):
    production_plan = filters.get("production_plan")
    if not production_plan:
        frappe.throw(_("Production Plan is mandatory"))

    sub_assembly_items = get_sub_assembly_items(production_plan)

    conditions = [
        "wo.production_plan = %(production_plan)s",
        "wo.docstatus != 2",
        # BR-01: Exclude items flagged as semi-finished / sub-assembly by item group
        "itm.item_group NOT IN ('Semi Finish Good', 'Semi-Finished', 'Sub Assembly', 'Sub-Assembly')",
        # BR-01: BOM level = 0 — item must NOT be a child component in any active BOM
        """wo.production_item NOT IN (
            SELECT DISTINCT bi.item_code
            FROM `tabBOM Item` bi
            INNER JOIN `tabBOM` b ON bi.parent = b.name
            WHERE b.is_active = 1 AND b.docstatus = 1
        )""",
    ]
    params = {"production_plan": production_plan}

    if sub_assembly_items:
        conditions.append("wo.production_item NOT IN %(sub_assembly_items)s")
        params["sub_assembly_items"] = tuple(sub_assembly_items)

    if filters.get("from_date"):
        conditions.append("pp.posting_date >= %(from_date)s")
        params["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("pp.posting_date <= %(to_date)s")
        params["to_date"] = filters["to_date"]

    fg_item = filters.get("fg_item")
    if fg_item:
        if isinstance(fg_item, str):
            fg_item = [fg_item]
        conditions.append("wo.production_item IN %(fg_item)s")
        params["fg_item"] = tuple(fg_item)

    if filters.get("item_group"):
        conditions.append("itm.item_group = %(item_group)s")
        params["item_group"] = filters["item_group"]

    if filters.get("warehouse"):
        conditions.append("wo.fg_warehouse = %(warehouse)s")
        params["warehouse"] = filters["warehouse"]

    if filters.get("wo_status"):
        conditions.append("wo.status = %(wo_status)s")
        params["wo_status"] = filters["wo_status"]

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            pp.name                          AS production_plan,
            pp.posting_date                  AS plan_date,
            wo.production_item               AS fg_item_code,
            itm.item_name                    AS fg_item_name,
            itm.item_group                   AS item_group,
            wo.stock_uom                     AS uom,
            wo.name                          AS work_order,
            wo.status                        AS wo_status,
            wo.fg_warehouse                  AS target_warehouse,
            wo.qty                           AS planned_qty,
            wo.produced_qty                  AS manufactured_qty,
            IFNULL(scrap.scrap_qty, 0)       AS scrap_qty,
            (wo.qty - wo.produced_qty)       AS pending_qty,
            ROUND(IFNULL(scrap.scrap_qty, 0)
                  / NULLIF(wo.qty, 0) * 100, 2) AS scrap_pct
        FROM `tabWork Order` wo
        INNER JOIN `tabProduction Plan` pp ON wo.production_plan = pp.name
        INNER JOIN `tabItem` itm ON itm.name = wo.production_item
        LEFT JOIN (
            SELECT se.work_order,
                   SUM(sed.qty) AS scrap_qty
            FROM `tabStock Entry` se
            INNER JOIN `tabStock Entry Detail` sed
                   ON sed.parent = se.name AND sed.is_scrap_item = 1
            WHERE se.docstatus = 1
              AND se.purpose = 'Manufacture'
            GROUP BY se.work_order
        ) AS scrap ON scrap.work_order = wo.name
        WHERE {where_clause}
        ORDER BY pp.name, wo.production_item, wo.name
    """

    rows = frappe.db.sql(query, params, as_dict=True)

    show_zero = filters.get("show_zero_qty")
    if not show_zero:
        rows = [r for r in rows if (r.get("manufactured_qty") or 0) > 0 or (r.get("scrap_qty") or 0) > 0]

    return build_summary_rows(rows)


def build_summary_rows(rows):
    """Inject plan-level subtotal rows and a grand-total row at the end."""
    if not rows:
        return rows

    output = []
    grand = {"planned_qty": 0, "manufactured_qty": 0, "scrap_qty": 0, "pending_qty": 0}

    current_plan = None
    plan_totals = None

    def flush_plan_total():
        if plan_totals and plan_totals["_rows_added"]:
            output.append({
                "production_plan": plan_totals["production_plan"],
                "fg_item_name": _("Plan Total"),
                "planned_qty": plan_totals["planned_qty"],
                "manufactured_qty": plan_totals["manufactured_qty"],
                "scrap_qty": plan_totals["scrap_qty"],
                "pending_qty": plan_totals["pending_qty"],
                "scrap_pct": round(
                    (plan_totals["scrap_qty"] / plan_totals["planned_qty"] * 100)
                    if plan_totals["planned_qty"] else 0,
                    2,
                ),
                "is_group": 1,
            })

    for row in rows:
        if row["production_plan"] != current_plan:
            flush_plan_total()
            current_plan = row["production_plan"]
            plan_totals = {
                "production_plan": current_plan,
                "planned_qty": 0,
                "manufactured_qty": 0,
                "scrap_qty": 0,
                "pending_qty": 0,
                "_rows_added": 0,
            }

        output.append(row)

        for key in ("planned_qty", "manufactured_qty", "scrap_qty", "pending_qty"):
            value = row.get(key) or 0
            plan_totals[key] += value
            grand[key] += value
        plan_totals["_rows_added"] += 1

    flush_plan_total()

    output.append({
        "fg_item_name": _("Grand Total"),
        "planned_qty": grand["planned_qty"],
        "manufactured_qty": grand["manufactured_qty"],
        "scrap_qty": grand["scrap_qty"],
        "pending_qty": grand["pending_qty"],
        "scrap_pct": round(
            (grand["scrap_qty"] / grand["planned_qty"] * 100) if grand["planned_qty"] else 0,
            2,
        ),
        "is_group": 1,
    })

    return output
