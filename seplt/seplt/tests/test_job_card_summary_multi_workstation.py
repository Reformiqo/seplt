"""Tests for Job Card Summary Multi Workstation -- SO1-I133.

Raj reported that the Workstation filter on "JOB CARD SUMMARY V2" only takes one
workstation.  These tests drive the exact path the browser drives --
``frappe.desk.query_report.get_script`` for the filter definitions and
``frappe.desk.query_report.run`` for the rows -- against the saved view's own
name, not just the python ``execute``.  A test that only called ``execute``
would pass even if the saved view were still pointing at core.

Every expected number is recomputed from the Job Card table in SQL, so the
assertions stay correct as the data on this site changes.
"""

from __future__ import annotations

import json

import frappe
from frappe.desk.query_report import get_script, run, save_report
from frappe.tests import IntegrationTestCase

from erpnext.manufacturing.report.job_card_summary.job_card_summary import (
	execute as core_execute,
)
from erpnext.manufacturing.report.job_card_summary.job_card_summary import (
	get_data as core_get_data,
)

from seplt.seplt.report.job_card_summary_multi_workstation.job_card_summary_multi_workstation import (
	CORE_REPORT,
	CUSTOM_REPORT,
	THIS_REPORT,
	execute,
	install,
	normalise_multi_select_filters,
)


def base_filters():
	"""Company + date window that actually has Job Cards on this site."""
	row = frappe.db.sql(
		"""SELECT company, MIN(posting_date) AS from_date, MAX(posting_date) AS to_date
		FROM `tabJob Card`
		WHERE docstatus < 2
		GROUP BY company
		ORDER BY COUNT(*) DESC
		LIMIT 1""",
		as_dict=True,
	)
	if not row:
		raise RuntimeError("no Job Cards on this site -- SO1-I133 tests need real data")

	fy = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ("<=", row[0].from_date), "year_end_date": (">=", row[0].from_date)},
		"name",
	)

	return frappe._dict(
		{
			"company": row[0].company,
			"fiscal_year": fy,
			"from_date": str(row[0].from_date),
			"to_date": str(row[0].to_date),
		}
	)


def busiest_workstations(filters, limit=2):
	return frappe.db.sql_list(
		"""SELECT workstation FROM `tabJob Card`
		WHERE docstatus < 2 AND company = %(company)s
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND IFNULL(workstation, '') != ''
		GROUP BY workstation ORDER BY COUNT(*) DESC LIMIT {}""".format(int(limit)),
		filters,
	)


def sql_count(filters, workstations=None):
	"""Job Card count computed independently of the report."""
	conditions = ""
	values = dict(filters)
	if workstations:
		conditions = " AND workstation IN %(workstations)s"
		values["workstations"] = tuple(workstations)

	return frappe.db.sql(
		"""SELECT COUNT(*) FROM `tabJob Card`
		WHERE docstatus < 2 AND company = %(company)s
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s"""
		+ conditions,
		values,
	)[0][0]


def names(rows):
	return {r.get("name") for r in rows}


