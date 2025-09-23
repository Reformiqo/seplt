# Copyright (c) 2025, Erpera and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "date",
            "label": "Date",
            "fieldtype": "Date",
            "width": 100
        },
        {
            "fieldname": "production_plan",
            "label": "Production Plan",
            "fieldtype": "Link",
            "options": "Production Plan",
            "width": 150
        },
        {
            "fieldname": "plan_status",
            "label": "Plan Status",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "fieldname": "work_order",
            "label": "Work Order",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "fieldname": "wo_status",
            "label": "WO Status",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "fieldname": "job_card",
            "label": "Job Card",
            "fieldtype": "Link",
            "options": "Job Card",
            "width": 120
        },
        {
            "fieldname": "production_item",
            "label": "Production Item",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "fieldname": "scrap_item",
            "label": "Scrap Item",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "fieldname": "scrap_qty",
            "label": "Scrap Qty",
            "fieldtype": "Float",
            "width": 100
        },
        {
            "fieldname": "planned_qty",
            "label": "Planned Qty",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "produced_qty",
            "label": "Produced Qty",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "pending_qty",
            "label": "Pending Qty",
            "fieldtype": "Float",
            "width": 120
        }
    ]


def get_data(filters):
    company = filters.get("company") if filters else None
    production_plan = filters.get("production_plan") if filters else None
    work_order_status = filters.get("work_order_status") if filters else None
    plan_status = filters.get("plan_status") if filters else None
    
    query = """
        WITH job_card_scrap AS (
            SELECT
                parent AS job_card,
                item_code,
                stock_qty
            FROM `tabJob Card Scrap Item`
            WHERE docstatus != 2
        ),

        work_order_scrap AS (
            SELECT
                jc.work_order,
                COALESCE(SUM(jcs.stock_qty), 0) AS total_scrap_qty_per_wo
            FROM `tabJob Card` jc
            LEFT JOIN job_card_scrap jcs ON jcs.job_card = jc.name
            WHERE jc.docstatus != 2
            GROUP BY jc.work_order
        ),

        work_order_data AS (
            SELECT
                pp.name AS production_plan,
                pp.posting_date,
                pp.status AS plan_status_raw,

                CASE
                    WHEN pp.status = 'Submitted' THEN '<span style="color: green; font-weight: bold; background-color: #2ed12e4a; padding: 0px 10px; border-radius: 12px;">Submitted</span>'
                    WHEN pp.status = 'In Process' THEN '<span style="color: orange; font-weight: bold; background-color: #ffa5004a; padding: 0px 10px; border-radius: 12px;">In Process</span>'
                    ELSE CONCAT('<span style="color: gray; font-weight: bold; background-color: #8080804a; padding: 0px 10px; border-radius: 12px;">', pp.status, '</span>')
                END AS plan_status,

                wo.name AS work_order,

                CASE
                    WHEN wo.status = 'Completed' THEN '<span style="color: green; font-weight: bold; background-color: #2ed12e4a; padding: 0px 10px; border-radius: 12px;">Completed</span>'
                    WHEN wo.status = 'In Process' THEN '<span style="color: orange; font-weight: bold; background-color: #ffa5004a; padding: 0px 10px; border-radius: 12px;">In Process</span>'
                    WHEN wo.status = 'Closed' THEN '<span style="color: gray; font-weight: bold; background-color: #8080804a; padding: 0px 10px; border-radius: 12px;">Closed</span>'
                    ELSE CONCAT('<span style="color: gray; font-weight: bold; background-color: #8080804a; padding: 0px 10px; border-radius: 12px;">', wo.status, '</span>')
                END AS wo_status,

                CONCAT('<a href="/app/work-order/', wo.name, '" target="_blank">', wo.name, '</a>') AS work_order_link,

                wo.qty AS planned_qty,
                wo.produced_qty AS produced_qty,
                (wo.qty - wo.produced_qty) AS pending_qty,

                COALESCE(wos.total_scrap_qty_per_wo, 0) AS scrap_qty,

                jc.name AS job_card,
                wo.item_name AS production_item,
                jcs.item_code,

                ROW_NUMBER() OVER (PARTITION BY pp.name ORDER BY wo.name, jc.name) AS row_num

            FROM `tabProduction Plan` pp
            LEFT JOIN `tabWork Order` wo 
                ON wo.production_plan = pp.name AND wo.docstatus != 2
                AND (
                    %(company)s IS NULL OR %(company)s = '' OR wo.company = %(company)s
                )
                AND (
                    %(work_order_status)s IS NULL OR %(work_order_status)s = '' OR wo.status = %(work_order_status)s
                )
            LEFT JOIN work_order_scrap wos ON wos.work_order = wo.name

            INNER JOIN `tabJob Card` jc ON jc.work_order = wo.name AND jc.docstatus != 2
            INNER JOIN job_card_scrap jcs ON jcs.job_card = jc.name

            WHERE pp.docstatus != 2
              AND (
                %(company)s IS NULL OR %(company)s = '' OR pp.company = %(company)s
              )
              AND (
                %(production_plan)s IS NULL OR %(production_plan)s = '' OR pp.name = %(production_plan)s
              )
              AND (
                %(plan_status)s IS NULL OR %(plan_status)s = '' OR pp.status = %(plan_status)s
              )
        )

        SELECT
            CASE WHEN is_total = 0 AND wd.row_num = 1 THEN wd.posting_date ELSE NULL END AS "Date",
            CASE WHEN is_total = 0 AND wd.row_num = 1 THEN wd.production_plan ELSE NULL END AS "Production Plan",
            CASE 
                WHEN is_total = 0 AND wd.row_num = 1 THEN wd.plan_status
                WHEN is_total = 0 THEN NULL
                ELSE '<b>Total</b>'
            END AS "Plan Status",

            CASE WHEN is_total = 0 THEN wd.work_order_link ELSE NULL END AS "Work Order",
            CASE WHEN is_total = 0 THEN wd.wo_status ELSE NULL END AS "WO Status",

            CASE WHEN is_total = 0 THEN wd.job_card ELSE NULL END AS "Job Card",
            CASE WHEN is_total = 0 THEN wd.production_item ELSE NULL END AS "Production Item",
            CASE WHEN is_total = 0 THEN wd.item_code ELSE NULL END AS "Scrap Item",

            SUM(wd.scrap_qty) AS "Scrap Qty",
            SUM(wd.planned_qty) AS "Planned Qty",
            SUM(wd.produced_qty) AS "Produced Qty",
            SUM(wd.pending_qty) AS "Pending Qty"

        FROM work_order_data wd

        CROSS JOIN (
            SELECT 0 AS is_total
            UNION ALL
            SELECT 1
        ) AS t

        GROUP BY
            wd.production_plan,
            CASE WHEN is_total = 0 THEN wd.work_order_link ELSE NULL END,
            CASE WHEN is_total = 0 THEN wd.wo_status ELSE NULL END,
            CASE WHEN is_total = 0 THEN wd.row_num ELSE NULL END,
            CASE WHEN is_total = 0 THEN wd.posting_date ELSE NULL END,
            CASE WHEN is_total = 0 THEN wd.plan_status ELSE NULL END,
            CASE WHEN is_total = 0 THEN wd.job_card ELSE NULL END,
            CASE WHEN is_total = 0 THEN wd.production_item ELSE NULL END,
            CASE WHEN is_total = 0 THEN wd.item_code ELSE NULL END,
            is_total

        ORDER BY
            wd.production_plan,
            is_total,
            wd.work_order,
            wd.job_card
    """
    
    data = frappe.db.sql(query, {
        "company": company,
        "production_plan": production_plan,
        "work_order_status": work_order_status,
        "plan_status": plan_status
    }, as_dict=True)
    
    # Convert the data to match the column fieldnames
    formatted_data = []
    for row in data:
        formatted_row = {
            "date": row.get("Date"),
            "production_plan": row.get("Production Plan"),
            "plan_status": row.get("Plan Status"),
            "work_order": row.get("Work Order"),
            "wo_status": row.get("WO Status"),
            "job_card": row.get("Job Card"),
            "production_item": row.get("Production Item"),
            "scrap_item": row.get("Scrap Item"),
            "scrap_qty": row.get("Scrap Qty"),
            "planned_qty": row.get("Planned Qty"),
            "produced_qty": row.get("Produced Qty"),
            "pending_qty": row.get("Pending Qty")
        }
        formatted_data.append(formatted_row)
    
    return formatted_data
