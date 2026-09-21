"""Tests for seplt.overrides.india_compliance_taxes.

Background
----------
On 2026-09-21 the live migrate failed in ``assert_patch_targets``:

    seplt patches validate_taxes, before_save in
    india_compliance.gst_india.overrides.subcontracting_transaction, but
    validate_taxes no longer exists there.

India Compliance 16.9.0 moved the Stock Entry / Subcontracting Order /
Subcontracting Receipt validation out of module-level functions into controller
classes (``CustomEwaybillController``), so the two functions this module
patches were no longer where it looked.  The guard did exactly its job -- but
the override itself had no tests, so nothing told us before the deploy.

What these tests pin
--------------------
* ``TestInstalledIndiaCompliance`` -- the contract with whatever India
  Compliance is *actually installed* on the bench running the tests.  This is
  the one that fails in CI, not on the live migrate, the next time India
  Compliance moves something.
* ``TestControllerLayout`` -- the >= 16.9.0 shape, built as stand-in modules
  that mirror the real ones (checked against the v16.9.1 sources), so the
  behaviour is covered even on a bench still running an older India Compliance.
* ``TestLegacyLayout`` -- the <= 16.8.x shape, same way.
* ``TestLayoutGuard`` -- ``assert_patch_targets`` refusing, and ``apply``
  not raising, on a layout nobody has seen.

Every stand-in below keeps India Compliance's real structure on purpose: the
patch relies on *where* names are looked up (a module global at call time, a
method resolved through the class), and a fake that resolved them differently
would prove nothing.
"""

from __future__ import annotations

import types
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from seplt.overrides import india_compliance_taxes as override
from seplt.overrides.india_compliance_taxes import (
	CONTROLLER,
	LEGACY,
	RELAXED_DOCTYPES,
	_detect,
	_install,
	_load_targets,
	apply,
	assert_patch_targets,
)

GST_ACCOUNTS = ("Input Tax CGST - X", "Input Tax SGST - X")


def tax_row(account_head="Freight Charges - X", charge_type="Actual", tax_amount=500.0, idx=1):
	return frappe._dict(
		idx=idx, account_head=account_head, charge_type=charge_type, tax_amount=tax_amount
	)


def make_doc(doctype="Stock Entry", *taxes):
	return frappe._dict(
		doctype=doctype,
		company="Test Company",
		taxes=list(taxes) or [tax_row()],
		taxes_and_charges="Some Template",
	)


@contextmanager
def other_site():
	"""The request is for a site that does not have seplt installed."""
	with patch("frappe.get_installed_apps", return_value=["frappe", "erpnext"]):
		yield


@contextmanager
def seplt_site():
	with patch("frappe.get_installed_apps", return_value=["frappe", "erpnext", "seplt"]):
		yield


@contextmanager
def isolated_originals():
	"""The fakes below capture their own 'originals'.  Restore the real ones after,
	or a later test would delegate to a fake."""
	with patch.dict(override._ORIGINALS, clear=True):
		yield


# --------------------------------------------------------------------------
# Stand-ins that mirror India Compliance's two layouts
# --------------------------------------------------------------------------


def _original_validate_taxes(doc):
	"""India Compliance's own check (taxes_controller.validate_taxes)."""
	for tax in doc.taxes:
		if not tax.tax_amount:
			continue
		if tax.account_head not in GST_ACCOUNTS:
			frappe.throw(f"Row #{tax.idx}: Only GST accounts are allowed in {doc.doctype}.")


def _throw_on_actual(taxes):
	for row in taxes:
		if row.charge_type == "Actual":
			frappe.throw(f"Tax Row #{row.idx}: Charge Type cannot be {row.charge_type}.")


def make_controller_layout(e_waybill_applicable=True):
	"""``(subcontracting_module, controller_module)`` shaped like IC >= 16.9.0.

	* ``custom_transaction_controller.validate_taxes`` is a module global that
	  ``CustomEwaybillController.validate`` looks up at call time.
	* ``CustomEwaybillController.before_save`` carries the Charge Type check.
	* Stock Entry / Subcontracting Order / Subcontracting Receipt controllers
	  share ``SubcontractingController``; Asset Movement extends the base
	  directly.
	"""
	controller = types.ModuleType("fake_custom_transaction_controller")
	controller.validate_taxes = _original_validate_taxes

	class CustomEwaybillController:
		def __init__(self, doc):
			self.doc = doc

		def is_e_waybill_applicable(self):
			return e_waybill_applicable

		def validate(self):
			# `validate_taxes(self.doc)` in the real one: a global of that module
			controller.validate_taxes(self.doc)

		def before_save(self):
			if not self.is_e_waybill_applicable():
				self.doc.taxes_and_charges = ""
				self.doc.taxes = []
				return
			_throw_on_actual(self.doc.taxes)

	controller.CustomEwaybillController = CustomEwaybillController

	subcontracting = types.ModuleType("fake_subcontracting_transaction")

	class SubcontractingController(CustomEwaybillController):
		pass

	class StockEntryController(SubcontractingController):
		DOCTYPE = "Stock Entry"

	class SubcontractingReceiptController(SubcontractingController):
		DOCTYPE = "Subcontracting Receipt"

	class AssetMovementController(CustomEwaybillController):
		DOCTYPE = "Asset Movement"

	subcontracting.SubcontractingController = SubcontractingController
	subcontracting.StockEntryController = StockEntryController
	subcontracting.SubcontractingReceiptController = SubcontractingReceiptController
	subcontracting.AssetMovementController = AssetMovementController

	return subcontracting, controller


