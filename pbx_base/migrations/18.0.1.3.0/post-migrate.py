# -*- coding: utf-8 -*-
"""Migrate to 18.0.1.3.0: move the global SIP domain to res.company.

Before: the domain lived in ir_config_parameter 'pbx.domain' (a global setting).
After: multicompany — each company has its own pbx_domain on res.company.

Copies the value to the main company (id 1) if it is not already set,
and clears the global parameter (replaced by per-company).
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        "SELECT value FROM ir_config_parameter WHERE key = 'pbx.domain'"
    )
    row = cr.fetchone()
    if row and row[0]:
        cr.execute(
            "UPDATE res_company SET pbx_domain = %s "
            "WHERE id = 1 AND (pbx_domain IS NULL OR pbx_domain = '')",
            (row[0],),
        )
        _logger.info("pbx.domain '%s' moved to res.company (id=1)", row[0])
    cr.execute("DELETE FROM ir_config_parameter WHERE key = 'pbx.domain'")
    # server-host/api-key are moved too (if they existed)
    for old_key, new_col in (
        ("pbx.server.host", "pbx_server_host"),
        ("pbx.api.key", "pbx_api_key"),
    ):
        cr.execute(
            "SELECT value FROM ir_config_parameter WHERE key = %s", (old_key,)
        )
        r = cr.fetchone()
        if r and r[0]:
            cr.execute(
                "UPDATE res_company SET %s = %%s WHERE id = 1 AND (%s IS NULL OR %s = '')"
                % (new_col, new_col, new_col),
                (r[0],),
            )
        cr.execute(
            "DELETE FROM ir_config_parameter WHERE key = %s", (old_key,)
        )
    _logger.info("Migration 18.0.1.3.0 done: SIP domain per company")
