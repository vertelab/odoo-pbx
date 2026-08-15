# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class PbxCodec(models.Model):
    """Codec-katalog.

    Central lista över tillgängliga codecs. "Vad som finns" styrs av
    Asterisk (via Salt-pushad `pbx.codecs.available`); `active` sätts av
    pbx_admin. Selektion per enhetstyp/enhet sker via pbx.codec.line
    (one2many, ordnad med sequence).
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
        help="Utgångsordning (från Salt-pushad lista). Vid ny selektion läggs "
             "raderna i denna ordning — användaren kan sedan dra om dem.",
    )
    supported = fields.Boolean(
        default=True,
        help="Finns på Asterisk (justeras vid sync från servern).",
    )
    active = fields.Boolean(
        default=True,
        help="Centralt på/av (pbx_admin). Inaktiva erbjuds inte i selektioner.",
    )
    description = fields.Char()

    _sql_constraints = [
        (
            "name_unique",
            "UNIQUE(name)",
            "Codec-namnet måste vara unikt!",
        ),
    ]

    @api.model
    def _sync_from_available(self):
        """Bygg/uppdatera katalogen från ir.config_parameter pbx.codecs.available.

        Parametern (kommaseparerad, ordning = priority) pushas till tenant-
        minioner via Salt (odoo/pbx.sls). Befintliga active/supported-värden
        bevaras; saknade codecs skapas som inactive.
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
                        "active": False,  # ny från Asterisk — avstängd tills admin aktiverar
                    }
                )
        return True

    def action_sync_codecs(self):
        """Sync-knapp (katalogen): bygg/uppdatera från pbx.codecs.available."""
        ok = self._sync_from_available()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Codecs",
                "message": "Katalogen uppdaterad från pbx.codecs.available"
                if ok
                else "Ingen pbx.codecs.available satt — seed-default gäller",
                "type": "success" if ok else "warning",
            },
        }

    def action_set_default_all_devices(self):
        """Sätt default-codec-listan på alla enheter utan egen selektion."""
        devices = self.env["pbx.sub_extension"].search([])
        devices._ensure_default_codecs()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Codecs",
                "message": "Default-codecs applicerade på %d enheter" % len(devices),
                "type": "success",
            },
        }


class PbxCodecLine(models.Model):
    """Ordrad codec-selektion (rad).

    En rad = en codec i en selektion. Exakt en förälder: antingen en
    device.template (default per enhetstyp) eller en sub_extension
    (den gällande listan per enhet). Ordningen (sequence) är codec-
    preferensen → pjsip allow-rader i samma ordning.
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
            "Codec-raden måste ha exakt en förälder (template eller enhet)!",
        ),
    ]
