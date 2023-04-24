# -*- coding: utf-8 -*-

from odoo import fields, models, api
import socket
from odoo.exceptions import ValidationError

def is_valid_ip(ip):
    try:
        socket.inet_aton(ip)
        return True
    except socket.error:
        return False

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    api_username = fields.Char(string="Api Username", config_parameter='46elks.api_username')
    api_password = fields.Char(string="Api Password", config_parameter='46elks.api_password')
    webrtc_user = fields.Char(string="WebRTC User", config_parameter='46elks.webrtc_user')
    webrtc_password = fields.Char(string="WebRTC Number", config_parameter='46elks.webrtc_password')
    virtual_number = fields.Char(string="Virtual Number", config_parameter='46elks.virtual_number')
    allowed_ips = fields.Char(string="Allowed Ip's", config_parameter="46elks.alowed_ips")
    
    
    @api.model
    def create(self, vals):
        
        ips = vals.get('allowed_ips')
        if ips:
            ip_addresses = ips.split(',')
        else:
            raise ValidationError("Input Ip-adress")
        valid_ips = []
        for ip in ip_addresses:
            if is_valid_ip(ip.strip()):
                valid_ips.append(ip.strip())
            else:
                raise ValidationError("Invalid Ip-adress")
        return super().create(vals)
        
        # Sets the appropriate type depending on alcoholcontent in the ingredients.
    #     super().create(vals)
    
    @api.model
    def _get_selection_options(self):
        # Define the selection options dynamically
        return [('1', '46Elks'), ('2', 'Teleproffs'), ('3', 'Telia')]

    my_field = fields.Selection(selection=_get_selection_options, config_parameter='46elks.provider', required=True)
    
