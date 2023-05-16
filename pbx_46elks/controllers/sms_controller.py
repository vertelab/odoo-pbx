import logging
from odoo import http, api, registry
from odoo.http import request, Response
import requests
_logger = logging.getLogger(__name__)


class SmsController(http.Controller):

    # Route for recieving sms-request from 46elks
    @http.route('/46elks/sms/recieve/', type='http', auth='public', methods=['POST', 'GET'], csrf=False)
    def recieve_sms(self, **kwargs):
        try:
            # Makes sure the request comes from one of the ip-adresses that 46elks uses
            allowed_ips_str = request.env['ir.config_parameter'].sudo().get_param('46elks.alowed_ips')
            if allowed_ips_str:
                allowed_ips_split = allowed_ips_str.split(',')
                allowed_ips = []
                for ip in allowed_ips_split:
                    allowed_ips.append(ip.strip())
            else:
                return Response('Forbidden', status=403)
            client_ip = request.httprequest.remote_addr
            if client_ip not in allowed_ips:
                _logger.error(f"Unauthorized IP({client_ip}) tried to post SMS")
                return Response('Forbidden', status=403)
            
            sms_model = http.request.env['sms.sms']
            sms_model.create_message_from_sms(kwargs)

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
    
    # Route for sending sms through website
    @http.route('/46elks/sms/send/', type='http', auth='user', methods=['POST'], csrf=False)
    def send_sms(self, **kwargs):
        env = http.request.env
        IrConfigParameter = env['ir.config_parameter'].sudo()
        api_username = IrConfigParameter.get_param('46elks.api_username', default='')
        api_password = IrConfigParameter.get_param('46elks.api_password', default='')

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