{
    "name": "PBX Tenant",
    "version": "18.0.1.0.0",
    "summary": "Customer PBX module with softphone, FOP2 panel, and voicemail",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://github.com/vertelab/odoo-pbx",
    "license": "AGPL-3",
    "depends": ["pbx_base", "voip_oca"],
    "data": [
        "security/ir.model.access.csv",
        "views/pbx_voicemail_views.xml",
        "views/res_users_views.xml",
        "views/pbx_fop2_views.xml",
    ],
    "demo": [
        "demo/demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pbx_tenant/static/src/**/*",
        ],
    },
    "installable": True,
    "application": True,
}
