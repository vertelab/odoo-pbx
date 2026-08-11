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
    pbx_sip_port = fields.Char(
        string="SIP Port",
        default="5061",
        help="SIP-port för enheter (5061 för WSS/WebRTC, 5060 för UDP/TCP)",
    )
    pbx_stun_enabled = fields.Boolean(
        string="STUN aktiverad",
        default=False,
        help="Slå på STUN för enheter bakom NAT (mobil/desktop).",
    )
    pbx_stun_server = fields.Char(
        string="STUN Server",
        help="t.ex. stun.vertel.se:3478",
    )
