{
    "name": "PBX HR Bridge",
    "version": "18.0.1.1.0",
    "summary": "PBX↔HR-brygga — anknytning på hr.employee (ange/fördela, hierarkisk numrering, omnumrering)",
    "category": "Productivity/VOIP",
    "author": "Vertel AB",
    "website": "https://github.com/vertelab/odoo-pbx",
    "license": "AGPL-3",
    "depends": ["pbx_base", "hr", "hr_org_chart"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_employee_views.xml",
    ],
    "installable": True,
    "application": False,
}
