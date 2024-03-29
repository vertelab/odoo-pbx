# -*- coding: utf-8 -*-
{
    'name': "46Elks IVR",
    'version': '1.1',
    'summary': 'Phone Managment Sofware',
    'sequence': -201,
    'description': """Phone Managment Sofware""",
    'category': 'Theme',
    'website': "https://www.odoomates.tech",
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
