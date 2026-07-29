{
    "name": "PBX CRM",
    "version": "18.0.1.0.0",
    "summary": "CRM integration for PBX — lead popup, call logging",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://github.com/vertelab/odoo-pbx",
    "license": "AGPL-3",
    "depends": ["pbx_tenant", "crm"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
