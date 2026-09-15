# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class PbxCodec(models.Model):
    """Codec catalogue.

    Central list of available codecs. "What exists" is controlled by
    Asterisk (via the Salt-pushed `pbx.codecs.available`); `active` is set by
    pbx_admin. Selection per device type/device happens via pbx.codec.line
    (one2many, ordered by sequence).
    """

    _name = "pbx.codec"
    _description = "PBX Codec"
    _order = "priority, name"
    _inherit = ["pbx.config.dirty.mixin"]

    name = fields.Char(required=True, help="pjsip-namn, t.ex. g722, ulaw, alaw, opus")
    kind = fields.Selection(
        [
            ("audio", "Audio"),
            ("video", "Video"),
            ("text", "Text"),
            ("image", "Image"),
        ],
        default="audio",
        required=True,
    )
    priority = fields.Integer(
        default=10,
        help="Output order (from the Salt-pushed list). New selections append "
             "rows in this order — the user can then drag to rearrange them.",
    )
    supported = fields.Boolean(
        default=True,
        help="Exists on Asterisk (adjusted on sync from the server).",
    )
    active = fields.Boolean(
        default=True,
        help="Centrally on/off (pbx_admin). Inactive codecs are not offered in selections.",
    )
    description = fields.Char()

    _sql_constraints = [
        (
            "name_unique",
            "UNIQUE(name)",
            "The codec name must be unique!",
        ),
    ]

    @api.model
    def _sync_from_available(self):
        """Build/update the catalogue from ir.config_parameter pbx.codecs.available.

        The parameter (comma-separated, order = priority) is pushed to tenant
        minions via Salt (odoo/pbx.sls). Existing active/supported values are
        preserved; missing codecs are created as inactive.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        raw = ICP.get_param("pbx.codecs.available", "")
        names = [n.strip() for n in raw.split(",") if n.strip()]
        if not names:
            return False
        existing = {c.name: c for c in self.search([])}
        for idx, name in enumerate(names, start=1):
            if name in existing:
                existing[name].write({"priority": idx * 10})
            else:
                self.create(
                    {
                        "name": name,
                        "priority": idx * 10,
                        "active": False,  # new from Asterisk — disabled until an admin enables it
                    }
                )
        return True

    @api.model
    def action_sync_codecs(self):
        """Sync button (catalogue): build/update from pbx.codecs.available."""
        ok = self._sync_from_available()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Codecs",
                "message": "Catalogue updated from pbx.codecs.available"
                if ok
                else "No pbx.codecs.available set — the seed default applies",
                "type": "success" if ok else "warning",
            },
        }

    @api.model
    def action_deploy_devices(self):
        """Deploy button (catalogue): apply the default codec list to all
        devices without their own selection (selections are preserved)."""
        devices = self.env["pbx.sub_extension"].search([])
        devices._ensure_default_codecs()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Codecs",
                "message": "Default codecs applied to %d devices" % len(devices),
                "type": "success",
            },
        }


class PbxCodecLine(models.Model):
    """Ordered codec selection (row).

    One row = one codec in a selection. Exactly one parent: either a
    device.template (default per device type) or a sub_extension
    (the effective list per device). The order (sequence) is the codec-
    preference → pjsip allow lines in the same order.
    """

    _name = "pbx.codec.line"
    _description = "PBX Codec Selection Line"
    _order = "sequence, id"
    _inherit = ["pbx.config.dirty.mixin"]

    sequence = fields.Integer(default=10)
    codec_id = fields.Many2one("pbx.codec", required=True, ondelete="cascade")
    codec_name = fields.Char(related="codec_id.name", string="Codec")
    codec_description = fields.Char(related="codec_id.description", string="Beskrivning")
    template_id = fields.Many2one(
        "pbx.device.template",
        string="Template",
        ondelete="cascade",
    )
    sub_extension_id = fields.Many2one(
        "pbx.sub_extension",
        string="Device",
        ondelete="cascade",
    )

    _sql_constraints = [
        (
            "check_single_parent",
            "CHECK((template_id IS NOT NULL)::int + (sub_extension_id IS NOT NULL)::int = 1)",
            "A codec row must have exactly one parent (template or device)!",
        ),
    ]
