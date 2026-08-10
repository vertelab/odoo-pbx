# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models

#: Destination models shown in every fields.Reference destination picker.
#: Every listed model must implement pbx.destination.mixin and provide
#: get_dialplan_target() returning a (context, exten, prio) goto-triple —
#: the single dialplan language used by inbound routes, IVR options, time
#: conditions, queue overflows and outbound failover (FreePBX-style dest).
DESTINATION_MODELS = [
    ("pbx.extension", "Extension"),
    ("pbx.queue", "Queue"),
    ("pbx.ivr", "IVR"),
    ("pbx.time_condition", "Time Condition"),
    ("pbx.conference", "Conference"),
    ("pbx.voicemail.destination", "Voicemail"),
    ("pbx.custom.destination", "Custom"),
]


class PbxDestinationMixin(models.AbstractModel):
    _name = "pbx.destination.mixin"
    _description = "PBX Destination Interface"

    def get_dialplan_target(self):
        """Return the (context, exten, prio) goto-triple for this destination.

        Every destination model implements this method. Routers render it
        into a Goto() via _render_destination().
        """
        raise NotImplementedError(
            "Model %s must implement get_dialplan_target()" % self._name
        )

    def get_internal_number(self):
        """Return the internal extension number used to dial this destination
        directly, or None when it is not directly dialable."""
        return None

    @api.model
    def _render_destination(self, ref_value):
        """Render a fields.Reference destination to a dialplan Goto() string.

        ref_value may be a resolved recordset (Odoo reads Reference fields
        as recordsets) or a "model,id" string.
        """
        if not ref_value:
            return "Hangup()"
        if isinstance(ref_value, models.Model):
            record = ref_value
        else:
            model, _, res_id = ref_value.partition(",")
            record = self.env[model].browse(int(res_id))
        ctx, exten, prio = record.get_dialplan_target()
        return "Goto(%s,%s,%s)" % (ctx, exten, prio)
