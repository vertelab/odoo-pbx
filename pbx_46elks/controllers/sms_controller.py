import logging
from odoo import http, api, registry
from odoo.http import request, Response
import requests
_logger = logging.getLogger(__name__)


class SmsController(http.Controller):

    @http.route('/46elks/sms/recieve/', type='http', auth='public', methods=['POST', 'GET'], csrf=False)
    def recieve_sms(self, **kwargs):
        try:
            
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
        