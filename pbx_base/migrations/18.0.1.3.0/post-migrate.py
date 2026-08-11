# -*- coding: utf-8 -*-
"""Migrate to 18.0.1.3.0: flytta global SIP-domän till res.company.

Före: domänen låg i ir_config_parameter 'pbx.domain' (en global setting).
Efter: multicompany — varje företag har egen pbx_domain på res.company.

Kopierar värdet till huvudföretaget (id 1) om det inte redan är satt,
och rensar den globala parametern (ersatt av per-företag).
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
        _logger.info("pbx.domain '%s' flyttad till res.company (id=1)", row[0])
    cr.execute("DELETE FROM ir_config_parameter WHERE key = 'pbx.domain'")
    # server-host/api-key flyttas också (om de fanns)
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
    _logger.info("Migration 18.0.1.3.0 klar: SIP-domän per företag")
