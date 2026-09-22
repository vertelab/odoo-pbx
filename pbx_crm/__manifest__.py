{
    "name": "PBX CRM",
    "version": "18.0.1.6.0",
    "summary": "CRM integration for PBX — lead popup, call logging",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://vertel.se/apps/odoo-pbx/pbx_crm",
    "license": "AGPL-3",
    "depends": ["pbx_tenant", "crm"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/crm_click_to_call_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