class TestJobCardSummaryMultiWorkstation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.filters = base_filters()
		cls.workstations = busiest_workstations(cls.filters)
		if len(cls.workstations) < 2:
			raise RuntimeError("SO1-I133 tests need at least two workstations with Job Cards")
		cls.ws_a, cls.ws_b = cls.workstations

	def run_report(self, **overrides):
		filters = frappe._dict(self.filters)
		filters.update(overrides)
		_columns, data, *_rest = execute(filters)
		return data

	# ------------------------------------------------------------------ rows

	def test_no_workstation_returns_every_job_card(self):
		"""(a) nothing selected -> unchanged behaviour, all rows."""
		self.assertEqual(len(self.run_report()), sql_count(self.filters))

	def test_single_workstation_returns_only_that_workstation(self):
		"""(b) one selected -> a strict subset, all on that workstation."""
		for workstation in (self.ws_a, self.ws_b):
			with self.subTest(workstation=workstation):
				rows = self.run_report(workstation=[workstation])
				self.assertEqual(len(rows), sql_count(self.filters, [workstation]))
				self.assertEqual({r.workstation for r in rows}, {workstation})
				self.assertLess(len(rows), sql_count(self.filters))

	def test_two_workstations_return_the_union(self):
		"""(c) two selected -> exactly the two single-workstation runs, combined.

		This is the behaviour SO1-I133 asks for and the one core cannot produce.
		"""
		rows_a = self.run_report(workstation=[self.ws_a])
		rows_b = self.run_report(workstation=[self.ws_b])
		rows_both = self.run_report(workstation=[self.ws_a, self.ws_b])

		self.assertEqual(len(rows_both), len(rows_a) + len(rows_b))
		self.assertEqual(names(rows_both), names(rows_a) | names(rows_b))
		self.assertEqual({r.workstation for r in rows_both}, {self.ws_a, self.ws_b})

	def test_empty_selection_is_identical_to_core(self):
		"""Nothing selected must behave exactly as it does today -- same rows as core."""
		for empty in ([], "", None):
			with self.subTest(value=empty):
				rows = self.run_report(workstation=empty)
				_c, core_rows, *_r = core_execute(frappe._dict(self.filters))
				self.assertEqual(names(rows), names(core_rows))

	def test_legacy_single_string_still_filters(self):
		"""A saved view or URL from the Link era carries a bare string, not a list."""
		self.assertEqual(
			names(self.run_report(workstation=self.ws_a)),
			names(self.run_report(workstation=[self.ws_a])),
		)

	def test_unknown_workstation_returns_nothing(self):
		self.assertEqual(self.run_report(workstation=["__no_such_workstation__"]), [])

	def test_other_filters_still_apply_alongside_workstation(self):
		"""Workstation must narrow, not replace, the rest of the filters."""
		rows = self.run_report(workstation=[self.ws_a], status="Completed")
		self.assertTrue(all(r.status == "Completed" for r in rows))
		self.assertTrue(all(r.workstation == self.ws_a for r in rows))

	# --------------------------------------------------------------- columns

	def test_columns_are_identical_to_core(self):
		"""What lets the saved view keep its columns: same fieldnames as core.

		``generate_report_result`` replaces the report's columns with the saved
		ones and then treats any saved column whose fieldname the report does
		not emit as a custom column to be fetched from another doctype
		(frappe/desk/query_report.py:100-113).  Identical fieldnames is
		therefore the whole requirement.
		"""
		mine, *_ = execute(frappe._dict(self.filters))
		theirs, *_ = core_execute(frappe._dict(self.filters))
		self.assertEqual(mine, theirs)

	# -------------------------------------------------- core coupling pinned

	def test_core_treats_the_second_filter_group_verbatim(self):
		"""Pin the contract this report relies on.

		``normalise_multi_select_filters`` hands core ``["in", [...]]`` because
		core copies that group's values straight into ``frappe.get_all``
		(job_card_summary.py:43-45).  If a future ERPNext moves ``workstation``
		into the ``("in", ...)`` group above it the value would be wrapped
		twice; this test fails then, instead of the report silently emptying.
		"""
		filters = frappe._dict(self.filters)
		filters.workstation = ["in", [self.ws_a, self.ws_b]]
		rows = core_get_data(filters)

		self.assertEqual(len(rows), sql_count(self.filters, [self.ws_a, self.ws_b]))

	# -------------------------------------------------------- filter helper

	def test_normalise_does_not_mutate_the_callers_filters(self):
		"""``run`` returns the same dict it passed in back to the browser.

		Mutating it would send ``workstation: ["in", [...]]`` to the filter
		control (frappe/desk/query_report.py:224, 247).
		"""
		original = frappe._dict(self.filters)
		original.workstation = [self.ws_a]

		normalise_multi_select_filters(original)

		self.assertEqual(original.workstation, [self.ws_a])

	def test_normalise_shapes(self):
		cases = [
			(None, None),
			("", None),
			("   ", None),
			([], None),
			((), None),
			(["", None], None),
			("AN-01", ["in", ["AN-01"]]),
			# a name containing a comma must stay one value, never be split
			("AN, 01", ["in", ["AN, 01"]]),
			(["A", "B"], ["in", ["A", "B"]]),
			(["A", "", None], ["in", ["A"]]),
			(("A", "B"), ["in", ["A", "B"]]),
		]
		for value, expected in cases:
			with self.subTest(value=value):
				out = normalise_multi_select_filters({"workstation": value})
				self.assertEqual(out.get("workstation"), expected)


