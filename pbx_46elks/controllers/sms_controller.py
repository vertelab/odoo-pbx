import logging
from odoo import http, api, registry
from odoo.http import request, Response
import requests
_logger = logging.getLogger(__name__)


class SmsController(http.Controller):

    @http.route('/46elks/sms/recieve/', type='http', auth='public', methods=['POST'], csrf=False)
    def recieve_sms(self, **kwargs):
        try:
            allowed_ips = ['176.10.154.199', '85.24.146.132', '185.39.146.243']
        
            client_ip = request.httprequest.remote_addr
            if client_ip not in allowed_ips:
                _logger.error("domain fail")
                return Response('Forbidden', status=403)

            _logger.error("domain succcess")
            recieved_message = kwargs.get('message')
            to_number = kwargs.get('to')
            from_number = kwargs.get('from')
            created = kwargs.get('created')

            _logger.error(from_number)
            _logger.error(to_number)
            _logger.error(created)
            _logger.error(recieved_message)
            
            # Maybe use for automated messages?
            # response_data = {
            #     'kalle': 'Success',
            # }
            headers = [
                ('Content-Type', 'application/json'),
            ]
            return Response(status=200, headers=headers) #response=response_data, 
        except:
            response_data = {
                'message': 'Unsuccessful',
            }
            headers = [
                ('Content-Type', 'application/json'),
            ]
            return Response(response=response_data, status=500, headers=headers)
    
    @http.route('/46elks/sms/send/', type='http', auth='user', methods=['POST'], csrf=False)
    def send_sms(self, **kwargs):
        env = http.request.env
        with api.Environment.manage():
            # Open a new database cursor
            with registry(env.cr.dbname).cursor() as new_cr:
                # Create a new Odoo environment with the new cursor
                new_env = api.Environment(new_cr, env.uid, env.context)
                # Retrieve the values of api_username and api_password from the database
                config_settings = new_env['res.config.settings'].sudo().create({})
                api_username = config_settings.api_username or ''
                api_password = config_settings.api_password or ''
        
        message = kwargs.get('message')
        to_number = kwargs.get('to')
        from_number = request.env.user.partner_id.phone.replace(" ", "")
        
        _logger.error(f"Message: {message}")
        _logger.error(f"To: {to_number}")
        _logger.error(f"From: {from_number}")
        
        response = requests.post(
            'https://api.46elks.com/a1/sms',
            auth = (api_username, api_password),
            data = {
                'from': from_number,
                'to': to_number,
                'message': message,
                'dryrun': 'no'
            }
        )
        _logger.error(response.text)