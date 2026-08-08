"""Tests for the Manufacture guards.

Each test maps to a defect actually seen on the live SEPL site on 09-08-2026:
zero-consumption Manufacture entries (410 of them, Rs 96.42 crore) and the
amount-in-rate typo on MAT-STE-40604 (Rs 93.92 crore).
"""

from __future__ import annotations

import unittest.mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from seplt.seplt.validations.manufacture_guard import (
	OVERRIDE_FIELD,
	RATE_BLOCK_MULTIPLE,
	check_consumption,
	check_rate_sanity,
	install,
)


class TestManufactureGuard(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install()
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.wh = frappe.db.get_value("Warehouse", {"company": cls.company, "is_group": 0}, "name")
		# an item that actually has a known valuation, so the rate check has a benchmark
		row = frappe.db.sql(
			"""SELECT b.item_code, b.warehouse, b.valuation_rate
			FROM `tabBin` b JOIN `tabItem` i ON i.name = b.item_code
			WHERE b.valuation_rate > 1 AND i.is_stock_item = 1 AND i.disabled = 0
			ORDER BY b.actual_qty DESC LIMIT 1""",
			as_dict=True,
		)
		assert row, "test prerequisite: need at least one Bin with a valuation rate on this site"
		cls.item = row[0].item_code
		cls.item_wh = row[0].warehouse
		cls.item_rate = flt(row[0].valuation_rate)

	def _entry(self, rows, purpose="Manufacture"):
		"""Build an in-memory Stock Entry — the guards are pure functions over the doc."""
		doc = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": purpose,
				"purpose": purpose,
				"company": self.company,
				"items": rows,
			}
		)
		for idx, row in enumerate(doc.items, start=1):
			row.idx = idx
		return doc

	def _produced(self, rate, qty=100, warehouse=None):
		return {
			"item_code": self.item,
			"qty": qty,
			"basic_rate": rate,
			"basic_amount": flt(qty) * flt(rate),
			"t_warehouse": warehouse or self.item_wh,
		}

	def _consumed(self, rate=None, qty=50):
		rate = self.item_rate if rate is None else rate
		return {
			"item_code": self.item,
			"qty": qty,
			"basic_rate": rate,
			"basic_amount": flt(qty) * flt(rate),
			"s_warehouse": self.item_wh,
		}

	# ------------------------------------------------------------------
	# Guard 1 — zero consumption (the 410-entry defect)
	# ------------------------------------------------------------------
	def test_production_without_consumption_is_blocked(self):
		doc = self._entry([self._produced(self.item_rate)])
		with self.assertRaises(frappe.ValidationError) as cm:
			check_consumption(doc)
		self.assertIn("consumes no raw material", str(cm.exception))

	def test_production_with_consumption_passes(self):
		doc = self._entry([self._consumed(), self._produced(self.item_rate)])
		check_consumption(doc)  # must not raise

	def test_entry_producing_nothing_is_ignored(self):
		doc = self._entry([self._consumed()])
		check_consumption(doc)  # material issue style — nothing to fund

	def test_non_manufacture_entry_is_untouched(self):
		doc = self._entry([self._produced(self.item_rate)], purpose="Material Receipt")
		check_consumption(doc)  # a receipt legitimately has no consumption

	# ------------------------------------------------------------------
	# Guard 1 — the role-gated override
	# ------------------------------------------------------------------
	def test_override_by_stock_manager_allows_submit(self):
		doc = self._entry([self._produced(self.item_rate)])
		doc.set(OVERRIDE_FIELD, 1)
		with unittest.mock.patch("frappe.get_roles", return_value=["Stock Manager"]), \
			unittest.mock.patch.object(type(doc), "add_comment", create=True) as comment:
			check_consumption(doc)
		comment.assert_called_once()  # the override is written to the timeline

	def test_override_by_unprivileged_user_is_refused(self):
		doc = self._entry([self._produced(self.item_rate)])
		doc.set(OVERRIDE_FIELD, 1)
		with unittest.mock.patch("frappe.get_roles", return_value=["Stock User"]):
			with self.assertRaises(frappe.ValidationError) as cm:
				check_consumption(doc)
		self.assertIn("Only a", str(cm.exception))

	# ------------------------------------------------------------------
	# Guard 2 — amount-in-rate (the MAT-STE-40604 defect)
	# ------------------------------------------------------------------
	def test_absurd_rate_is_blocked(self):
		# mirrors MAT-STE-40604: a rate thousands of times the real one
		doc = self._entry([self._produced(self.item_rate * (RATE_BLOCK_MULTIPLE + 500))])
		with self.assertRaises(frappe.ValidationError) as cm:
			check_rate_sanity(doc)
		msg = str(cm.exception)
		self.assertIn("times the known rate", msg)
		self.assertIn("Amount column", msg)  # tells the user what they did wrong

	def test_normal_rate_passes(self):
		doc = self._entry([self._produced(self.item_rate * 1.2)])
		check_rate_sanity(doc)  # must not raise

	def test_moderately_high_rate_warns_but_saves(self):
		frappe.clear_messages()
		doc = self._entry([self._produced(self.item_rate * 20)])
		check_rate_sanity(doc)  # warns only — must not raise
		log = " ".join(str(m) for m in (frappe.local.message_log or []))
		self.assertIn("times the known rate", log)

	def test_item_without_history_is_skipped(self):
		doc = self._entry([self._produced(999999)])
		doc.items[0].item_code = "___seplt_nonexistent_item___"
		check_rate_sanity(doc)  # no benchmark, so no opinion — must not raise

	def test_rate_check_ignores_non_manufacture(self):
		doc = self._entry(
			[self._produced(self.item_rate * (RATE_BLOCK_MULTIPLE + 500))], purpose="Material Receipt"
		)
		check_rate_sanity(doc)  # a receipt may legitimately carry any rate

	# ------------------------------------------------------------------
	# Wiring
	# ------------------------------------------------------------------
	def test_override_field_installed(self):
		self.assertTrue(
			frappe.db.exists("Custom Field", {"dt": "Stock Entry", "fieldname": OVERRIDE_FIELD})
		)

	def test_install_is_idempotent(self):
		install()
		install()
		self.assertEqual(
			frappe.db.count("Custom Field", {"dt": "Stock Entry", "fieldname": OVERRIDE_FIELD}), 1
		)
