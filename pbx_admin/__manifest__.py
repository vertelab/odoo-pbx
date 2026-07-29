{
    "name": "PBX Admin",
    "version": "18.0.1.0.0",
    "summary": "Central MSP panel for multi-tenant PBX management",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://github.com/vertelab/odoo-pbx",
    "license": "AGPL-3",
    "depends": ["pbx_base"],
    "data": [
        "security/ir.model.access.csv",
        "views/pbx_admin_settings_views.xml",
        "views/pbx_tenant_admin_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
}
