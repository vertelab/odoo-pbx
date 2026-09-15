# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import re
import secrets
import string

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _generate_sip_secret(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class PbxSubExtension(models.Model):
    _name = "pbx.sub_extension"
    _inherit = ["pbx.config.dirty.mixin"]
    _description = "PBX Sub Extension (individual device)"

    extension_id = fields.Many2one("pbx.extension", required=True, ondelete="cascade")
    number = fields.Char(
        string="Number",
        readonly=True,
        help="SIP identity for the device (auto-generated, e.g. 101 for extension 10). "
             "Has no relation to the ring order — sequence determines the order in which the devices ring.",
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
    sequence = fields.Integer(
        default=1,
        string="Sequence",
        help="Ring order (1 = first). Number has no relation to the ring order.",
    )
    ring_timeout = fields.Integer(
        default=10,
        help="How long (seconds) to ring this device before giving up. "
             "In sequential mode each device gets its own timeout; "
             "in parallel mode the longest timeout among active devices is used.",
    )
    transport = fields.Selection(
        [("wss", "WebSocket Secure"), ("udp", "UDP"), ("tcp", "TCP")],
        default="udp",
        string="Transport",
        help="wss for browser/Odoo VOIP (set automatically); udp/tcp for "
             "hardware phones and other devices.",
    )
    username = fields.Char(
        readonly=True,
        help="SIP username (auto-generated as u+number).",
    )
    secret = fields.Char(default=lambda self: _generate_sip_secret())
    active = fields.Boolean(
        default=True,
        help="When unchecked, this device is excluded from the generated dialplan.",
    )

    sip_config_display = fields.Char(
        string="SIP-konfiguration",
        compute="_compute_sip_config_display",
        help="Generated SIP parameters for the device: username, password, server, port, "
             "domain, protocol and STUN.",
    )

    config = fields.Json(
        string="SIP-konfiguration (resolverad)",
        compute="_compute_config",
        help="Per-parameter SIP configuration populated from the device type template "
             "(pbx.device.template) with real data.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-generate `number` (SIP identity) when it is not given.

        Convention: {extension.public_number}{index} → extension 10 gets devices
        101, 102, 103…  The lowest free number is chosen so that deletions or
        priority changes never cause collisions or renumbering. Numbers generated
        in the same batch are counted (otherwise several rows would collide on
        the same number).

        For provisioning: `mac_address` is normalised for the hardware type and
        `provisioning_token` is auto-generated for the desktop/mobile type.
        """
        used = {}
        for vals in vals_list:
            if vals.get("type") == "hardware" and vals.get("mac_address"):
                vals["mac_address"] = self._normalize_mac(vals["mac_address"])
            if vals.get("type") in ("desktop", "mobile"):
                vals.setdefault("provisioning_token", secrets.token_hex(16))
            if vals.get("extension_id"):
                ext_id = vals["extension_id"]
                if ext_id not in used:
                    used[ext_id] = set(
                        self.env["pbx.sub_extension"]
                        .search([("extension_id", "=", ext_id)])
                        .mapped("number")
                    )
                if vals.get("number"):
                    # Explicit numbers in the same batch are counted, otherwise
                    # generated numbers collide with them at flush.
                    used[ext_id].add(vals["number"])
                else:
                    number = self._next_free_number(ext_id, used[ext_id])
                    used[ext_id].add(number)
                    vals["number"] = number
                if vals.get("number"):
                    vals.setdefault(
                        "username",
                        "u%s" % re.sub(r"\D", "", vals["number"]),
                    )
            if vals.get("template_id") and not vals.get("transport"):
                tpl = self.env["pbx.device.template"].browse(vals["template_id"])
                if tpl.transport:
                    vals["transport"] = tpl.transport
        recs = super().create(vals_list)
        for rec in recs:
            rec._validate_provisioning_fields()
        recs._ensure_default_codecs()
        return recs

    def _ensure_default_codecs(self):
        """All devices get the default codec list (active + supported, in
        priority order) if no selection of their own has been set."""
        codecs = self.env["pbx.codec"].search(
            [("active", "=", True), ("supported", "=", True)]
        ).sorted("priority")
        for rec in self:
            if rec.codec_ids:
                continue
            rec.codec_ids = [
                (0, 0, {"sequence": idx * 10, "codec_id": codec.id})
                for idx, codec in enumerate(codecs, start=1)
            ]

    def write(self, vals):
        if vals.get("mac_address"):
            vals["mac_address"] = self._normalize_mac(vals["mac_address"])
        if vals.get("type") in ("desktop", "mobile"):
            # Only rotate if the token is missing (create handles generation).
            for rec in self:
                if not rec.provisioning_token:
                    vals.setdefault("provisioning_token", secrets.token_hex(16))
        res = super().write(vals)
        for rec in self:
            rec._validate_provisioning_fields()
        return res

    def _validate_provisioning_fields(self):
        """Hardware requires mac_address; other types must not have a MAC."""
        for rec in self:
            if rec.type == "hardware" and not rec.mac_address:
                raise ValidationError(
                    _("Hardware devices require a MAC address.")
                )

    @staticmethod
    def _normalize_mac(mac):
        """'00:15:65:A1:B2:C3' / '00-15-65-A1-B2-C3' → '001565a1b2c3'."""
        return re.sub(r"[^0-9a-fA-F]", "", mac or "").lower()

    @api.model
    def _next_free_number(self, extension_id, used=None):
        ext = self.env["pbx.extension"].browse(extension_id)
        prefix = "".join(ch for ch in str(ext.public_number or "") if ch.isdigit())
        if not prefix:
            prefix = "0"
        if used is None:
            used = set(
                self.env["pbx.sub_extension"]
                .search([("extension_id", "=", extension_id)])
                .mapped("number")
            )
        else:
            used = set(used)
        i = 1
        while True:
            candidate = "%s%d" % (prefix, i)
            if candidate not in used:
                return candidate
            i += 1

    @api.depends("username", "secret", "transport", "extension_id.password", "extension_id.company_id")
    def _compute_sip_config_display(self):
        for rec in self:
            company = rec.extension_id.company_id
            server = company.pbx_server_host or "«global setting missing»"
            domain = company.pbx_domain or "—"
            port = company.pbx_sip_port or (5061 if rec.transport == "wss" else 5060)
            stun = ""
            if company.pbx_turn_enabled:
                turn = self.env["ir.config_parameter"].sudo().get_param("pbx.turn.server", "")
                if turn:
                    stun = " | TURN: %s" % turn
            shared = rec.extension_id.password or rec.secret
            rec.sip_config_display = (
                "User: %s | Password: %s | Server: %s:%s | Domain: %s | "
                "Protocol: %s%s" % (rec.username, shared, server, port, domain, rec.transport, stun)
            )

    @api.depends(
        "type",
        "username",
        "secret",
        "transport",
        "mac_address",
        "provisioning_token",
        "template_id",
        "extension_id.password",
        "extension_id.public_number",
        "extension_id.user_id",
        "extension_id.company_id",
    )
    def _compute_config(self):
        """Resolved SIP configuration from the device type template.

        Template priority: explicit template_id → company-specific per type →
        global per type (company_id=False).
        """
        for rec in self:
            template = rec.template_id
            if not template:
                template = self.env["pbx.device.template"].search(
                    [
                        ("device_type", "=", rec.type),
                        ("company_id", "in", [rec.extension_id.company_id.id, False]),
                        ("active", "=", True),
                    ],
                    limit=1,
                    order="company_id DESC NULLS LAST",
                )
            if not template or not template.config_template:
                rec.config = False
                continue
            rec.config = rec._populate_config(template.config_template)

    def _populate_config(self, config_template):
        """Populate the template's parameter definitions with real data.

        Returns {"<param_key>": {"label": …, "value": <live value>, "help": …}}
        """
        self.ensure_one()
        if isinstance(config_template, str):
            # XML data may deliver the Json field as a string — parse defensively.
            try:
                config_template = json.loads(config_template or "{}")
            except (ValueError, TypeError):
                config_template = {}
        resolved = {}
        ext = self.extension_id
        company = ext.company_id
        sources = {
            "device": self,
            "extension": ext,
            "company": company,
            "user": ext.user_id,
        }
        ICP = self.env["ir.config_parameter"].sudo()
        for key, spec in sorted(
            (config_template or {}).items(),
            key=lambda kv: (kv[1] or {}).get("order", 99),
        ):
            if not isinstance(spec, dict):
                continue
            source = spec.get("source")
            only_if = spec.get("only_if")
            if only_if and not getattr(company, only_if, False):
                continue
            if source == "static":
                value = spec.get("value", "")
            elif source == "config":
                # Global config (t.ex. TURN/STUN provisionerade av pbx_admin)
                value = ICP.get_param(spec.get("field", ""), "")
            else:
                record = sources.get(source)
                if record is None:
                    continue
                value = getattr(record, spec.get("field", ""), False)
                if value in (False, None):
                    value = ""
                value = str(value)
            resolved[key] = {
                "label": spec.get("label", key),
                "value": value,
                "help": spec.get("help", ""),
            }
        return resolved

    config_display = fields.Char(
        string="SIP configuration (detail)",
        compute="_compute_config_display",
        help="Readable per-parameter SIP configuration (from the device type template).",
    )

    @api.depends("config", "sip_config_display")
    def _compute_config_display(self):
        for rec in self:
            if rec.config:
                rec.config_display = "\n".join(
                    "%s: %s" % (p["label"], p["value"])
                    for p in rec.config.values()
                )
            else:
                rec.config_display = rec.sip_config_display

    # Voicemail fields
    greeting = fields.Many2one("ir.attachment", string="Greeting")
    max_duration = fields.Integer(default=120, help="Max recording duration (seconds)")
    max_messages = fields.Integer(default=100)
    delete_after_days = fields.Integer(default=30)
    transcribe_enabled = fields.Boolean(default=False)

    # Provisioning (pbx-provisioning): hardware keyed by MAC, softphones by token
    mac_address = fields.Char(
        string="MAC address",
        help="Physical device MAC — provisioning key for hardware phones. "
             "Normalised to lower case without separators (001565a1b2c3).",
    )
    codec_ids = fields.One2many(
        "pbx.codec.line",
        "sub_extension_id",
        string="Codecs",
        help="The effective codec list for the device (ordered — sequence is "
             "the preference). Left empty → the template default / global default.",
    )
    template_id = fields.Many2one(
        "pbx.device.template",
        string="Device Template",
        help="Device template that controls the SIP configuration. Choose a template → "
             "the configuration is adapted to the device.",
    )

    @api.onchange("template_id")
    def _onchange_template_id(self):
        """On template selection: suggest transport (and default codecs) from the template."""
        if not self.template_id:
            return
        if self.template_id.transport:
            self.transport = self.template_id.transport
    device_model = fields.Char(
        string="Device Model",
        help="e.g. T46S — to select the correct shared provisioning config.",
    )
    provisioning_token = fields.Char(
        string="Provisioning Token",
        copy=False,
        groups="pbx_base.group_pbx_admin",
        help="Per-device token for softphone provisioning (desktop/mobile). "
             "Auto-generated; the URL is /pbx/provisioning/softphone/<token>.xml",
    )

    _sql_constraints = [
        (
            "sub_ext_unique",
            "unique(extension_id, number)",
            "Sub-extension number must be unique per extension!",
        ),
        (
            "sub_ext_mac_unique",
            "unique(mac_address)",
            "The MAC address may only be used by one device!",
        ),
        (
            "sub_ext_token_unique",
            "unique(provisioning_token)",
            "The provisioning token must be unique!",
        ),
    ]
