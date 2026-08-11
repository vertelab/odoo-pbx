{
    "name": "PBX Helpdesk",
    "version": "18.0.1.1.0",
    "summary": "Helpdesk integration for PBX — ticket popup, SLA monitoring",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://github.com/vertelab/odoo-pbx",
    "license": "AGPL-3",
    "depends": ["pbx_tenant", "helpdesk"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
