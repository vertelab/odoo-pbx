{
    "name": "PBX Queue",
    "version": "18.0.1.0.0",
    "summary": "Call queue and ring group management for Asterisk",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://github.com/vertelab/odoo-pbx",
    "license": "AGPL-3",
    "depends": ["pbx_base"],
    "data": [
        "security/ir.model.access.csv",
        "views/pbx_queue_views.xml",
    ],
        "assets": {
        "web.assets_backend": [
            "pbx_queue/static/src/**/*",
        ],
    },
    "installable": True,
    "application": False,
}
