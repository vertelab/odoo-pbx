# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


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
    pbx_odoo_url = fields.Char(
        string="Odoo URL",
        help="Kundens Odoo-bas-URL som den genererade dialplanen anropar för "
             "tillgänglighetskontroll (t.ex. https://crm.vertel.se). "
             "Tom = använd web.base.url.",
    )
    pbx_sip_port = fields.Char(
        string="SIP Port",
        default="5061",
        help="SIP-port för enheter (5061 för WSS/WebRTC, 5060 för UDP/TCP)",
    )
    pbx_sip_ws_port = fields.Integer(
        string="WebSocket Port",
        default=8089,
        help="Asterisk HTTP/WebSocket-port för Odoo-softphonen (SIP.js). "
             "Default 8089 (WSS). Används vid härledning av ws_server om "
             "inget explicit pbx_ws_server anges.",
    )
    pbx_ws_server = fields.Char(
        string="WebSocket Server (override)",
        help="Explicit WebSocket-URL för Odoo-softphonen, t.ex. "
             "wss://192.168.11.213:8089/ws. Tom = härled automatiskt från "
             "pbx_server_host + pbx_sip_ws_port.",
    )
    pbx_config_version = fields.Integer(
        string="PBX Config Version",
        default=0,
        help="Senast publicerade config-version (räknas upp vid varje sync).",
    )
    pbx_config_applied_version = fields.Integer(
        string="PBX Config Applied Version",
        default=0,
        help="Senast bekräftat applicerade config-version (från daemon-ack).",
    )
    pbx_config_sync_error = fields.Text(
        string="PBX Config Sync Error",
        help="Senaste felmeddelande från daemon-ack (tom = inget fel).",
    )
    pbx_config_sync_state = fields.Selection(
        [
            ("clean", "Clean"),
            ("sent", "Sent"),
            ("applied", "Applied"),
            ("error", "Error"),
        ],
        string="PBX Config Sync State",
        compute="_compute_pbx_config_sync_state",
        help="Synk-status: clean/applied = bekräftat, sent = publicerat utan "
             "bekräftelse, error = daemon rapporterade fel.",
    )

    @api.depends(
        "config_dirty",
        "pbx_config_version",
        "pbx_config_applied_version",
        "pbx_config_sync_error",
    )
    def _compute_pbx_config_sync_state(self):
        for rec in self:
            if (
                rec.pbx_config_sync_error
                and rec.pbx_config_applied_version < rec.pbx_config_version
            ):
                rec.pbx_config_sync_state = "error"
            elif rec.pbx_config_applied_version >= rec.pbx_config_version:
                rec.pbx_config_sync_state = "applied"
            elif rec.pbx_config_version or rec.config_dirty:
                rec.pbx_config_sync_state = "sent"
            else:
                rec.pbx_config_sync_state = "clean"
    pbx_turn_enabled = fields.Boolean(
        string="TURN aktiverad",
        default=False,
        help="Slå på TURN för enheter bakom NAT (coturn gör både STUN-discovery "
        "och TURN-media-relay på samma adress).",
    )
    pbx_provisioning_token = fields.Char(
        string="PBX Provisioning-token",
        groups="pbx_base.group_pbx_admin,base.group_system",
        help="Hemlig token för provisioning-endpointen (hårdvarutelefoner). "
             "Telefonen skickar den som lösenord i URL:en: "
             "https://<domän>:<token>@provision.../<MAC>.cfg",
    )

    def _ensure_pbx_provisioning_token(self):
        """Generera provisioning-token om den saknas (idempotent)."""
        import secrets

        for rec in self:
            if not rec.pbx_provisioning_token:
                rec.pbx_provisioning_token = secrets.token_urlsafe(24)
    config_dirty = fields.Boolean(
        string="PBX Config Dirty",
        default=False,
        help="True när konfigurationsändringar väntar på att synkas till Asterisk.",
    )

    def _pbx_mark_dirty(self):
        """Markera att konfigurationen behöver synkas till Asterisk."""
        if not self.config_dirty:
            self.config_dirty = True