def make_legacy_layout():
	"""``subcontracting_transaction`` shaped like IC <= 16.8.x: module-level
	``validate_taxes`` / ``before_save`` / ``is_e_waybill_applicable``."""
	subcontracting = types.ModuleType("fake_subcontracting_transaction_legacy")
	subcontracting.validate_taxes = _original_validate_taxes
	subcontracting.is_e_waybill_applicable = lambda doc: True

	def before_save(doc, method=None):
		if not subcontracting.is_e_waybill_applicable(doc):
			doc.taxes_and_charges = ""
			doc.taxes = []
			return
		_throw_on_actual(doc.taxes)

	subcontracting.before_save = before_save
	return subcontracting


# --------------------------------------------------------------------------
# The contract with the India Compliance that is actually installed
# --------------------------------------------------------------------------


class TestInstalledIndiaCompliance(IntegrationTestCase):
	def test_every_patch_target_exists_in_the_installed_version(self):
		"""The test that would have caught the failed migrate before it shipped.

		Whatever layout the bench has, everything this module patches must be
		where it expects -- this is what ``assert_patch_targets`` checks on
		migrate, run here in CI instead.
		"""
		subcontracting, controller = _load_targets()
		self.assertIsNotNone(subcontracting, "india_compliance is not installed on this bench")

		layout, missing = _detect(subcontracting, controller)
		self.assertEqual(missing, [], f"India Compliance ({layout} layout) moved: {missing}")

		assert_patch_targets()  # must not raise

	def test_apply_patches_the_installed_layout_and_is_idempotent(self):
		apply()
		apply()
		apply()

		subcontracting, controller = _load_targets()
		layout, _missing = _detect(subcontracting, controller)

		if layout == CONTROLLER:
			self.assertIs(controller.validate_taxes, override._validate_taxes)
			self.assertIs(
				subcontracting.SubcontractingController.before_save,
				override._controller_before_save,
			)
		else:
			self.assertIs(subcontracting.validate_taxes, override._validate_taxes)
			self.assertIs(subcontracting.before_save, override._before_save)

		# the originals it delegates to were captured, and are not our own patch
		for key in ("validate_taxes", "before_save"):
			self.assertIn(key, override._ORIGINALS)
			self.assertNotEqual(override._ORIGINALS[key].__module__, override.__name__)

	def installed_validate_taxes(self):
		subcontracting, controller = _load_targets()
		layout, _missing = _detect(subcontracting, controller)
		return controller.validate_taxes if layout == CONTROLLER else subcontracting.validate_taxes

	def test_real_original_would_reject_a_non_gst_charge(self):
		"""Guards the next test against being vacuous: India Compliance's own
		check really does throw for the row we then show being allowed."""
		apply()
		with self.assertRaises(frappe.ValidationError):
			override._ORIGINALS["validate_taxes"](make_doc("Stock Entry"))

	def test_non_gst_charge_is_allowed_on_a_seplt_site(self):
		apply()
		validate_taxes = self.installed_validate_taxes()

		with seplt_site():
			for doctype in RELAXED_DOCTYPES:
				with self.subTest(doctype=doctype):
					self.assertIsNone(validate_taxes(make_doc(doctype)))

	def test_other_sites_keep_india_compliances_own_check(self):
		"""The patch is process-wide, so the per-call site check is what stops
		it leaking onto other sites served by the same worker."""
		apply()
		validate_taxes = self.installed_validate_taxes()

		with other_site():
			for doctype in RELAXED_DOCTYPES:
				with self.subTest(doctype=doctype), self.assertRaises(frappe.ValidationError):
					validate_taxes(make_doc(doctype))

	def test_other_doctypes_keep_india_compliances_own_check(self):
		"""Asset Movement shares India Compliance's controller in 16.9.0+; it
		must not be relaxed just because seplt is installed on the site."""
		apply()
		validate_taxes = self.installed_validate_taxes()

		with seplt_site(), self.assertRaises(frappe.ValidationError):
			validate_taxes(make_doc("Asset Movement"))


