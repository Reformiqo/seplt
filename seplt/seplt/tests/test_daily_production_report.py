"""Tests for the Daily Production Report (SO1-I132).

Raj Tiwari asked for Item, Batch, Machine No., Employee Name, Finished Quantity
and Scrap Quantity. Machine No. and Employee Name were the two that did not
exist, so most of these tests are about proving those two actually carry values
-- a column that renders but is always blank would not answer the ticket.

The deterministic tests seed one Job Card on an isolated posting date
(1 January 2019, decades before any real SEPL production) against a real Work
Order, so the assertions cannot be perturbed by live data. The remaining tests
run against the real site data to prove the joins hold at scale.
"""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from seplt.seplt.report.daily_production_report.daily_production_report import (
	execute,
	get_columns,
)

# far outside any real SEPL production window, so the seeded card is the only
# row the report can return for this date
SEED_DATE = "2019-01-01"

# the nine fieldnames the report shipped with before SO1-I132; they are kept so
# that saved column widths / pinned columns keep working
LEGACY_FIELDNAMES = [
	"date",
	"product_name",
	"opration_name",
	"rm_batch_no",
	"production_quantity",
	"qty_rejected",
	"rej_",
	"final_product_batch_no",
	"lot_no",
]


class TestDailyProductionReport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		source = frappe.db.sql(
			"""SELECT wo.name AS work_order, wo.company, wo.production_item,
				o.name AS operation_id, o.operation, o.workstation, o.sequence_id, o.idx
			FROM `tabWork Order` wo
			JOIN `tabWork Order Operation` o ON o.parent = wo.name
			WHERE wo.docstatus = 1 AND IFNULL(o.workstation, '') != ''
			LIMIT 1""",
			as_dict=True,
		)
		assert source, "test prerequisite: need one submitted Work Order with a workstation"
		cls.source = source[0]

		cls.employees = [
			row.name for row in frappe.get_all("Employee", fields=["name"], order_by="name", limit=2)
		]
		assert len(cls.employees) == 2, "test prerequisite: need at least two Employee records"
		cls.employee_names = [
			frappe.db.get_value("Employee", employee, "employee_name") for employee in cls.employees
		]

		card = frappe.get_doc(
			{
				"doctype": "Job Card",
				"company": cls.source.company,
				"work_order": cls.source.work_order,
				"posting_date": SEED_DATE,
				"production_item": cls.source.production_item,
				"operation": cls.source.operation,
				"operation_id": cls.source.operation_id,
				"operation_row_id": cls.source.idx,
				"sequence_id": cls.source.sequence_id,
				"workstation": cls.source.workstation,
				"for_quantity": 100,
				"time_logs": [
					{
						"employee": cls.employees[0],
						"completed_qty": 45,
						"from_time": f"{SEED_DATE} 08:00:00",
						"to_time": f"{SEED_DATE} 12:00:00",
					},
					{
						"employee": cls.employees[1],
						"completed_qty": 45,
						"from_time": f"{SEED_DATE} 12:00:00",
						"to_time": f"{SEED_DATE} 16:00:00",
					},
				],
			}
		)
		card.insert(ignore_permissions=True)
		# set on the row rather than the doc: ERPNext recomputes both from the
		# time logs during validate, and the report reads the stored values
		card.db_set("total_completed_qty", 90)
		card.db_set("process_loss_qty", 10)
		card.submit()
		cls.job_card = card.name

	@classmethod
	def tearDownClass(cls):
		# the class cleanup rolls the transaction back; this is the belt and
		# braces in case anything in the submit path committed
		frappe.db.rollback()
		if getattr(cls, "job_card", None) and frappe.db.exists("Job Card", cls.job_card):
			frappe.db.sql("DELETE FROM `tabJob Card Time Log` WHERE parent = %s", cls.job_card)
			frappe.db.sql("DELETE FROM `tabJob Card` WHERE name = %s", cls.job_card)
			frappe.db.commit()
		super().tearDownClass()

	def seeded_row(self):
		_, data = execute({"from_date": SEED_DATE, "to_date": SEED_DATE})
		rows = [row for row in data if row["job_card"] == self.job_card]
		self.assertEqual(len(rows), 1, "the seeded Job Card must produce exactly one row")
		return rows[0]

	# ---- columns -------------------------------------------------------

	def test_machine_no_and_employee_name_columns_exist(self):
		"""The two fields SO1-I132 asked for that the report did not have."""
		columns = {column["fieldname"]: column for column in get_columns()}

		self.assertIn("machine_no", columns)
		self.assertEqual(columns["machine_no"]["fieldtype"], "Link")
		self.assertEqual(columns["machine_no"]["options"], "Workstation")

		self.assertIn("employee_name", columns)
		self.assertEqual(columns["employee_name"]["fieldtype"], "Data")

	def test_legacy_fieldnames_are_preserved(self):
		"""Enhancing, not replacing -- saved views key off the fieldname."""
		fieldnames = [column["fieldname"] for column in get_columns()]
		for fieldname in LEGACY_FIELDNAMES:
			self.assertIn(fieldname, fieldnames)

	def test_quantity_columns_are_numeric(self):
		"""They were Data, which made the total row meaningless."""
		columns = {column["fieldname"]: column for column in get_columns()}
		self.assertEqual(columns["production_quantity"]["fieldtype"], "Float")
		self.assertEqual(columns["qty_rejected"]["fieldtype"], "Float")
		self.assertEqual(columns["rej_"]["fieldtype"], "Percent")

	# ---- seeded, deterministic -----------------------------------------

	def test_machine_no_is_the_job_card_workstation(self):
		self.assertEqual(self.seeded_row()["machine_no"], self.source.workstation)

	def test_employee_name_lists_every_operator(self):
		employee_name = self.seeded_row()["employee_name"]
		for name in self.employee_names:
			self.assertIn(name, employee_name)

	def test_multiple_operators_do_not_multiply_the_quantities(self):
		"""Two operators must stay one row.

		Exploding a card into one row per operator would double Production
		Quantity in the total row, because the report has add_total_row set.
		"""
		row = self.seeded_row()
		self.assertEqual(row["employee_name"].count(","), 1)
		self.assertEqual(flt(row["production_quantity"]), 90.0)
		self.assertEqual(flt(row["qty_rejected"]), 10.0)

	def test_item_operation_and_work_order_come_from_the_job_card(self):
		row = self.seeded_row()
		self.assertEqual(row["product_name"], self.source.production_item)
		self.assertEqual(row["opration_name"], self.source.operation)
		self.assertEqual(row["work_order"], self.source.work_order)

	def test_rejection_percentage_is_computed(self):
		"""It used to be hard-coded to 0. 10 rejected of 100 handled = 10%."""
		self.assertAlmostEqual(flt(self.seeded_row()["rej_"]), 10.0, places=4)

	def test_zero_production_does_not_divide_by_zero(self):
		frappe.db.set_value(
			"Job Card", self.job_card, {"total_completed_qty": 0, "process_loss_qty": 0}
		)
		try:
			self.assertEqual(flt(self.seeded_row()["rej_"]), 0.0)
		finally:
			frappe.db.set_value(
				"Job Card", self.job_card, {"total_completed_qty": 90, "process_loss_qty": 10}
			)

	# ---- filters -------------------------------------------------------

	def test_workstation_filter_narrows_to_that_machine(self):
		_, data = execute(
			{
				"from_date": SEED_DATE,
				"to_date": SEED_DATE,
				"workstation": self.source.workstation,
			}
		)
		self.assertTrue(data)
		self.assertEqual({row["machine_no"] for row in data}, {self.source.workstation})

	def test_employee_filter_matches_a_card_worked_by_that_operator(self):
		_, data = execute(
			{"from_date": SEED_DATE, "to_date": SEED_DATE, "employee": self.employees[1]}
		)
		self.assertIn(self.job_card, [row["job_card"] for row in data])

		_, data = execute({"from_date": SEED_DATE, "to_date": SEED_DATE, "employee": "__no_such__"})
		self.assertEqual(data, [])

	def test_dates_are_mandatory(self):
		self.assertRaises(frappe.ValidationError, execute, {})
		self.assertRaises(frappe.ValidationError, execute, {"from_date": SEED_DATE})

	def test_reversed_date_range_is_rejected(self):
		self.assertRaises(
			frappe.ValidationError,
			execute,
			{"from_date": "2026-03-31", "to_date": "2026-03-01"},
		)

	def test_filter_values_are_bound_not_interpolated(self):
		"""A quote in a filter must be a literal, not SQL."""
		_, data = execute(
			{
				"from_date": SEED_DATE,
				"to_date": SEED_DATE,
				"workstation": "' OR '1'='1",
			}
		)
		self.assertEqual(data, [])

	# ---- real site data -------------------------------------------------

	def test_machine_no_is_never_blank_on_real_production_data(self):
		"""Every submitted Job Card carries a workstation, so the column must
		be fully populated -- a column of blanks would not answer the ticket."""
		window = frappe.db.sql(
			"""SELECT posting_date FROM `tabJob Card`
			WHERE docstatus = 1 AND posting_date IS NOT NULL
			ORDER BY posting_date DESC LIMIT 1""",
			as_dict=True,
		)
		assert window, "test prerequisite: need submitted Job Cards on this site"
		day = window[0].posting_date

		_, data = execute({"from_date": day, "to_date": day})
		self.assertTrue(data, f"expected production rows on {day}")
		self.assertTrue(
			all(row["machine_no"] for row in data),
			"Machine No. must be populated on every row",
		)

	def test_employee_name_is_populated_on_real_production_data(self):
		"""Pick a day that actually has operators recorded and prove the join
		lands, rather than asserting the column merely exists."""
		day = frappe.db.sql(
			"""SELECT jc.posting_date
			FROM `tabJob Card` jc
			JOIN `tabJob Card Time Log` tl
				ON tl.parent = jc.name AND tl.parenttype = 'Job Card'
			WHERE jc.docstatus = 1 AND IFNULL(tl.employee, '') != ''
			ORDER BY jc.posting_date DESC LIMIT 1""",
			as_dict=True,
		)
		assert day, "test prerequisite: need a Job Card with an operator on this site"
		day = day[0].posting_date

		_, data = execute({"from_date": day, "to_date": day})
		named = [row for row in data if row["employee_name"]]
		self.assertTrue(named, f"expected at least one operator name on {day}")

		# and the names must resolve to real Employee records, not raw ids
		sample = named[0]["employee_name"].split(", ")[0]
		self.assertTrue(
			frappe.db.exists("Employee", {"employee_name": sample})
			or frappe.db.exists("Employee", sample),
			f"{sample!r} should be an Employee name",
		)

	def test_final_product_batch_comes_from_the_manufacture_stock_entry(self):
		"""The Job Card carries no batch, so the batch columns are read off the
		Manufacture Stock Entry of the same Work Order on the same day."""
		match = frappe.db.sql(
			"""SELECT jc.name AS job_card, jc.posting_date, sed.batch_no
			FROM `tabJob Card` jc
			JOIN `tabStock Entry` se
				ON se.work_order = jc.work_order
				AND se.posting_date = jc.posting_date
				AND se.docstatus = 1 AND se.purpose = 'Manufacture'
			JOIN `tabStock Entry Detail` sed
				ON sed.parent = se.name
				AND sed.is_finished_item = 1
				AND sed.item_code = jc.production_item
			WHERE jc.docstatus = 1 AND IFNULL(sed.batch_no, '') != ''
			ORDER BY jc.posting_date DESC LIMIT 1""",
			as_dict=True,
		)
		assert match, "test prerequisite: need a Job Card whose Work Order produced a batch"
		match = match[0]

		_, data = execute({"from_date": match.posting_date, "to_date": match.posting_date})
		row = next(row for row in data if row["job_card"] == match.job_card)
		self.assertIn(match.batch_no, row["final_product_batch_no"])
