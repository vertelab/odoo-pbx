import logging
from odoo import http
from odoo.http import request, Response
_logger = logging.getLogger(__name__)


class SmsController(http.Controller):

    @http.route('/46elks/sms/recieve/', type='http', auth='public', methods=['POST'], csrf=False)
    def recieve_sms(self, **kwargs):
        try:
            recieved_message = kwargs.get('message')
            to_number = kwargs.get('to')
            from_number = kwargs.get('from')
            created = kwargs.get('created')

            _logger.error(from_number)
            _logger.error(to_number)
            _logger.error(created)
            _logger.error(recieved_message)        
            
            response_data = {
                'kalle': 'Success',
            }
            headers = [
                ('Content-Type', 'application/json'),
            ]
            return Response(response=response_data, status=200, headers=headers)
        except:
            response_data = {
                'message': 'Unsuccessful',
            }
            headers = [
                ('Content-Type', 'application/json'),
            ]
            return Response(response=response_data, status=500, headers=headers)
        