# --------------------------------------------------------------------------
# Controller layout (India Compliance >= 16.9.0)
# --------------------------------------------------------------------------


class TestControllerLayout(IntegrationTestCase):
	def install(self, **layout_kwargs):
		subcontracting, controller = make_controller_layout(**layout_kwargs)
		layout, missing = _detect(subcontracting, controller)
		self.assertEqual((layout, missing), (CONTROLLER, []))
		_install(subcontracting, controller, layout)
		return subcontracting

	def setUp(self):
		super().setUp()
		patcher = isolated_originals()
		patcher.__enter__()
		self.addCleanup(patcher.__exit__, None, None, None)

	def test_stand_ins_reject_a_non_gst_charge_before_patching(self):
		"""Baseline: without the patch these stand-ins behave like stock India
		Compliance -- so the tests below prove the patch, not the fake."""
		subcontracting, _controller = make_controller_layout()
		with self.assertRaises(frappe.ValidationError):
			subcontracting.StockEntryController(make_doc("Stock Entry")).validate()
		with self.assertRaises(frappe.ValidationError):
			subcontracting.StockEntryController(make_doc("Stock Entry")).before_save()

	def test_non_gst_account_allowed_on_all_three_doctypes(self):
		subcontracting = self.install()
		with seplt_site():
			subcontracting.StockEntryController(make_doc("Stock Entry")).validate()
			subcontracting.SubcontractingReceiptController(make_doc("Subcontracting Receipt")).validate()

	def test_actual_charge_type_allowed_on_all_three_doctypes(self):
		subcontracting = self.install()
		with seplt_site():
			subcontracting.StockEntryController(make_doc("Stock Entry")).before_save()
			subcontracting.SubcontractingReceiptController(
				make_doc("Subcontracting Receipt")
			).before_save()

	def test_actual_charge_type_allowed_on_a_gst_account_too(self):
		"""The docstring's promise: 'Actual' is allowed on every account."""
		subcontracting = self.install()
		doc = make_doc("Stock Entry", tax_row(account_head=GST_ACCOUNTS[0], charge_type="Actual"))
		with seplt_site():
			subcontracting.StockEntryController(doc).before_save()

	def test_taxes_are_still_cleared_when_no_e_waybill_applies(self):
		"""What must survive the relaxation: stale tax rows are not left behind."""
		subcontracting = self.install(e_waybill_applicable=False)
		doc = make_doc("Stock Entry")

		with seplt_site():
			subcontracting.StockEntryController(doc).before_save()

		self.assertEqual(doc.taxes, [])
		self.assertEqual(doc.taxes_and_charges, "")

	def test_taxes_are_kept_when_an_e_waybill_applies(self):
		subcontracting = self.install(e_waybill_applicable=True)
		doc = make_doc("Stock Entry")

		with seplt_site():
			subcontracting.StockEntryController(doc).before_save()

		self.assertEqual(len(doc.taxes), 1)
		self.assertEqual(doc.taxes_and_charges, "Some Template")

	def test_asset_movement_is_not_relaxed(self):
		"""Asset Movement shares CustomEwaybillController and the module-level
		``validate_taxes`` with the three doctypes above.  It must keep India
		Compliance's behaviour on both checks."""
		subcontracting = self.install()
		doc = make_doc("Asset Movement")

		with seplt_site():
			with self.assertRaises(frappe.ValidationError):
				subcontracting.AssetMovementController(doc).validate()
			with self.assertRaises(frappe.ValidationError):
				subcontracting.AssetMovementController(doc).before_save()

	def test_other_sites_keep_both_of_india_compliances_checks(self):
		subcontracting = self.install()
		doc = make_doc("Stock Entry")

		with other_site():
			with self.assertRaises(frappe.ValidationError):
				subcontracting.StockEntryController(doc).validate()
			with self.assertRaises(frappe.ValidationError):
				subcontracting.StockEntryController(doc).before_save()

	def test_installing_twice_keeps_the_original_and_does_not_recurse(self):
		subcontracting, controller = make_controller_layout()
		_install(subcontracting, controller, CONTROLLER)
		first = dict(override._ORIGINALS)
		_install(subcontracting, controller, CONTROLLER)

		self.assertEqual(override._ORIGINALS, first)
		with other_site(), self.assertRaises(frappe.ValidationError):
			subcontracting.StockEntryController(make_doc("Stock Entry")).validate()  # no RecursionError


