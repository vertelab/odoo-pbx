{
    "name": "PBX AI Bridge",
    "version": "18.0.1.1.0",
    "summary": "Bridge between odoo-pbx and Odoo Mind (graph + memory)",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://github.com/vertelab/odoo-pbx",
    "license": "AGPL-3",
    "depends": ["pbx_tenant"],
    "data": [
        "security/ir.model.access.csv",
        "data/graph_definitions.xml",
    ],
    "installable": True,
    "auto_install": False,
}
