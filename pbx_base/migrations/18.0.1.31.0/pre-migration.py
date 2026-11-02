# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://vertel.se).

"""pbx_base 18.0.1.31.0 — Design A: one shared SIP password per extension.

`pbx.sub_extension.secret` (a per-device password) is removed. Every device
now authenticates with `pbx.extension.password`, the shared password of the
extension it belongs to.

Runs BEFORE the ORM drops the column: a device whose extension has no
password yet inherits its own `secret`, so no device loses its credentials
during the upgrade. Extensions that already have a password are left alone —
their devices were already using that one.
"""


def migrate(cr, version):
    if not version:
        return
    # Only touch rows where the extension has no password yet, and only when
    # the column still exists (idempotent on a re-run).
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'pbx_sub_extension' AND column_name = 'secret'
        """
    )
    if not cr.fetchone():
        return
    cr.execute(
        """
        UPDATE pbx_extension ext
           SET password = sub.secret
          FROM pbx_sub_extension sub
         WHERE sub.extension_id = ext.id
           AND (ext.password IS NULL OR ext.password = '')
           AND sub.secret IS NOT NULL
           AND sub.secret <> ''
        """
    )
