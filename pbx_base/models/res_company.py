# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResCompany(models.Model):
    """Asterisk/SIP settings per company — enables multicompany.

    Each company has its own SIP domain (and may point at its own server),
    while extensions/trunks/routes are already company-scoped.
    """

    _inherit = "res.company"

    pbx_domain = fields.Char(
        string="SIP Domain",
        help="The company's SIP domain on the Asterisk server, e.g. vertel.se",
    )
    pbx_server_host = fields.Char(
        string="PBX Server",
        help="Asterisk server address (empty = use the global setting)",
    )
    pbx_api_key = fields.Char(
        string="PBX API Key",
        groups="base.group_system",
        help="API-nyckel mot Asterisk-servern / provisioning-daemon",
    )
    pbx_odoo_url = fields.Char(
        string="Odoo URL",
        help="The customer's Odoo base URL that the generated dialplan calls "
             "for availability checks (e.g. https://crm.vertel.se). "
             "Empty = use web.base.url.",
    )
    pbx_sip_port = fields.Char(
        string="SIP Port",
        default="5061",
        help="SIP port for devices (5061 for WSS/WebRTC, 5060 for UDP/TCP)",
    )
    pbx_sip_ws_port = fields.Integer(
        string="WebSocket Port",
        default=8089,
        help="Asterisk HTTP/WebSocket port for the Odoo softphone (SIP.js). "
             "Default 8089 (WSS). Used when deriving ws_server if "
             "no explicit pbx_ws_server is specified.",
    )
    pbx_ws_server = fields.Char(
        string="WebSocket Server (override)",
        help="Explicit WebSocket URL for the Odoo softphone, e.g. "
             "wss://192.168.11.213:8089/ws. Empty = derived automatically from "
             "pbx_server_host + pbx_sip_ws_port.",
    )
    pbx_config_version = fields.Integer(
        string="PBX Config Version",
        default=0,
        help="Last published config version (incremented on every sync).",
    )
    pbx_config_applied_version = fields.Integer(
        string="PBX Config Applied Version",
        default=0,
        help="Last confirmed applied config version (from the daemon ack).",
    )
    pbx_config_sync_error = fields.Text(
        string="PBX Config Sync Error",
        help="Latest error message from the daemon ack (empty = no error).",
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
        help="Sync status: clean/applied = confirmed, sent = published without "
             "confirmation, error = the daemon reported an error.",
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
        help="Enable TURN for devices behind NAT (coturn handles both STUN "
        "discovery and TURN media relay on the same address).",
    )
    pbx_provisioning_token = fields.Char(
        string="PBX Provisioning-token",
        groups="pbx_base.group_pbx_admin,base.group_system",
        help="Secret token for the provisioning endpoint (hardware phones). "
             "The phone sends it as the password in the URL: "
             "https://<domain>:<token>@provision.../<MAC>.cfg",
    )

    def _ensure_pbx_provisioning_token(self):
        """Generate a provisioning token if it is missing (idempotent)."""
        import secrets

        for rec in self:
            if not rec.pbx_provisioning_token:
                rec.pbx_provisioning_token = secrets.token_urlsafe(24)
    config_dirty = fields.Boolean(
        string="PBX Config Dirty",
        default=False,
        help="True when configuration changes are waiting to be synced to Asterisk.",
    )

    def _pbx_mark_dirty(self):
        """Mark that the configuration needs to be synced to Asterisk."""
        if not self.config_dirty:
            self.config_dirty = True
