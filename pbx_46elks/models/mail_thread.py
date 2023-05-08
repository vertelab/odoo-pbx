from odoo import models, _, api
from odoo import http
from odoo.http import request
import requests
from odoo.tools import html2plaintext

import logging
_logger = logging.getLogger(__name__)

class MailThread(models.AbstractModel):
    _inherit = "mail.thread"
    
    def _message_post_after_hook(self, message, msg_vals):
        res = super()._message_post_after_hook(message, msg_vals)
        env = http.request.env
        IrConfigParameter = env['ir.config_parameter'].sudo()
        provider = IrConfigParameter.get_param('46elks.provider', default='')
        if msg_vals["message_type"] == "sms" and provider == "1":
            self.send_46elks_sms(msg_vals)
        _logger.error("MailThread _message_post_after_hook - message : " + str(message))
        _logger.error("MailThread _message_post_after_hook - msg_vals : " + str(msg_vals))
        return res
    
    def send_46elks_sms(self, msg_vals):
        env = http.request.env
        IrConfigParameter = env['ir.config_parameter'].sudo()
        api_username = IrConfigParameter.get_param('46elks.api_username', default='')
        api_password = IrConfigParameter.get_param('46elks.api_password', default='')

        message = html2plaintext(msg_vals.get('body'))
        
        partner_ids = list(msg_vals['partner_ids'])
        author_id = msg_vals['author_id']
        for partner_id in partner_ids:
            
            reciever = self.env['res.partner'].browse(partner_id)
            sender = self.env['res.partner'].browse(author_id)
            
            to_phone_number = reciever.phone.replace("-", "").replace(" ", "")
            from_phone_number = sender.phone.replace("-", "").replace(" ", "")
            
            response = requests.post(
                'https://api.46elks.com/a1/sms',
                auth = (api_username, api_password),
                data = {
                    'from': from_phone_number,
                    'to': to_phone_number,
                    'message': message,
                    'dryrun': 'yes'
                }
            )
            _logger.error("--------------------" + str(response.status_code))
            _logger.error("--------------------" + str(response.text))
            
            for i in response:
                _logger.error("--------------------" + str(i))
                
        
        # values.update({
        #     'author_id': author_id,
        #     'email_from': email_from,
        #     'model': self._name,
        #     'res_id': self.id,
        #     'body': body,
        #     'subject': subject or False,
        #     'message_type': message_type,
        #     'parent_id': parent_id,
        #     'subtype_id': subtype_id,
        #     'partner_ids': partner_ids,
        #     'channel_ids': channel_ids,
        #     'add_sign': add_sign,
        #     'record_name': record_name,
        # })