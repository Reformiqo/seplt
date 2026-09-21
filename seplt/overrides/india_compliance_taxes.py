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

Two India Compliance layouts
----------------------------
The two checks above have moved once, and this module patches both places:

  * legacy (<= 16.8.x): ``validate_taxes`` and ``before_save`` are module-level
    functions in ``gst_india.overrides.subcontracting_transaction``, which is
    where the doc_events point. Rebinding the module globals is enough.

  * controller (>= 16.9.0): the doc_events still name ``validate`` /
    ``before_save``, but those now hand off to a controller class. The
    non-GST account check is ``validate_taxes()`` called as a *global* of
    ``gst_india.utils.custom_transaction_controller`` from
    ``CustomEwaybillController.validate``, and the "Actual" charge-type check
    is ``CustomEwaybillController.before_save``.

The controller layout needs more care than a plain rebind, because
``CustomEwaybillController`` is not ours alone -- Asset Movement uses it too
(gst_india/overrides/asset_movement.py). So:

  * ``_validate_taxes`` only short-circuits for the three doctypes above and
    hands every other doctype to India Compliance's own function, and
  * ``before_save`` is replaced on ``SubcontractingController`` -- the base
    shared by exactly Stock Entry / Subcontracting Order / Subcontracting
    Receipt -- and not on ``CustomEwaybillController``, so Asset Movement keeps
    India Compliance's own ``before_save``.
"""

from importlib import import_module

import frappe
from frappe import _

SUBCONTRACTING_MODULE = "india_compliance.gst_india.overrides.subcontracting_transaction"
CONTROLLER_MODULE = "india_compliance.gst_india.utils.custom_transaction_controller"

# Kept for the migrate guard's message and for anyone grepping for the old names.
TARGET_MODULE = SUBCONTRACTING_MODULE
TARGET_FUNCTIONS = ("validate_taxes", "before_save")

# The only doctypes seplt relaxes. India Compliance's controller layout shares
# `validate_taxes` with Asset Movement, which must keep the stock behaviour.
RELAXED_DOCTYPES = ("Stock Entry", "Subcontracting Order", "Subcontracting Receipt")

LEGACY = "legacy"  # module-level functions, India Compliance <= 16.8.x
CONTROLLER = "controller"  # controller classes, India Compliance >= 16.9.0

_PATCHED = False
# apply() reports an unrecognised layout once per process, not once per save.
_WARNED = False

# India Compliance's own implementations, captured before they are rebound. The
# relaxations below delegate back to these on every site that does not have seplt
# installed, and for any doctype outside RELAXED_DOCTYPES -- see _is_relaxed().
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
	"""Replaces India Compliance's validate_taxes -- non-GST accounts pass.

	The original does nothing but throw for tax rows with a non-zero amount on
	a non-GST account, so the relaxed version is a no-op -- for the three
	doctypes on a seplt site, and only those. Anything else (another site on
	this bench, or another doctype behind the same India Compliance controller,
	Asset Movement today) gets India Compliance's own check.
	"""
	if doc.doctype not in RELAXED_DOCTYPES or not _is_relaxed():
		return _ORIGINALS["validate_taxes"](doc)

	return


def _before_save(doc, method=None):
	"""Replaces India Compliance's before_save (legacy layout).

	The original's Charge Type check is dropped entirely -- "Actual" is allowed
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


def _controller_before_save(self):
	"""Replaces ``SubcontractingController.before_save`` (controller layout).

	Same contract as _before_save above: no Charge Type check, but the
	"clear the taxes table when no e-Waybill applies" behaviour stays.
	"""
	if not _is_relaxed():
		return _ORIGINALS["before_save"](self)

	if not self.is_e_waybill_applicable():
		self.doc.taxes_and_charges = ""
		self.doc.taxes = []
		return


def _load_targets():
	"""India Compliance's two modules, or ``(None, None)`` when it is not installed.

	``custom_transaction_controller`` only exists from 16.9.0; on the legacy
	layout it is simply absent and comes back as None.
	"""
	try:
		subcontracting = import_module(SUBCONTRACTING_MODULE)
	except ImportError:
		return None, None

	try:
		controller = import_module(CONTROLLER_MODULE)
	except ImportError:
		controller = None

	return subcontracting, controller


