{
    "name": "PBX Time Condition",
    "version": "18.0.1.0.0",
    "summary": "Time-based call routing for Asterisk",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://github.com/vertelab/odoo-pbx",
    "license": "AGPL-3",
    "depends": ["pbx_base", "resource"],
    "data": [
        "security/ir.model.access.csv",
        "views/pbx_time_condition_views.xml",
    ],
    "installable": True,
    "application": False,
}
