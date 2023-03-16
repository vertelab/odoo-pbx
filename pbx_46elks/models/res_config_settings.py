# -*- coding: utf-8 -*-

from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    api_username = fields.Char(string="Api Username", config_parameter='46elks.api_username')
    api_password = fields.Char(string="Api Password", config_parameter='46elks.api_password')
    
    @api.model
    def _get_selection_options(self):
        # Define the selection options dynamically
        return [('1', '46Elks'), ('2', 'Teleproffs'), ('3', 'Telia')]

    my_field = fields.Selection(selection=_get_selection_options, config_parameter='46elks.provider', required=True)