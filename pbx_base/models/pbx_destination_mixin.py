# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models

#: Destination models that always exist when pbx_base is installed.
BASE_DESTINATION_MODELS = [
    ("pbx.extension", "Extension"),
    ("pbx.voicemail.destination", "Voicemail"),
    ("pbx.custom.destination", "Custom"),
]

#: Destination models provided by optional plugin modules.
PLUGIN_DESTINATION_MODELS = [
    ("pbx.queue", "Queue"),
    ("pbx.ivr", "IVR"),
    ("pbx.time_condition", "Time Condition"),
    ("pbx.conference", "Conference"),
]


def destination_models(records=None):
    """Selection for fields.Reference destination pickers.

    Returns only destination models whose module is actually installed
    (present in the registry/env). Plugin destinations (queue/ivr/conference/
    time_condition) are only offered when their module is installed.

    Odoo invokes the callable lazily via ``determine(selection, recordset)``
    with the model's recordset; ``records.env`` tells us which models exist.
    When called before env is ready (records=None), all plugins are included
    and the next lazy evaluation filters correctly.
    """
    env = getattr(records, "env", None)
    models = list(BASE_DESTINATION_MODELS)
    for model, label in PLUGIN_DESTINATION_MODELS:
        if env is None or model in env:
            models.append((model, label))
    return models


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
