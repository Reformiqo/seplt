app_name = "seplt"
app_title = "Seplt"
app_publisher = "Erpera"
app_description = "Erpera"
app_email = "info@erpera.io"
app_license = "mit"
# required_apps = []

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/seplt/css/seplt.css"
# app_include_js = "/assets/seplt/js/seplt.js"

# include js, css files in header of web template
# web_include_css = "/assets/seplt/css/seplt.css"
# web_include_js = "/assets/seplt/js/seplt.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "seplt/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Stock Entry" : "public/js/stock_entry.js",
    "Subcontracting Inward Order" : "public/js/subcontracting_inward_order.js"
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "seplt/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "seplt.utils.jinja_methods",
# 	"filters": "seplt.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "seplt.install.before_install"
# after_install = "seplt.install.after_install"

# Creates the Stock-Manager-only override checkbox used by the Manufacture
# guards. Idempotent, so it is safe to run on every migrate.
#
# NOTE: a list, not a string — add new entries here rather than writing a
# second `after_migrate = ...`, which would silently replace this one.
after_migrate = [
	"seplt.seplt.validations.manufacture_guard.install",
	"seplt.seplt.report.job_card_summary_multi_workstation.job_card_summary_multi_workstation.install",
	# Guards the India Compliance monkeypatch below: fails the migrate if the
	# functions it rebinds have moved, rather than silently reverting to
	# India Compliance's stock validation.
	"seplt.overrides.india_compliance_taxes.assert_patch_targets",
]


# Uninstallation
# ------------

# before_uninstall = "seplt.uninstall.before_uninstall"
# after_uninstall = "seplt.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "seplt.utils.before_app_install"
# after_app_install = "seplt.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "seplt.utils.before_app_uninstall"
# after_app_uninstall = "seplt.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "seplt.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Stock Entry": "seplt.overrides.stock_entry.CustomStockEntry",
	"Work Order": "seplt.overrides.work_order.CustomWorkOrder"
}

# Document Events
# ---------------
# Hook on document methods and events

# Guards against the two Manufacture defects found on 09-08-2026: entries that
# produce stock while consuming nothing (410 entries, Rs 96.42 cr) and a line
# total typed into the rate column (MAT-STE-40604, Rs 93.92 cr). Neither could
# be corrected after the fact, so they are stopped at entry.
#
# NOTE: keep every entry in this ONE dict. A second `doc_events = {...}`
# assignment silently replaces the first — that is how the Stock Entry guards
# below were disabled once already.
doc_events = {
	"Stock Entry": {
		# Installs the India Compliance relaxation — see india_compliance_taxes.py.
		# before_validate, because frappe runs that event for every app before it
		# runs `validate` for any (frappe/model/document.py), so the patch is in
		# place before India Compliance validates no matter what order the apps
		# are installed in — here India Compliance is actually ahead of seplt.
		"before_validate": "seplt.overrides.india_compliance_taxes.apply",
		"validate": "seplt.seplt.validations.manufacture_guard.check_rate_sanity",
		"before_submit": "seplt.seplt.validations.manufacture_guard.check_consumption",
	},
	"Subcontracting Order": {
		"before_validate": "seplt.overrides.india_compliance_taxes.apply",
	},
	"Subcontracting Receipt": {
		"before_validate": "seplt.overrides.india_compliance_taxes.apply",
	},
	"Subcontracting Inward Order": {
		"on_submit": "seplt.overrides.subcontracting_inward_order.set_received_qty_on_submit"
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"seplt.tasks.all"
# 	],
# 	"daily": [
# 		"seplt.tasks.daily"
# 	],
# 	"hourly": [
# 		"seplt.tasks.hourly"
# 	],
# 	"weekly": [
# 		"seplt.tasks.weekly"
# 	],
# 	"monthly": [
# 		"seplt.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "seplt.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "seplt.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "seplt.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["seplt.utils.before_request"]
# after_request = ["seplt.utils.after_request"]

# Job Events
# ----------
# before_job = ["seplt.utils.before_job"]
# after_job = ["seplt.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"seplt.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
    {"doctype": "Client Script", 
    "filters": [["module" , "in" , ("Seplt" )]]
    },
    {"doctype": "Custom Field",
    "filters": [["module" , "in" , ("Seplt" )]]
    },
    {
        "doctype" : "Property Setter",
        "filters": [["module" , "in" , ("Seplt" )]]
    }
    ]