def _detect(subcontracting, controller):
	"""Which India Compliance layout is installed, and what of it is missing.

	Returns ``(layout, missing)``. ``missing`` is empty when every name this
	module patches is where it is expected; otherwise it lists the ones that
	are not, as dotted names, for the migrate guard's message.

	The controller layout is recognised by ``SubcontractingController`` on the
	subcontracting module; anything without it is checked against the legacy
	layout, which is also what a future India Compliance that moves things
	again will be judged against -- and fail, loudly, in assert_patch_targets().
	"""
	sub_name = SUBCONTRACTING_MODULE.rsplit(".", 1)[-1]

	if hasattr(subcontracting, "SubcontractingController"):
		klass = subcontracting.SubcontractingController
		missing = []

		if controller is None or not hasattr(controller, "validate_taxes"):
			missing.append("custom_transaction_controller.validate_taxes")

		for name in ("before_save", "is_e_waybill_applicable"):
			if not hasattr(klass, name):
				missing.append(f"{sub_name}.SubcontractingController.{name}")

		return CONTROLLER, missing

	missing = [
		f"{sub_name}.{name}"
		for name in ("validate_taxes", "before_save", "is_e_waybill_applicable")
		if not hasattr(subcontracting, name)
	]
	return LEGACY, missing


def _install(subcontracting, controller, layout):
	"""Rebind India Compliance's functions for ``layout``. Idempotent.

	Split out of apply() so the tests can hand it stand-in modules; there is no
	other reason for the indirection.

	Originals are captured before rebinding, and only from a function that is
	not already ours: _PATCHED is per process, so a reload or a second import
	must not capture the previous patch and recurse.
	"""
	if layout == CONTROLLER:
		klass = subcontracting.SubcontractingController
		targets = (
			(controller, "validate_taxes", _validate_taxes, "validate_taxes"),
			(klass, "before_save", _controller_before_save, "before_save"),
		)
	else:
		targets = (
			(subcontracting, "validate_taxes", _validate_taxes, "validate_taxes"),
			(subcontracting, "before_save", _before_save, "before_save"),
		)

	for owner, attribute, replacement, key in targets:
		original = getattr(owner, attribute)
		if original.__module__ != __name__:
			_ORIGINALS[key] = original

		setattr(owner, attribute, replacement)


def apply(doc=None, method=None):
	"""Install the patches. Idempotent; called before each affected document validates.

	``doc`` / ``method`` are the doc_event signature and are unused -- the patch is
	process-wide, and which site it applies to is decided later in _is_relaxed().

	Both entry points are resolved by attribute lookup at call time -- the
	doc_event goes through frappe.get_attr(), and India Compliance looks up
	``validate_taxes`` as a module global and ``before_save`` as a method -- so
	rebinding is enough, with no import-order juggling.

	Installing is process-wide and unconditional; whether the relaxation actually
	takes effect is decided per call in _is_relaxed(), which is what keeps the
	other sites on this bench on India Compliance's stock validation.

	An unrecognised India Compliance layout is not patched, and does not raise
	here: this runs inside every Stock Entry save, and stock validation coming
	back is a far smaller problem than nobody being able to save. The place that
	refuses is assert_patch_targets(), on migrate.
	"""
	global _PATCHED, _WARNED

	if _PATCHED:
		return

	subcontracting, controller = _load_targets()

	if subcontracting is None:
		# india_compliance not installed on this bench -- nothing to patch.
		_PATCHED = True
		return

	layout, missing = _detect(subcontracting, controller)

	if missing:
		if not _WARNED:
			_WARNED = True
			frappe.log_error(
				title="seplt: India Compliance relaxation NOT applied",
				message=(
					f"Unrecognised India Compliance layout ({layout}); not found: {', '.join(missing)}. "
					"Non-GST charge rows on Stock Entry / Subcontracting Order / Subcontracting Receipt "
					"will be rejected again. Review seplt/overrides/india_compliance_taxes.py."
				),
			)
		return  # not marked patched, so a later call re-checks

	_install(subcontracting, controller, layout)
	_PATCHED = True


def assert_patch_targets():
	"""Fail the migrate if India Compliance moved what we patch.

	A monkeypatch that silently stops applying is worse than one that breaks:
	the validation would quietly come back and nobody would know why the entry
	stopped saving. Called from hooks.after_migrate.
	"""
	subcontracting, controller = _load_targets()

	if subcontracting is None:
		return

	layout, missing = _detect(subcontracting, controller)

	if not missing:
		return

	frappe.throw(
		_(
			"seplt patches India Compliance's non-GST tax validation and Charge Type check"
			" for Stock Entry / Subcontracting Order / Subcontracting Receipt, but {0} no"
			" longer exists where it is expected ({1} layout). Review"
			" seplt/overrides/india_compliance_taxes.py against the installed"
			" India Compliance version."
		).format(", ".join(missing), layout)
	)
