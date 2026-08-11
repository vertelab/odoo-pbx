# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://vertel.se).

"""pbx_base 18.0.1.12.0 — backfill user↔extension link + implicit browser sub
+ shared SIP password + voip_oca sync.

Existing extensions (created before the auto-provisioning code) lack the
reverse res.users.pbx_extension_id link, the implicit "Odoo VOIP" (browser)
sub-extension and the shared per-person SIP password.
"""

from odoo import SUPERUSER_ID, api

from odoo.addons.pbx_base.models.pbx_sub_extension import _generate_sip_secret


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for ext in env["pbx.extension"].search([]):
        if not ext.password:
            ext.password = _generate_sip_secret()
        if not ext.sub_extension_ids.filtered(lambda s: s.type == "browser"):
            env["pbx.sub_extension"].create(
                {
                    "extension_id": ext.id,
                    "type": "browser",
                    "label": "Odoo VOIP",
                    "sequence": 1,
                }
            )
        if ext.user_id:
            ext.user_id.pbx_extension_id = ext.id
            ext._sync_voip()
