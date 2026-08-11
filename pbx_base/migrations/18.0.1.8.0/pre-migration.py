# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://vertel.se).

"""pbx_base 18.0.1.8.0 — rename pbx_sub_extension.priority → sequence.

Renames the stored column AND rewrites already-loaded ir.ui.view archs that
reference the old field name (otherwise the next module update fails view
validation with 'Field priority does not exist in pbx.sub_extension').

ir_ui_view.arch_db is a translated jsonb column ({"en_US": "<xml>"}), so the
replacement must go through the 'en_US' key to get unescaped XML text.
"""


def migrate(cr, version):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='pbx_sub_extension' AND column_name='priority'"
    )
    if cr.fetchone():
        cr.execute(
            "ALTER TABLE pbx_sub_extension RENAME COLUMN priority TO sequence"
        )
    cr.execute(
        "UPDATE ir_ui_view "
        "SET arch_db = jsonb_set("
        "    arch_db, '{en_US}',"
        "    to_jsonb(replace(arch_db->>'en_US', 'name=\"priority\"', 'name=\"sequence\"'))"
        ") "
        "WHERE arch_db->>'en_US' ILIKE '%sub_extension%' "
        "AND arch_db->>'en_US' LIKE '%name=\"priority\"%'"
    )
