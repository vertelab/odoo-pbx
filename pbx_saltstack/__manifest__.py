# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "PBX SaltStack Bridge",
    "version": "18.0.1.0.0",
    "summary": "Knyt en Salt-minion till en pbx.tenant och deploya växelinfo via Salt",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://github.com/vertelab/odoo-pbx",
    "license": "AGPL-3",
    "depends": ["pbx_admin", "pbx_base"],
    "data": [
        "views/pbx_tenant_views.xml",
    ],
    "installable": True,
    "application": False,
}
