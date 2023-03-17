# -*- coding: utf-8 -*-

from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    api_username = fields.Char(string="Api Username", config_parameter='46elks.api_username')
    api_password = fields.Char(string="Api Password", config_parameter='46elks.api_password')
    webrtc_user = fields.Char(string="WebRTC User", config_parameter='46elks.webrtc_user')
    webrtc_password = fields.Char(string="WebRTC Number", config_parameter='46elks.webrtc_password')
    virtual_number = fields.Char(string="Virtual Number", config_parameter='46elks.virtual_number')
    
    
    
    @api.model
    def _get_selection_options(self):
        # Define the selection options dynamically
        return [('1', '46Elks'), ('2', 'Teleproffs'), ('3', 'Telia')]

    my_field = fields.Selection(selection=_get_selection_options, config_parameter='46elks.provider', required=True)