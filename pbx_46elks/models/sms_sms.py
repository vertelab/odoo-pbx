from odoo import models, fields, api, exceptions, _, http

import logging
_logger = logging.getLogger(__name__)


class SmsSms(models.Model):
    _inherit = 'sms.sms'

    def _send(self, delete_all=False, raise_exception=False):
        if self.get_provider() == "1":
            self.state = "sent"
            return

        return super(SmsSms, self)._send(delete_all=delete_all, raise_exception=raise_exception)

    # Overrides the function if 46elks is selected so that Odoo doesn't try to send messages using the built in method
    def _process_queue(self, ids=None):
        env = self.env
        _logger.error(f"{env=}")
        IrConfigParameter = env['ir.config_parameter'].sudo()
        provider = IrConfigParameter.get_param('46elks.provider', default='')
        if provider == "1":
            _logger.error("_process_queue overridden")
            return None

        return super(SmsSms, self)._process_queue(ids)
    
    # Takes the values from the request and creates a mail.message
    def create_message_from_sms(self, values):
        recieved_message = values.get('message') 
        to_number = values.get('to')
        from_number = values.get('from')
        
        partners = self.env['res.partner'].sudo().search([])

        # Find the partners with a matching cleaned phone number
        # TODO: Add functionality for handling scenario where a partner cannot be found.
        to_partner = None
        from_partner = None
        for partner in partners:
            cleaned_phone = partner.phone.replace(" ", "") if partner.phone else ""
            cleaned_mobile = partner.mobile.replace(" ", "") if partner.mobile else ""
            
            if not to_partner and (cleaned_phone == to_number or cleaned_mobile == to_number):
                to_partner = partner
                _logger.error("To_partner = " + to_partner.name)

            if not from_partner and (cleaned_phone == from_number or cleaned_mobile == from_number):
                from_partner = partner
                _logger.error("From_partner = " + from_partner.name)

            if to_partner and from_partner:
                break
        
        values_list = {
            'author_id': from_partner.id,
            'email_from': from_partner.email,
            'model': 'res.partner',
            'res_id': to_partner.id,
            'body': f'<p>{recieved_message}</p>',
            'subject': False,
            'message_type': 'sms',
            'parent_id': False,
            'subtype_id': 2,
            'partner_ids': [(6, 0, [to_partner.id])],
            'channel_ids': [(6, 0, [])],
            'add_sign': True,
            'record_name': from_partner.name,
            'attachment_ids': [],
        }

        # Create the message using the data retrieved from the request and partners correlated to the message
        message_model = self.env['mail.message']
        
        # Need to add .sudo() in order for it to work
        message = message_model.create(values_list)
        
        kwargs = {
            'sms_numbers': None,
            'sms_pid_to_number': {to_partner.id: to_number}
        }
        
        values_list['partner_ids'] = {to_partner.id}
        values_list['channel_ids'] = set()
        
        # For notifying reviever of message delivered
        thread_model = self.env['mail.thread']
        thread_model._notify_thread(message, values_list, **kwargs)
    
    # Function for checking which provider is selected in system parameters
    def get_provider(self):
        env = self.env
        IrConfigParameter = env['ir.config_parameter'].sudo()
        provider = IrConfigParameter.get_param('46elks.provider', default='')
        return provider