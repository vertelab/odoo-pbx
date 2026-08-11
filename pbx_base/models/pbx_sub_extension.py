# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import secrets
import string

from odoo import api, fields, models


def _generate_sip_secret(length=16):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class PbxSubExtension(models.Model):
    _name = "pbx.sub_extension"
    _description = "PBX Sub Extension (individual device)"

    extension_id = fields.Many2one("pbx.extension", required=True, ondelete="cascade")
    number = fields.Char(
        string="Nummer",
        readonly=True,
        help="SIP-identitet för enheten (auto-genererat, t.ex. 101 för anknytning 10). "
             "Har ingen koppling till ringordningen — priority styr i vilken ordning enheterna ringer.",
    )
    label = fields.Char(help="e.g. Odoo, Yealink, Mobile")
    type = fields.Selection(
        [
            ("browser", "Odoo VOIP"),
            ("desktop", "Desktop Softphone"),
            ("hardware", "Hardware Phone"),
            ("mobile", "Mobile"),
            ("voicemail", "Voicemail"),
        ],
        default="browser",
        required=True,
    )
    priority = fields.Integer(default=1, help="Ring priority (1 = first, 99 = last)")
    ring_timeout = fields.Integer(
        default=30,
        help="How long (seconds) to ring this device before giving up. "
             "In sequential mode each device gets its own timeout; "
             "in parallel mode the longest timeout among active devices is used.",
    )
    transport = fields.Selection(
        [("wss", "WebSocket Secure"), ("udp", "UDP"), ("tcp", "TCP")],
        default="wss",
    )
    username = fields.Char(default=lambda self: _generate_sip_secret(8))
    secret = fields.Char(default=lambda self: _generate_sip_secret())
    active = fields.Boolean(
        default=True,
        help="When unchecked, this device is excluded from the generated dialplan.",
    )

    sip_config_display = fields.Char(
        string="SIP-konfiguration",
        compute="_compute_sip_config_display",
        help="Genererade SIP-parametrar för enheten: username, lösenord, server, port, "
             "domän, protokoll och STUN.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-generera `number` (SIP-identitet) när den inte anges.

        Konvention: {extension.public_number}{index} → anknytning 10 får enheter
        101, 102, 103…  Minsta lediga nummer väljs så att raderingar/prio-byten
        aldrig orsakar kollisioner eller omnumrering.
        """
        for vals in vals_list:
            if not vals.get("number") and vals.get("extension_id"):
                vals["number"] = self._next_free_number(vals["extension_id"])
        return super().create(vals_list)

    @api.model
    def _next_free_number(self, extension_id):
        ext = self.env["pbx.extension"].browse(extension_id)
        prefix = "".join(ch for ch in str(ext.public_number or "") if ch.isdigit())
        if not prefix:
            prefix = "0"
        existing = set(
            self.env["pbx.sub_extension"]
            .search([("extension_id", "=", extension_id)])
            .mapped("number")
        )
        i = 1
        while True:
            candidate = "%s%d" % (prefix, i)
            if candidate not in existing:
                return candidate
            i += 1

    @api.depends("username", "secret", "transport", "extension_id.company_id")
    def _compute_sip_config_display(self):
        for rec in self:
            company = rec.extension_id.company_id
            server = company.pbx_server_host or "«central inställning saknas»"
            domain = company.pbx_domain or "—"
            port = company.pbx_sip_port or (5061 if rec.transport == "wss" else 5060)
            stun = ""
            if company.pbx_stun_enabled and company.pbx_stun_server:
                stun = " | STUN: %s" % company.pbx_stun_server
            rec.sip_config_display = (
                "Användare: %s | Lösenord: %s | Server: %s:%s | Domän: %s | "
                "Protokoll: %s%s" % (rec.username, rec.secret, server, port, domain, rec.transport, stun)
            )

    # Voicemail fields
    greeting = fields.Many2one("ir.attachment", string="Greeting")
    max_duration = fields.Integer(default=120, help="Max recording duration (seconds)")
    max_messages = fields.Integer(default=100)
    delete_after_days = fields.Integer(default=30)
    transcribe_enabled = fields.Boolean(default=False)

    _sql_constraints = [
        (
            "sub_ext_unique",
            "unique(extension_id, number)",
            "Sub-extension number must be unique per extension!",
        ),
    ]