class TestSavedViewRepoint(IntegrationTestCase):
	"""The saved view Raj actually opens: "JOB CARD SUMMARY V2".

	It does not exist on the local bench (it was created on the live site), so
	it is rebuilt here exactly as it is stored there -- Custom Report, non
	standard, Sona letter head, 13 saved columns and saved filters -- and then
	put through ``install()`` and the two whitelisted endpoints the desk calls.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.filters = base_filters()
		cls.workstations = busiest_workstations(cls.filters)
		cls.ws_a, cls.ws_b = cls.workstations
		cls.addClassCleanup(frappe.clear_document_cache, "Report", CUSTOM_REPORT)

	def setUp(self):
		super().setUp()
		if frappe.db.exists("Report", CUSTOM_REPORT):
			# These tests re-point and delete the view by its real name.  They
			# roll back, but another test module in the same run can commit in
			# between (seplt.seplt.validations.manufacture_guard.install does),
			# which would make that damage permanent.  Refuse rather than risk
			# it: this suite is only ever meant to build its own copy.
			raise RuntimeError(
				f"'{CUSTOM_REPORT}' already exists on {frappe.local.site}. "
				"These tests rebuild it from scratch and must not touch a real saved view."
			)
		self.make_saved_view()

	def saved_columns(self):
		"""The 13 columns the live view has saved: core's 12, plus one extra.

		Core emits 12 columns when no status filter is set
		(job_card_summary.py:125-190).  The 13th is modelled as a column pulled
		from a linked doctype, which is the harder case -- it only resolves if
		its ``link_field`` names a fieldname the report still emits.
		"""
		columns, *_ = core_execute(frappe._dict(self.filters))
		saved = [dict(c) for c in columns]
		saved.append(
			{
				"label": "Item Group",
				"fieldname": "item_group",
				"fieldtype": "Link",
				"options": "Item Group",
				"doctype": "Item",
				"link_field": {"fieldname": "production_item", "names": []},
				"width": 110,
			}
		)
		return saved

	def make_saved_view(self):
		doc = frappe.get_doc(
			{
				"doctype": "Report",
				"report_name": CUSTOM_REPORT,
				# explicit: Report.validate promotes a blank is_standard to "Yes"
				# for Administrator when developer_mode is on, which would write
				# this throwaway report to disk (report.py:60-64, 157-164).
				"is_standard": "No",
				"report_type": "Custom Report",
				"reference_report": CORE_REPORT,
				"ref_doctype": "Job Card",
				"module": "Manufacturing",
				"json": json.dumps(
					{
						"filters": {
							"company": self.filters.company,
							"fiscal_year": self.filters.fiscal_year,
							"from_date": self.filters.from_date,
							"to_date": self.filters.to_date,
							"work_order": [],
							"production_item": [],
						},
						"columns": self.saved_columns(),
					}
				),
			}
		)
		doc.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Report", CUSTOM_REPORT, force=True, ignore_permissions=True)

	def desk_run(self, workstation=None):
		"""Exactly what the browser posts once a filter has been touched.

		``js_filters`` carries only Link filters (query_report.js:740-745), so
		Workstation being a MultiSelectList is what keeps it out of
		``validate_filters_permissions``' per-value Link permission check.
		"""
		filters = dict(self.filters)
		if workstation is not None:
			filters["workstation"] = workstation

		return run(
			report_name=CUSTOM_REPORT,
			filters=json.dumps(filters),
			are_default_filters=False,
			js_filters=json.dumps(
				[
					{"fieldname": "company", "fieldtype": "Link", "options": "Company"},
					{"fieldname": "fiscal_year", "fieldtype": "Link", "options": "Fiscal Year"},
					{"fieldname": "operation", "fieldtype": "Link", "options": "Operation"},
				]
			),
		)

	def data_rows(self, result):
		"""Drop the total row.

		``add_total_row`` appends a plain *list* while every data row is a dict
		(frappe/desk/query_report.py:681-758), so the type is the discriminator.
		"""
		return [r for r in result["result"] if isinstance(r, dict)]

	# ------------------------------------------------------------- re-point

	def test_install_repoints_the_saved_view(self):
		self.assertEqual(
			frappe.db.get_value("Report", CUSTOM_REPORT, "reference_report"), CORE_REPORT
		)

		install()

		self.assertEqual(
			frappe.db.get_value("Report", CUSTOM_REPORT, "reference_report"), THIS_REPORT
		)

	def test_install_is_idempotent(self):
		install()
		install()
		install()
		self.assertEqual(
			frappe.db.get_value("Report", CUSTOM_REPORT, "reference_report"), THIS_REPORT
		)

	def test_install_leaves_a_view_pointed_elsewhere_alone(self):
		frappe.db.set_value("Report", CUSTOM_REPORT, "reference_report", "Work Order Summary")
		install()
		self.assertEqual(
			frappe.db.get_value("Report", CUSTOM_REPORT, "reference_report"), "Work Order Summary"
		)

	def test_install_is_a_noop_where_the_view_does_not_exist(self):
		frappe.delete_doc("Report", CUSTOM_REPORT, force=True, ignore_permissions=True)
		install()  # must not raise
		self.assertFalse(frappe.db.exists("Report", CUSTOM_REPORT))

	# --------------------------------------------------------- desk endpoint

	def test_get_script_serves_the_multiselect_filters(self):
		install()
		settings = get_script(CUSTOM_REPORT)

		# the desk looks the settings up under the reference report's name
		# (query_report.js:461-468), so the script has to register under it
		self.assertEqual(settings["custom_report_name"], THIS_REPORT)
		self.assertIn(f'frappe.query_reports["{THIS_REPORT}"]', settings["script"])

		workstation_filter = self.filter_block(settings["script"], "workstation")
		self.assertIn('fieldtype: "MultiSelectList"', workstation_filter)
		self.assertIn('frappe.db.get_link_options("Workstation", txt)', workstation_filter)

	def test_get_script_before_repoint_is_the_single_select_link(self):
		"""The reported defect, reproduced through the endpoint the browser calls."""
		settings = get_script(CUSTOM_REPORT)

		self.assertEqual(settings["custom_report_name"], CORE_REPORT)
		self.assertIn('fieldtype: "Link"', self.filter_block(settings["script"], "workstation"))

	def filter_block(self, script, fieldname):
		"""The text of one filter object in a report's js."""
		start = script.index(f'fieldname: "{fieldname}"')
		return script[start : script.index("},", start)]

	def test_desk_run_returns_the_union_for_two_workstations(self):
		install()

		none_selected = self.data_rows(self.desk_run())
		only_a = self.data_rows(self.desk_run([self.ws_a]))
		only_b = self.data_rows(self.desk_run([self.ws_b]))
		both = self.data_rows(self.desk_run([self.ws_a, self.ws_b]))

		self.assertEqual(len(none_selected), sql_count(self.filters))
		self.assertEqual(len(only_a), sql_count(self.filters, [self.ws_a]))
		self.assertEqual(len(only_b), sql_count(self.filters, [self.ws_b]))
		self.assertEqual(len(both), len(only_a) + len(only_b))
		self.assertEqual(names(both), names(only_a) | names(only_b))

	def test_desk_run_empty_list_matches_pre_repoint_behaviour(self):
		"""Nothing selected has to return what the saved view returned before."""
		before = self.data_rows(self.desk_run())
		install()
		after = self.data_rows(self.desk_run())
		after_empty = self.data_rows(self.desk_run([]))

		self.assertEqual(names(after), names(before))
		self.assertEqual(names(after_empty), names(before))

	def test_saved_columns_survive_the_repoint(self):
		"""Raj's 13 saved columns come back unchanged, and still carry data."""
		expected = self.saved_columns()

		before = self.desk_run()
		install()
		after = self.desk_run()

		self.assertEqual(len(after["columns"]), 13)
		self.assertEqual(
			[c["fieldname"] for c in after["columns"]],
			[c["fieldname"] for c in expected],
		)
		self.assertEqual(
			[c["fieldname"] for c in after["columns"]],
			[c["fieldname"] for c in before["columns"]],
		)

		# the linked 13th column still resolves -- it depends on the report
		# still emitting `production_item`
		with_item = [r for r in self.data_rows(after) if r.get("production_item")]
		self.assertTrue(with_item)
		self.assertTrue(any(r.get("item_group") for r in with_item))

	def test_saving_the_view_keeps_the_repoint_and_the_multi_selection(self):
		"""Raj pressing Save must not undo the re-point.

		``save_report`` updates only ``json`` when the name already belongs to a
		Custom Report (frappe/desk/query_report.py:817-823), so
		``reference_report`` survives -- and the multi-value Workstation is
		stored as a list and read back as one.
		"""
		install()

		save_report(
			reference_report=CUSTOM_REPORT,
			report_name=CUSTOM_REPORT,
			columns=json.dumps(self.saved_columns()),
			filters=json.dumps(dict(self.filters, workstation=[self.ws_a, self.ws_b])),
		)

		self.assertEqual(
			frappe.db.get_value("Report", CUSTOM_REPORT, "reference_report"), THIS_REPORT
		)

		result = run(report_name=CUSTOM_REPORT, are_default_filters=True)
		self.assertEqual(result["custom_filters"]["workstation"], [self.ws_a, self.ws_b])
		self.assertEqual(
			{r["workstation"] for r in self.data_rows(result)}, {self.ws_a, self.ws_b}
		)

	def test_saved_default_filters_still_apply(self):
		"""Opening the view untouched uses its saved filters, as before."""
		install()
		result = run(report_name=CUSTOM_REPORT, are_default_filters=True)

		self.assertEqual(result["custom_filters"]["company"], self.filters.company)
		# the saved filters must come back exactly as stored -- not rewritten
		# into the ["in", [...]] shape this report uses internally
		self.assertEqual(result["custom_filters"].get("work_order"), [])
		self.assertNotIn("workstation", result["custom_filters"])
