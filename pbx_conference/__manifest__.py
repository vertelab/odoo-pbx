{
    "name": "PBX Conference",
    "version": "18.0.1.2.0",
    "summary": "Conference room management for Asterisk",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://github.com/vertelab/odoo-pbx",
    "license": "AGPL-3",
    "depends": ["pbx_base"],
    "data": [
        "security/ir.model.access.csv",
        "views/pbx_conference_views.xml",
    ],
        "assets": {
        "web.assets_backend": [
            "pbx_conference/static/src/**/*",
        ],
    },
    "installable": True,
    "application": False,
}
