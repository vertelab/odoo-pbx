from odoo import models, fields, api, exceptions, _, http

import logging
_logger = logging.getLogger(__name__)


class SmsSms(models.Model):
    _inherit = 'sms.sms'

    def _send(self, delete_all=False, raise_exception=False):
        env = self.env
        _logger.error("Hej1")
        IrConfigParameter = env['ir.config_parameter'].sudo()
        _logger.error("Hej2")
        provider = IrConfigParameter.get_param('46elks.provider', default='')
        _logger.error("provider = " + str(provider))
        if provider == "1":
            self.state = "sent"
            return

        return super(SmsSms, self)._send(delete_all=delete_all, raise_exception=raise_exception)

    def _process_queue(self, ids=None):
        env = self.env
        _logger.error(f"{env=}")
        IrConfigParameter = env['ir.config_parameter'].sudo()
        provider = IrConfigParameter.get_param('46elks.provider', default='')
        if provider == "1":
            _logger.error("_process_queue overridden")
            return None

        return super(SmsSms, self)._process_queue(ids)
    
    def create_message_from_sms(self): #, values
        _logger.error("create_message_from_sms - 1")
        values = {
            'message': 'Test Message create_message_from_sms',
            'to': '+46766867369',  # Replace with the recipient's phone number
            'from': '+46768763536'  # Replace with the sender's phone number
        }
        
        recieved_message = values.get('message')
        to_number = values.get('to')
        from_number = values.get('from')
        _logger.error("create_message_from_sms - 2")
        
        partners = self.env['res.partner'].search([])

        # Find the partner with a matching cleaned phone number
        to_partner = None
        for partner in partners:
            cleaned_phone = partner.phone.replace(" ", "") if partner.phone else ""
            cleaned_mobile = partner.mobile.replace(" ", "") if partner.mobile else ""
            
            if cleaned_phone == to_number or cleaned_mobile == to_number:
                to_partner = partner
                _logger.error("To_partner = " + to_partner.name)
                break
            
        from_partner = None
        for partner in partners:
            cleaned_phone = partner.phone.replace(" ", "") if partner.phone else ""
            cleaned_mobile = partner.mobile.replace(" ", "") if partner.mobile else ""
            
            if cleaned_phone == from_number or cleaned_mobile == from_number:
                from_partner = partner
                _logger.error("From_partner = " + from_partner.name)
                break
        _logger.error("create_message_from_sms - 3")
        
        # to_partner = self.env['res.partner'].search([('phone', 'ilike', to_number)], limit=1)
        # from_partner = self.env['res.partner'].search([('phone', 'like', from_number)], limit=1)
        _logger.error("create_message_from_sms - 4")
        
        values_list = {}
        values_list['author_id'] = from_partner.id
        values_list['email_from'] = from_partner.email
        values_list['model'] = 'res.partner'
        values_list['res_id'] = to_partner.id
        values_list['body'] = f'<p>{recieved_message}</p>'
        values_list['subject'] = False
        values_list['message_type'] = 'sms'
        values_list['parent_id'] = False
        values_list['subtype_id'] = 2
        values_list['partner_ids'] = [(6, 0, [to_partner.id])]
        values_list['channel_ids'] = [(6, 0, [])]
        values_list['add_sign'] = True
        values_list['record_name'] = from_partner.name
        values_list['attachment_ids'] = []

        _logger.error("create_message_from_sms - 5")
        _logger.error("create_message_from_sms - 6 = " + str(values_list))
        

        message_model = self.env['mail.message']
        res = message_model.create(values_list)