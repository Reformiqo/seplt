"""Tests for the Item "Tube Grams" field type change -- SO1-I124.

The field (Item.custom_tube_grams) existed on the live site since 2024-11-07
but was never tracked by this app -- it carried ``module = None``, which the
Custom Field fixtures filter in hooks.py (``module in ("Seplt")``) silently
excludes from every export. It is added to ``fixtures/custom_field.json``
here for the first time, alongside the requested type change, so both are
now version controlled and survive every migrate rather than living only in
the site's database.

Existing data: 1,115 Items on the live site (174 on this bench) already carry
a value in this field, in at least 48 different raw shapes (``5GM``, ``30GMS``,
``1KG``, ``3.5GM``, bare ``30``, ``NOS``, and several ``*ML`` values that are not
a gram measurement at all) -- none of which exactly match the 15 values this
ticket specifies as the new Select options. Converting the field type does
not delete or rewrite any of that data (Frappe's fixture sync only changes
the Custom Field row, never touches `tabItem`), so nothing is lost -- but a
value that isn't one of the 15 options won't show as selected in the new
dropdown until someone repicks it or the data is normalised, and no mapping
for the out-of-pattern values was given, so none is invented here. See the
ticket thread for the reconciliation decision.
"""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

FIELD = "custom_tube_grams"
EXPECTED_OPTIONS = [
	"2 GM",
	"3 GM",
	"5 GM",
	"7 GM",
	"10 GM",
	"15 GM",
	"20 GM",
	"25 GM",
	"30 GM",
	"35 GM",
	"40 GM",
	"50 GM",
	"60 GM",
	"70 GM",
	"100 GM",
]


class TestTubeGramsFieldType(IntegrationTestCase):
	def test_field_is_a_select(self):
		meta = frappe.get_meta("Item")
		self.assertTrue(meta.has_field(FIELD))
		self.assertEqual(meta.get_field(FIELD).fieldtype, "Select")

	def test_options_match_the_ticket_exactly(self):
		options = frappe.get_meta("Item").get_field(FIELD).options
		self.assertEqual(options.splitlines(), EXPECTED_OPTIONS)

	def test_field_now_belongs_to_this_app(self):
		"""Otherwise the next `bench export-fixtures` silently drops it again
		-- the exact way it went untracked for two years in the first place."""
		self.assertEqual(frappe.db.get_value("Custom Field", "Item-custom_tube_grams", "module"), "Seplt")

	def test_position_is_unchanged(self):
		"""The type change must not have moved the field on the form."""
		self.assertEqual(
			frappe.get_meta("Item").get_field(FIELD).insert_after, "custom_customer_art_code"
		)

	def test_existing_data_is_untouched(self):
		"""The fixture changes the Custom Field row only. No value on any
		Item -- matching one of the 15 options or not -- is rewritten,
		normalised or dropped by this change."""
		before = frappe.db.sql(
			"""SELECT `{field}`, COUNT(*) n FROM `tabItem`
			WHERE IFNULL(`{field}`, '') != '' GROUP BY `{field}`""".format(field=FIELD),
			as_dict=True,
		)
		total_before = sum(r.n for r in before)

		# Re-apply the fixture the exact way `bench migrate` does, to prove
		# re-running it is not what silently touches data.
		from frappe.utils.fixtures import sync_fixtures

		sync_fixtures(app="seplt")

		after = frappe.db.sql(
			"""SELECT `{field}`, COUNT(*) n FROM `tabItem`
			WHERE IFNULL(`{field}`, '') != '' GROUP BY `{field}`""".format(field=FIELD),
			as_dict=True,
		)
		self.assertEqual(sum(r.n for r in after), total_before)
		self.assertEqual({r[FIELD] for r in after}, {r[FIELD] for r in before})
