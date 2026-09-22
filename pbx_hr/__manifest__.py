{
    "name": "PBX HR Bridge",
    "version": "18.0.1.4.0",
    "summary": "PBX<>HR bridge — extension on hr.employee (assign/suggest, hierarchical numbering, renumbering)",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://vertel.se/apps/odoo-pbx/pbx_hr",
    "license": "AGPL-3",
    "depends": ["pbx_base", "hr", "hr_org_chart"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_employee_views.xml",
        "views/hr_click_to_call_views.xml",
    ],
    "installable": True,
    "application": False,
}
