"""Tests for the Purchase Receipt Trends Including Subcontracting report -- SO1-I134.

Raj reported that "Purchase Receipt Trends" never shows subcontracting
receipts.  It cannot: the shared trends engine reads a single doctype pair
(erpnext/controllers/trends.py:107-218) and in v16 subcontracted material is
received on `Subcontracting Receipt`, not on `Purchase Receipt`.

These tests run against the real data on this site rather than fixtures, which
is the whole point -- the report has to reconcile against what SEPL actually
booked.  Every expected number is recomputed independently in SQL, so the
tests stay correct as the dataset grows.
"""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

from erpnext.controllers.trends import get_period_date_ranges
from erpnext.stock.report.purchase_receipt_trends.purchase_receipt_trends import (
	execute as execute_standard,
)

from seplt.seplt.report.purchase_receipt_trends_including_subcontracting.purchase_receipt_trends_including_subcontracting import (
	execute,
)

def label(column):
	"""'Total(Qty):Float:120' -> 'Total(Qty)'."""
	return column.split(":")[0]


def canonical(data, based_on):
	"""Rows as plain lists, with the Item Name column pinned to the Item master.

	The standard report groups on ``item_code`` but selects the child row's
	``item_name``, so MariaDB hands back an arbitrary one of the historical
	names.  This report resolves it from the master on purpose; normalising
	both sides is what lets the rest of the row be compared exactly.
	"""
	rows = [list(row) for row in data]
	if based_on != "Item":
		return rows

	for row in rows:
		if row[0] and row[0] != "'Total'":
			row[1] = frappe.db.get_value("Item", row[0], "item_name") or row[1]
	return rows