# --------------------------------------------------------------------------
# Legacy layout (India Compliance <= 16.8.x)
# --------------------------------------------------------------------------


class TestLegacyLayout(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		patcher = isolated_originals()
		patcher.__enter__()
		self.addCleanup(patcher.__exit__, None, None, None)

		self.subcontracting = make_legacy_layout()
		layout, missing = _detect(self.subcontracting, None)
		self.assertEqual((layout, missing), (LEGACY, []))
		_install(self.subcontracting, None, layout)

	def test_non_gst_account_and_actual_charge_allowed_on_a_seplt_site(self):
		doc = make_doc("Stock Entry")
		with seplt_site():
			self.subcontracting.validate_taxes(doc)
			self.subcontracting.before_save(doc)

	def test_other_sites_keep_india_compliances_own_checks(self):
		doc = make_doc("Stock Entry")
		with other_site():
			with self.assertRaises(frappe.ValidationError):
				self.subcontracting.validate_taxes(doc)
			with self.assertRaises(frappe.ValidationError):
				self.subcontracting.before_save(doc)

	def test_taxes_are_still_cleared_when_no_e_waybill_applies(self):
		"""The relaxed before_save asks India Compliance's own
		``is_e_waybill_applicable`` -- the real module's, not the stand-in's --
		so that is what is pointed at 'no' here."""
		doc = make_doc("Stock Entry")

		with (
			seplt_site(),
			patch(
				"india_compliance.gst_india.overrides.subcontracting_transaction.is_e_waybill_applicable",
				return_value=False,
			),
		):
			self.subcontracting.before_save(doc)

		self.assertEqual(doc.taxes, [])
		self.assertEqual(doc.taxes_and_charges, "")


# --------------------------------------------------------------------------
# What happens on a layout nobody has seen
# --------------------------------------------------------------------------


class TestLayoutGuard(IntegrationTestCase):
	def test_a_module_missing_the_legacy_names_is_reported(self):
		"""The exact failure on the live migrate: a subcontracting module that
		has neither the legacy functions nor the controller class."""
		empty = types.ModuleType("fake_subcontracting_transaction_moved")

		layout, missing = _detect(empty, None)

		self.assertEqual(layout, LEGACY)
		self.assertEqual(
			set(missing),
			{
				"subcontracting_transaction.validate_taxes",
				"subcontracting_transaction.before_save",
				"subcontracting_transaction.is_e_waybill_applicable",
			},
		)

	def test_controller_layout_without_validate_taxes_is_reported(self):
		subcontracting, controller = make_controller_layout()
		del controller.validate_taxes

		layout, missing = _detect(subcontracting, controller)

		self.assertEqual(layout, CONTROLLER)
		self.assertEqual(missing, ["custom_transaction_controller.validate_taxes"])

	def test_controller_layout_without_before_save_is_reported(self):
		subcontracting, controller = make_controller_layout()
		# `before_save` lives on the base class and reaches SubcontractingController by inheritance
		del controller.CustomEwaybillController.before_save

		layout, missing = _detect(subcontracting, controller)

		self.assertEqual(layout, CONTROLLER)
		self.assertEqual(missing, ["subcontracting_transaction.SubcontractingController.before_save"])

	def test_assert_patch_targets_refuses_and_names_what_moved(self):
		empty = types.ModuleType("fake_subcontracting_transaction_moved")

		with patch.object(override, "_load_targets", return_value=(empty, None)):
			with self.assertRaises(frappe.ValidationError) as ctx:
				assert_patch_targets()

		message = str(ctx.exception)
		self.assertIn("validate_taxes", message)
		self.assertIn("Review", message)

	def test_assert_patch_targets_passes_when_india_compliance_is_absent(self):
		with patch.object(override, "_load_targets", return_value=(None, None)):
			assert_patch_targets()  # nothing to patch, nothing to refuse

	def test_apply_does_not_raise_on_an_unrecognised_layout(self):
		"""apply() runs inside every Stock Entry save; it must not be what
		stops people saving.  It logs once and leaves stock validation in
		place -- the migrate guard is what refuses loudly."""
		empty = types.ModuleType("fake_subcontracting_transaction_moved")

		with (
			patch.object(override, "_PATCHED", False),
			patch.object(override, "_WARNED", False),
			patch.object(override, "_load_targets", return_value=(empty, None)),
			patch("frappe.log_error") as log_error,
		):
			apply()
			apply()
			apply()

		self.assertEqual(log_error.call_count, 1)
		self.assertIn("NOT applied", log_error.call_args.kwargs["title"])
