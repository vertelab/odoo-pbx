# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    """Asterisk/SIP-inställningar per företag — möjliggör multicompany.

    Varje företag har sin egen SIP-domän (och kan peka på egen server),
    medan extensions/trunks/routes redan är company-scopade.
    """

    _inherit = "res.company"

    pbx_domain = fields.Char(
        string="SIP Domain",
        help="Företagets SIP-domän på Asterisk-servern, t.ex. vertel.se",
    )
    pbx_server_host = fields.Char(
        string="PBX Server",
        help="Asterisk-serveradress (tom = använd global setting)",
    )
    pbx_api_key = fields.Char(
        string="PBX API Key",
        groups="base.group_system",
        help="API-nyckel mot Asterisk-servern / provisioning-daemon",
    )
