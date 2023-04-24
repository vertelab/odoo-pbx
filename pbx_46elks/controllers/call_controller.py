import json
import logging
from odoo import http, api, registry
from odoo.http import request
import base64
import requests
_logger = logging.getLogger(__name__)


class CallController(http.Controller):

    @http.route('/46elks/call/', type='http', auth='user', methods=['POST'], csrf=False)
    def call_api(self, **kwargs):
        env = http.request.env
        IrConfigParameter = env['ir.config_parameter'].sudo()
        api_username = IrConfigParameter.get_param('46elks.api_username', default='')
        api_password = IrConfigParameter.get_param('46elks.api_password', default='')
        # Use the retrieved values to authenticate the API call
        username = api_username
        password = api_password
        _logger.error(f"Username: {username}")
        _logger.error(f"Password: {password}")

        from_number = kwargs.get('from')
        to_number = kwargs.get('to')
        voice_start = kwargs.get('voice_start')

        url = "https://api.46elks.com/a1/calls"
        auth = (username, password)
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        
        data = {
            'from': from_number,
            'to': to_number,
            'voice_start': voice_start
        }
        
        _logger.error(voice_start)
        _logger.error(from_number)
        _logger.error(to_number)
    
        response = requests.post(url, auth=auth, headers=headers, data=data)
        _logger.error(response.text)

        if response.status_code == 200:
            return response.text
        else:
            return response.status_code

    @http.route('/46elks/webrtc/data', type='http', auth='user', methods=['GET'], csrf=False)
    def get_data(self):
        _logger.error("Funkar?")
        env = http.request.env
        config_settings = env['res.config.settings'].sudo()
        data = {
            'webrtc_user': config_settings.get_param('46elks.webrtc_user', default=''), 
            'webrtc_password': config_settings.get_param('46elks.webrtc_password', default=''),
            'virtual_number': config_settings.get_param('46elks.virtual_number', default=''),
        }
        return json.dumps(data)