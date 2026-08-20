"""Allow non-GST charge rows on subcontracting Stock Entries.

India Compliance blocks non-GST charges two independent ways on Stock Entry /
Subcontracting Order / Subcontracting Receipt (india_compliance/hooks.py
``doc_events``):

  * validate    -> gst_india.utils.taxes_controller.validate_taxes() throws
                   "Row #N: Only GST accounts are allowed in {doctype}." for any
                   tax row whose account_head is not a GST account from GST
                   Settings.
  * before_save -> gst_india.overrides.subcontracting_transaction.before_save()
                   throws for Charge Type = "Actual" outright.

``validate`` runs first, so the account error masks the charge-type one; both
have to be relaxed to book a freight / loading / handling charge here.

Why this is safe: India Compliance derives the CGST/SGST/IGST/cess breakup from
``gst_tax_type``, and set_gst_tax_type() (gst_india/overrides/transaction.py)
leaves that as None on non-GST accounts. CustomItemGSTDetails skips every row
with a falsy gst_tax_type, so these rows can never enter the GST breakup on the
e-Waybill or in ITC-04. They only reach ``total_taxes`` / ``base_grand_total``
via CustomTaxController.update_tax_amount() — the intended treatment for
freight in the e-Waybill's total value.

Both checks are bypassed outright — no account or charge-type combination is
rejected any more. Note the one real consequence: on a GST account, "Actual"
sets tax_amount directly and leaves item_wise_tax_rates empty (see
CustomTaxController.set_item_wise_tax_rates / update_tax_amount), so that GST
row contributes no per-item rate to the e-Waybill breakup. Keep GST rows on
"On Net Total" / "On Item Quantity" and use "Actual" for non-GST charges.

Installed from hooks.py via a before_validate doc_event on the three affected
doctypes; see apply(). Nothing runs on requests that never touch one of them.
"""

import frappe
from frappe import _

# Patch target. Kept here so assert_patch_targets() can fail loudly if a future
# India Compliance release renames or moves either function.
TARGET_MODULE = "india_compliance.gst_india.overrides.subcontracting_transaction"
TARGET_FUNCTIONS = ("validate_taxes", "before_save")

_PATCHED = False

# India Compliance's own implementations, captured before they are rebound. The
# relaxations below delegate back to these on every site that does not have seplt
# installed — see _is_relaxed().
_ORIGINALS = {}


def _is_relaxed():
	"""Whether the relaxation applies to the site serving the current request.

	The patch rebinds a module global, and Python caches modules per *process*,
	not per site. A bench worker serves every site on the bench from the same
	interpreter, so an unguarded rebind reaches sites that never asked for it:
	once any request for a seplt site runs apply(), that worker's India
	Compliance stays relaxed for whatever site it handles next. Workers that
	never served a seplt site stay unpatched, so the same site would validate
	differently from one request to the next depending on which worker answered.

	Deciding per call instead keeps the relaxation to the sites that installed
	seplt. get_installed_apps() is per-site and cached on frappe.local, so this
	costs nothing per document.
	"""
	return "seplt" in frappe.get_installed_apps()


def _validate_taxes(doc):
	"""Replaces India Compliance's validate_taxes — non-GST accounts pass.

	The original does nothing but throw for tax rows with a non-zero amount on
	a non-GST account, so the relaxed version is a no-op.
	"""
	if not _is_relaxed():
		return _ORIGINALS["validate_taxes"](doc)

	return


def _before_save(doc, method=None):
	"""Replaces India Compliance's before_save.

	The original's Charge Type check is dropped entirely — "Actual" is allowed
	on every account, GST ones included. What remains is the original's "clear
	the taxes table when no e-Waybill applies" behaviour, which has to stay:
	dropping it would leave stale tax rows on non-e-Waybill entries.
	"""
	if not _is_relaxed():
		return _ORIGINALS["before_save"](doc, method)

	from india_compliance.gst_india.overrides.subcontracting_transaction import (
		is_e_waybill_applicable,
	)

	if not is_e_waybill_applicable(doc):
		doc.taxes_and_charges = ""
		doc.taxes = []
		return


def apply(doc=None, method=None):
	"""Install the patches. Idempotent; called before each affected document validates.

	``doc`` / ``method`` are the doc_event signature and are unused — the patch is
	process-wide, and which site it applies to is decided later in _is_relaxed().

	Both entry points are resolved by attribute lookup at call time — the
	doc_event goes through frappe.get_attr(), and India Compliance's validate()
	looks up ``validate_taxes`` as a module global — so rebinding on the module
	is enough, with no import-order juggling.

	Installing is process-wide and unconditional; whether the relaxation actually
	takes effect is decided per call in _is_relaxed(), which is what keeps the
	other sites on this bench on India Compliance's stock validation.
	"""
	global _PATCHED

	if _PATCHED:
		return

	try:
		from india_compliance.gst_india.overrides import subcontracting_transaction
	except ImportError:
		# india_compliance not installed on this bench — nothing to patch.
		_PATCHED = True
		return

	# Captured before rebinding, and only from a function that is not already
	# ours: _PATCHED is per process, so a reload or a second import must not
	# capture the previous patch and recurse.
	for name, replacement in (
		("validate_taxes", _validate_taxes),
		("before_save", _before_save),
	):
		original = getattr(subcontracting_transaction, name)
		if original.__module__ != __name__:
			_ORIGINALS[name] = original

		setattr(subcontracting_transaction, name, replacement)

	_PATCHED = True


def assert_patch_targets():
	"""Fail the migrate if India Compliance moved what we patch.

	A monkeypatch that silently stops applying is worse than one that breaks:
	the validation would quietly come back and nobody would know why the entry
	stopped saving. Called from hooks.after_migrate.
	"""
	try:
		from india_compliance.gst_india.overrides import subcontracting_transaction
	except ImportError:
		return

	missing = [fn for fn in TARGET_FUNCTIONS if not hasattr(subcontracting_transaction, fn)]

	if not missing:
		return

	frappe.throw(
		_(
			"seplt patches {0} in {1}, but {2} no longer exists there. Review"
			" seplt/overrides/india_compliance_taxes.py against the installed"
			" India Compliance version."
		).format(", ".join(TARGET_FUNCTIONS), TARGET_MODULE, ", ".join(missing))
	)
