# Copyright (c) 2026, Erpera and contributors
# For license information, please see license.txt

"""Job Card Summary Multi Workstation -- SO1-I133.

Why this report exists
----------------------
Raj reported that the Workstation filter on "JOB CARD SUMMARY V2" only accepts
one workstation at a time.

"JOB CARD SUMMARY V2" has no code of its own.  It is a saved view
(``report_type = "Custom Report"``, ``reference_report = "Job Card Summary"``)
holding 13 saved columns and a set of saved filters; its ``javascript`` /
``query`` / ``report_script`` fields are all empty.  Its filter UI therefore
comes entirely from ERPNext core, where Workstation is declared as a single
value Link field (erpnext/manufacturing/report/job_card_summary/
job_card_summary.js:73-78).  There is no setting that changes that.

Core cannot be edited -- ``erpnext`` is shared by every site on this bench --
so the multi-select lives here instead, and ``install()`` below re-points the
saved view at it.  Raj keeps the report name and his 13 columns; only the
Workstation control changes.

Approach: no logic is copied
----------------------------
Columns, row building, chart and the total row all come from core, unchanged,
by calling ``core_execute`` directly.  The only thing this module does is
rewrite one filter value on the way in.

That works because of how core groups its filters
(erpnext/manufacturing/report/job_card_summary/job_card_summary.py:39-45)::

    for field in ["work_order", "production_item"]:
        if filters.get(field):
            query_filters[field] = ("in", filters.get(field))

    for field in ["workstation", "operation", "status", "company"]:
        if filters.get(field):
            query_filters[field] = filters.get(field)

The second loop copies the filter value into ``frappe.get_all``'s filter dict
*verbatim*, and ``["in", [...]]`` is a valid ``frappe.get_all`` filter value.
So handing core ``workstation = ["in", ["AN-01", "LN-1"]]`` produces exactly
the query core would have produced had Workstation been in the first group --
without touching core and without a second copy of the query to keep in sync.

The coupling to core's grouping is pinned by
``test_job_card_summary_multi_workstation.TestCoreContract``: if a future
ERPNext moves ``workstation`` into the first loop, the value would be wrapped
twice and that test fails loudly rather than the report silently returning
nothing.

Empty / absent Workstation is untouched: the key is removed, core's
``if filters.get(field)`` is False, and no workstation condition is added --
byte-identical behaviour to today.
"""

from __future__ import annotations

import frappe

from erpnext.manufacturing.report.job_card_summary.job_card_summary import execute as core_execute

# Filters this report turns into `IN (...)` conditions.  SO1-I133 asks for
# Workstation only.
#
# If Raj later wants the other two: "operation" is the same one-word change here
# plus flipping its control in the .js.  "status" is NOT -- core hides the whole
# Status column whenever a status filter has a value (job_card_summary.py:137-140),
# so selecting two statuses would drop the column that tells them apart, and core
# also relabels every non-Completed row as "Open" on the way out
# (job_card_summary.py:70-71).  Both would need answering first.
MULTI_SELECT_FILTERS = ("workstation",)

# The saved view Raj uses, and the report it shipped pointing at.
CUSTOM_REPORT = "JOB CARD SUMMARY V2"
CORE_REPORT = "Job Card Summary"
THIS_REPORT = "Job Card Summary Multi Workstation"


def execute(filters=None):
	return core_execute(normalise_multi_select_filters(filters))


def normalise_multi_select_filters(filters=None):
	"""Return a copy of ``filters`` with the multi-select fields as ``["in", [...]]``.

	A copy, never the caller's dict: ``frappe.desk.query_report.run`` hands the
	saved view's ``custom_filters`` straight to the report and then returns that
	same object to the browser (query_report.py:224, 247).  Mutating it in place
	would send ``workstation: ["in", [...]]`` back as the field's value and
	corrupt the filter control on screen.
	"""
	# core reads `filters.from_date` / `filters.to_date` as attributes, so the
	# copy has to stay a _dict (job_card_summary.py:23).
	filters = frappe._dict(filters or {})

	for fieldname in MULTI_SELECT_FILTERS:
		values = as_value_list(filters.get(fieldname))
		if values:
			filters[fieldname] = ["in", values]
		else:
			# nothing selected -> no condition at all, i.e. today's behaviour
			filters.pop(fieldname, None)

	return filters


def as_value_list(value) -> list:
	"""Coerce whatever the filter holds into a clean list of values.

	MultiSelectList sends a list, but the same filter used to be a Link, so a
	saved view or a bookmarked URL can still carry a bare string.  That is
	wrapped rather than split on commas -- ``frappe.get_all`` would comma-split
	it (frappe/model/db_query.py:880-887), which would silently break a
	workstation whose name contains a comma.
	"""
	if value is None or isinstance(value, bool):
		return []

	if isinstance(value, str):
		value = value.strip()
		return [value] if value else []

	if isinstance(value, list | tuple | set):
		return [v for v in value if v not in (None, "")]

	return [value]


def install():
	"""Point the saved "JOB CARD SUMMARY V2" view at this report.

	Runs from the ``after_migrate`` hook so the re-point survives every redeploy
	and never has to be done by hand on the live site.  Idempotent, and a no-op
	on any site that does not have the saved view (the local bench, for one).
	"""
	current = frappe.db.get_value(
		"Report", CUSTOM_REPORT, ["report_type", "reference_report"], as_dict=True
	)

	if not current:
		return  # saved view does not exist on this site

	if current.report_type != "Custom Report":
		return  # not a saved view any more -- do not touch someone else's report

	if current.reference_report != CORE_REPORT:
		# already re-pointed (the second and every later migrate), or somebody
		# deliberately pointed it somewhere else.  Either way, leave it alone.
		return

	if not frappe.db.exists("Report", THIS_REPORT):
		# defensive: this app's reports are synced earlier in the same migrate,
		# so this should never happen -- but re-pointing at a missing report
		# would break the saved view outright.
		return

	# db.set_value rather than doc.save(): exactly one column changes, and a
	# full save would re-run the Report doctype's own side effects on Raj's
	# view -- role defaults, json rewriting, and (on a developer_mode bench)
	# promoting a blank is_standard to "Yes" and exporting the doc to disk
	# (frappe/core/doctype/report/report.py:60-64, 127-133, 157-164).
	frappe.db.set_value("Report", CUSTOM_REPORT, "reference_report", THIS_REPORT)
	frappe.clear_document_cache("Report", CUSTOM_REPORT)
	print(f"seplt: {CUSTOM_REPORT} re-pointed to {THIS_REPORT} (SO1-I133)")