class TestPurchaseReceiptTrendsIncludingSubcontracting(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		# the company / fiscal year that actually has submitted subcontracting
		# receipts, so the assertions below have something to bite on
		row = frappe.db.sql(
			"""SELECT sr.company, fy.name, fy.year_start_date, fy.year_end_date, count(*) AS n
			FROM `tabSubcontracting Receipt` sr
			JOIN `tabFiscal Year` fy
				ON sr.posting_date BETWEEN fy.year_start_date AND fy.year_end_date
			WHERE sr.docstatus = 1
			GROUP BY sr.company, fy.name
			ORDER BY n DESC LIMIT 1""",
			as_dict=True,
		)
		assert row, "test prerequisite: this site has no submitted Subcontracting Receipts"

		cls.company = row[0].company
		cls.fiscal_year = row[0].name
		cls.year_start_date = row[0].year_start_date
		cls.year_end_date = row[0].year_end_date

		assert frappe.db.exists(
			"Purchase Receipt", {"docstatus": 1, "company": cls.company}
		), "test prerequisite: need submitted Purchase Receipts to compare against"

	# --- helpers ----------------------------------------------------------

	def filters(self, **overrides):
		values = {
			"company": self.company,
			"period": "Monthly",
			"fiscal_year": self.fiscal_year,
			"period_based_on": "posting_date",
			"based_on": "Item",
			"group_by": "",
		}
		values.update(overrides)
		return frappe._dict(values)

	def subcontracting_totals(self, from_date=None, to_date=None):
		"""Qty and amount the report is expected to add, computed independently.

		Mirrors the mapping documented on the report: `Subcontracting Receipt
		Item` stores `qty` + `conversion_factor` instead of `stock_qty`, and
		`amount` instead of `base_net_amount` (it has no currency field, so it
		is always already in company currency).
		"""
		row = frappe.db.sql(
			"""SELECT ifnull(sum(sri.qty * ifnull(sri.conversion_factor, 1)), 0),
				ifnull(sum(sri.amount), 0)
			FROM `tabSubcontracting Receipt` sr
			JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = sr.name
			WHERE sr.docstatus = 1 AND sr.company = %s
				AND sr.posting_date BETWEEN %s AND %s""",
			(self.company, from_date or self.year_start_date, to_date or self.year_end_date),
			as_list=True,
		)
		return row[0][0], row[0][1]

	# --- the reported defect ---------------------------------------------

	def test_standard_report_omits_subcontracting(self):
		"""Reproduces SO1-I134 on the standard report."""
		sc_qty, sc_amount = self.subcontracting_totals()
		self.assertGreater(sc_qty, 0, "no subcontracting qty in the chosen window")

		_columns, data, _msg, _chart = execute_standard(self.filters())
		standard_total = data[-1]

		purchase_only = frappe.db.sql(
			"""SELECT sum(pri.stock_qty), sum(pri.base_net_amount)
			FROM `tabPurchase Receipt` pr
			JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
			WHERE pr.docstatus = 1 AND pr.company = %s
				AND pr.posting_date BETWEEN %s AND %s""",
			(self.company, self.year_start_date, self.year_end_date),
			as_list=True,
		)[0]

		# the standard total is purchase receipts and nothing else ...
		self.assertAlmostEqual(standard_total[-2], purchase_only[0], places=2)
		self.assertAlmostEqual(standard_total[-1], purchase_only[1], places=2)
		# ... so the subcontracting qty and amount are simply missing from it
		self.assertNotAlmostEqual(standard_total[-2], purchase_only[0] + sc_qty, places=2)
		self.assertNotAlmostEqual(standard_total[-1], purchase_only[1] + sc_amount, places=2)

	# --- parity with the standard report ---------------------------------

	def test_identical_to_standard_report_when_subcontracting_excluded(self):
		"""Nothing but the union changed: switch it off and the output matches."""
		for based_on in ("Item", "Item Group", "Supplier", "Supplier Group"):
			with self.subTest(based_on=based_on):
				filters = self.filters(based_on=based_on)
				std_columns, std_data, _m1, _std_chart = execute_standard(filters.copy())
				columns, data, _m2, _chart = execute(dict(filters, include_subcontracting=0))

				self.assertEqual(std_columns, columns)
				self.assertEqual(canonical(std_data, based_on), canonical(data, based_on))

	def test_company_without_subcontracting_is_unchanged(self):
		"""A company with no subcontracting receipts must read exactly as before."""
		company = frappe.db.sql(
			"""SELECT pr.company FROM `tabPurchase Receipt` pr
			WHERE pr.docstatus = 1 AND pr.company NOT IN (
				SELECT sr.company FROM `tabSubcontracting Receipt` sr WHERE sr.docstatus = 1)
			LIMIT 1""",
			as_list=True,
		)
		self.assertTrue(company, "test prerequisite: need a company with no Subcontracting Receipts")

		filters = self.filters(company=company[0][0])
		_c1, std_data, _m1, _ch1 = execute_standard(filters.copy())
		_c2, data, _m2, _ch2 = execute(dict(filters, include_subcontracting=1))

		self.assertEqual(canonical(std_data, "Item"), canonical(data, "Item"))

	def test_item_name_is_taken_from_the_item_master(self):
		"""Deterministic labels, unlike the standard report's arbitrary pick."""
		ambiguous = frappe.db.sql(
			"""SELECT item_code FROM `tabPurchase Receipt Item`
			GROUP BY item_code HAVING count(DISTINCT item_name) > 1""",
			as_list=True,
		)
		self.assertTrue(ambiguous, "test prerequisite: need an item renamed mid-history")

		_columns, data, _msg, _chart = execute(dict(self.filters(), include_subcontracting=1))
		checked = 0
		for row in data:
			if not row[0] or row[0] == "'Total'":
				continue
			master_name = frappe.db.get_value("Item", row[0], "item_name")
			if master_name:
				self.assertEqual(row[1], master_name)
				checked += 1
		self.assertGreater(checked, 0)

	# --- subcontracting actually lands in the numbers ---------------------

	def test_totals_include_subcontracting(self):
		sc_qty, sc_amount = self.subcontracting_totals()

		_c1, without, _m1, _ch1 = execute(dict(self.filters(), include_subcontracting=0))
		_c2, with_sc, _m2, _ch2 = execute(dict(self.filters(), include_subcontracting=1))

		self.assertAlmostEqual(with_sc[-1][-2] - without[-1][-2], sc_qty, places=2)
		self.assertAlmostEqual(with_sc[-1][-1] - without[-1][-1], sc_amount, places=2)

	def test_draft_and_cancelled_subcontracting_receipts_are_ignored(self):
		"""The delta must match submitted receipts only."""
		unsubmitted = frappe.db.count("Subcontracting Receipt", {"docstatus": ["!=", 1]})
		self.assertGreater(unsubmitted, 0, "test prerequisite: need draft/cancelled receipts")

		everything = frappe.db.sql(
			"""SELECT ifnull(sum(sri.qty * ifnull(sri.conversion_factor, 1)), 0)
			FROM `tabSubcontracting Receipt` sr
			JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = sr.name
			WHERE sr.company = %s AND sr.posting_date BETWEEN %s AND %s""",
			(self.company, self.year_start_date, self.year_end_date),
			as_list=True,
		)[0][0]
		submitted_qty, _amount = self.subcontracting_totals()
		self.assertGreater(everything, submitted_qty, "test prerequisite: drafts in this window")

		_c1, without, _m1, _ch1 = execute(dict(self.filters(), include_subcontracting=0))
		_c2, with_sc, _m2, _ch2 = execute(dict(self.filters(), include_subcontracting=1))
		self.assertAlmostEqual(with_sc[-1][-2] - without[-1][-2], submitted_qty, places=2)

	def test_subcontracted_only_item_gets_its_own_row(self):
		"""An item received only via subcontracting is invisible to the standard report."""
		item = frappe.db.sql(
			"""SELECT sri.item_code
			FROM `tabSubcontracting Receipt` sr
			JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = sr.name
			WHERE sr.docstatus = 1 AND sr.company = %s
				AND sr.posting_date BETWEEN %s AND %s
				AND sri.item_code NOT IN (
					SELECT pri.item_code FROM `tabPurchase Receipt` pr
					JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
					WHERE pr.docstatus = 1 AND pr.company = %s
						AND pr.posting_date BETWEEN %s AND %s)
			LIMIT 1""",
			(
				self.company,
				self.year_start_date,
				self.year_end_date,
				self.company,
				self.year_start_date,
				self.year_end_date,
			),
			as_list=True,
		)
		self.assertTrue(item, "test prerequisite: need a subcontracting-only item")
		item_code = item[0][0]

		_c1, std_data, _m1, _ch1 = execute_standard(self.filters())
		self.assertNotIn(item_code, [row[0] for row in std_data])

		_c2, data, _m2, _ch2 = execute(dict(self.filters(), include_subcontracting=1))
		self.assertIn(item_code, [row[0] for row in data])

	def test_monthly_buckets_get_subcontracting(self):
		"""Every month column, not just the grand total, picks the receipts up."""
		columns, without, _m1, _ch1 = execute(dict(self.filters(), include_subcontracting=0))
		_c2, with_sc, _m2, _ch2 = execute(dict(self.filters(), include_subcontracting=1))

		labels = [label(column) for column in columns]
		months_checked = 0

		for start_date, end_date in get_period_date_ranges("Monthly", self.fiscal_year):
			sc_qty, sc_amount = self.subcontracting_totals(start_date, end_date)
			if not sc_qty:
				continue

			month = start_date.strftime("%b")
			qty_index = labels.index(f"{month} (Qty)")
			amount_index = labels.index(f"{month} (Amt)")

			self.assertAlmostEqual(
				(with_sc[-1][qty_index] or 0) - (without[-1][qty_index] or 0), sc_qty, places=2
			)
			self.assertAlmostEqual(
				(with_sc[-1][amount_index] or 0) - (without[-1][amount_index] or 0),
				sc_amount,
				places=2,
			)
			months_checked += 1

		self.assertGreater(months_checked, 0, "no month carried subcontracting qty")

	def test_item_group_is_resolved_for_subcontracting_items(self):
		"""`Subcontracting Receipt Item` has no item_group column; it comes from Item."""
		row = frappe.db.sql(
			"""SELECT itm.item_group,
				sum(sri.qty * ifnull(sri.conversion_factor, 1)), sum(sri.amount)
			FROM `tabSubcontracting Receipt` sr
			JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = sr.name
			JOIN `tabItem` itm ON itm.name = sri.item_code
			WHERE sr.docstatus = 1 AND sr.company = %s
				AND sr.posting_date BETWEEN %s AND %s
			GROUP BY itm.item_group ORDER BY 3 DESC LIMIT 1""",
			(self.company, self.year_start_date, self.year_end_date),
			as_list=True,
		)
		self.assertTrue(row, "test prerequisite: subcontracting items must link to an Item")
		item_group, sc_qty, sc_amount = row[0]

		filters = self.filters(based_on="Item Group")
		_c1, without, _m1, _ch1 = execute(dict(filters, include_subcontracting=0))
		_c2, with_sc, _m2, _ch2 = execute(dict(filters, include_subcontracting=1))

		def find(data):
			for data_row in data:
				if data_row[0] == item_group:
					return data_row
			return None

		after = find(with_sc)
		self.assertIsNotNone(after, f"{item_group} missing once subcontracting is included")

		before = find(without)
		self.assertAlmostEqual(after[-2] - (before[-2] if before else 0), sc_qty, places=2)
		self.assertAlmostEqual(after[-1] - (before[-1] if before else 0), sc_amount, places=2)

	# --- group by ---------------------------------------------------------

	def test_group_by_rows_reconcile_with_their_parent(self):
		filters = self.filters(based_on="Item", group_by="Supplier")
		columns, data, _msg, _chart = execute(dict(filters, include_subcontracting=1))

		# Item / Item Name / Currency / Supplier / <periods> / Total(Qty) / Total(Amt)
		self.assertEqual(label(columns[3]), "Supplier")

		parent = None
		children = 0
		checked = 0
		running_qty = 0.0

		def flush():
			nonlocal checked
			if parent is not None and children:
				self.assertAlmostEqual(running_qty, parent[-2], places=2)
				checked += 1

		for row in data:
			if row[0] == "'Total'":
				break
			if row[0] != "":
				flush()
				parent, children, running_qty = row, 0, 0.0
				self.assertEqual(row[3], "", "consolidated row must leave Group By blank")
			else:
				children += 1
				self.assertTrue(row[3], "group row must name its supplier")
				running_qty += row[-2] or 0
		flush()

		self.assertGreater(checked, 10, "expected many Based On rows to reconcile")

	def test_based_on_supplier_credits_the_subcontractor(self):
		"""The subcontractor's own row has to grow by exactly its receipts."""
		row = frappe.db.sql(
			"""SELECT sr.supplier,
				sum(sri.qty * ifnull(sri.conversion_factor, 1)), sum(sri.amount)
			FROM `tabSubcontracting Receipt` sr
			JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = sr.name
			WHERE sr.docstatus = 1 AND sr.company = %s
				AND sr.posting_date BETWEEN %s AND %s
			GROUP BY sr.supplier ORDER BY 3 DESC LIMIT 1""",
			(self.company, self.year_start_date, self.year_end_date),
			as_list=True,
		)
		self.assertTrue(row, "test prerequisite: need a subcontractor in this window")
		supplier, sc_qty, sc_amount = row[0]

		filters = self.filters(based_on="Supplier")
		_c1, without, _m1, _ch1 = execute(dict(filters, include_subcontracting=0))
		_c2, with_sc, _m2, _ch2 = execute(dict(filters, include_subcontracting=1))

		def find(data):
			for data_row in data:
				if data_row[0] == supplier:
					return data_row
			return None

		after = find(with_sc)
		self.assertIsNotNone(after, f"{supplier} missing once subcontracting is included")

		before = find(without)
		self.assertAlmostEqual(after[-2] - (before[-2] if before else 0), sc_qty, places=2)
		self.assertAlmostEqual(after[-1] - (before[-1] if before else 0), sc_amount, places=2)

	def test_unsupported_group_by_is_rejected(self):
		filters = self.filters(based_on="Item", group_by="Territory")
		self.assertRaises(frappe.ValidationError, execute, dict(filters))

	# --- chart ------------------------------------------------------------

	def test_chart_keeps_the_standard_shape(self):
		_c1, _d1, _m1, std_chart = execute_standard(self.filters())
		_c2, data, _m2, chart = execute(dict(self.filters(), include_subcontracting=1))

		self.assertEqual(std_chart["type"], chart["type"])
		self.assertEqual(std_chart["colors"], chart["colors"])
		self.assertEqual(std_chart["fieldtype"], chart["fieldtype"])
		self.assertEqual(
			std_chart["data"]["datasets"][0]["name"], chart["data"]["datasets"][0]["name"]
		)

		# every plotted point is the Total(Amt) of the row it is labelled with
		totals = {row[0]: row[-1] for row in data}
		labels = chart["data"]["labels"]
		values = chart["data"]["datasets"][0]["values"]
		self.assertEqual(len(labels), len(values))
		self.assertTrue(labels)
		for name, value in zip(labels, values, strict=True):
			self.assertAlmostEqual(totals[name], value, places=2)

	def test_chart_moves_once_subcontracting_counts(self):
		"""Based On = Item Group: few enough rows that the receipts reach the top 10."""
		filters = self.filters(based_on="Item Group")
		_c1, _d1, _m1, chart_without = execute(dict(filters, include_subcontracting=0))
		_c2, _d2, _m2, chart_with = execute(dict(filters, include_subcontracting=1))

		self.assertNotEqual(chart_without["data"], chart_with["data"])

	# --- defaults ---------------------------------------------------------

	def test_subcontracting_is_included_by_default(self):
		"""A missing or blank filter must not silently reintroduce the defect."""
		_c0, explicit, _m0, _ch0 = execute(dict(self.filters(), include_subcontracting=1))

		for value in ({}, {"include_subcontracting": None}, {"include_subcontracting": ""}):
			with self.subTest(value=value):
				_c1, data, _m1, _ch1 = execute(dict(self.filters(), **value))
				self.assertEqual([list(r) for r in data], [list(r) for r in explicit])
