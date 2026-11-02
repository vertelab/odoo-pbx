# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://vertel.se).

"""pbx_base 18.0.1.52.0 — Design A cleanup: drop the per-device secret column.

The ORM no longer knows about `pbx.sub_extension.secret` (removed in 6.1), so
the column is dead weight after the upgrade. It is dropped here rather than in
pre-migration so the pre-migration can still read it for the backfill.

Also strips `secret` references from stored view archs. No shipped view
references `pbx.sub_extension.secret` any more, but a customer database may
have a stale inherited view from before Design A — the same failure mode as
18.0.1.14.0 (skip_if_busy) where a removed field in a stored arch breaks the
next module update with a view validation error.

Idempotent: both steps check for existence first.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # 1. Strip stored-view references to the removed field. `secret` is a
    #    common field name (pbx.trunk has one too), so only touch archs that
    #    mention pbx.sub_extension.
    cr.execute(
        """
        UPDATE ir_ui_view
           SET arch_db = jsonb_set(
                   arch_db, '{en_US}',
                   to_jsonb(replace(arch_db->>'en_US',
                                    '<field name="secret"/>', ''))
               )
         WHERE arch_db->>'en_US' LIKE '%<field name="secret"/>%'
           AND (arch_db->>'en_US' LIKE '%pbx.sub_extension%'
                OR arch_db->>'en_US' LIKE '%pbx_sub_extension%')
        """
    )
    if cr.rowcount:
        _logger.info(
            "pbx_base 18.0.1.52.0: stripped a removed field from %s stored view(s)",
            cr.rowcount,
        )

    # 2. Drop the dead column. The ORM already ignores it, but leaving it
    #    around invites a future migration to read stale per-device passwords.
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'pbx_sub_extension' AND column_name = 'secret'
        """
    )
    if cr.fetchone():
        cr.execute("ALTER TABLE pbx_sub_extension DROP COLUMN secret")
        _logger.info("pbx_base 18.0.1.52.0: dropped pbx_sub_extension.secret")
