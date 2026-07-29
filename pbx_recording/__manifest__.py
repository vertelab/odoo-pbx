{
    "name": "PBX Recording",
    "version": "18.0.1.0.0",
    "summary": "Call recording with Garage S3 storage",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://github.com/vertelab/odoo-pbx",
    "license": "AGPL-3",
    "depends": ["pbx_base"],
    "data": [
        "security/ir.model.access.csv",
        "views/pbx_recording_views.xml",
    ],
    "installable": True,
    "application": False,
}
