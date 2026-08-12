# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://vertel.se).

"""pbx_base 18.0.1.14.0 — strip removed skip_if_busy fields from stored views.

`skip_if_busy` (pbx.extension) and `pbx_skip_if_busy` (res.users proxy) were
removed; stored ir.ui.view archs still referencing them break the next module
update ('Field does not exist' view validation error).
"""


def migrate(cr, version):
    cr.execute(
        "UPDATE ir_ui_view "
        "SET arch_db = jsonb_set("
        "    arch_db, '{en_US}',"
        "    to_jsonb(replace(replace(arch_db->>'en_US',"
        "        '<field name=\"pbx_skip_if_busy\"/>', ''),"
        "        '<field name=\"skip_if_busy\"/>', ''))"
        ") "
        "WHERE arch_db->>'en_US' LIKE '%skip_if_busy%'"
    )
