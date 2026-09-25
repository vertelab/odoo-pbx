# -*- coding: utf-8 -*-
{
    'name': "46Elks IVR",
    'version': '18.0.1.1.0',
    'summary': 'Phone Managment Sofware.',
    'sequence': -201,
    'description': '''
46Elks IVR
==========

    Phone Managment Sofware.

    Features:

        - Web integration: Exposes HTTP endpoints for external systems.
        - UI Integration: Extends 2 view(s) in the Odoo interface.
        - Extends Odoo: Builds on mail.thread, sms.sms.
    ''',
    'category': 'Theme',
    'website': "https://vertel.se/apps/odoo-pbx/pbx_46elks",
    'license': 'LGPL-3',
    'depends': ['website', 'base', 'contacts', 'sms'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/assets.xml',
        'views/snippets/index.xml',
        'views/snippets/sms_snippet.xml',
        'views/snippets/snippets.xml'
        ],
    'demo': [],
    'qweb': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
