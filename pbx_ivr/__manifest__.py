{
    "name": "PBX IVR",
    "version": "18.0.1.1.0",
    "summary": "IVR menu tree management for Asterisk",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://vertel.se/apps/odoo-pbx/pbx_ivr",
    "license": "AGPL-3",
    "depends": ["pbx_base"],
    "data": [
        "security/ir.model.access.csv",
        "views/pbx_ivr_views.xml",
    ],
        "assets": {
        "web.assets_backend": [
            "pbx_ivr/static/src/**/*",
        ],
    },
    "installable": True,
    "application": False,
}
