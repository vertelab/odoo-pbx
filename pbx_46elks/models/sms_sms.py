from odoo import models, fields, api, exceptions, _, http

import logging
_logger = logging.getLogger(__name__)


class SmsSms(models.Model):
    _inherit = 'sms.sms'

    def _send(self, delete_all=False, raise_exception=False):
        env = self.env
        _logger.error("Hej1")
        IrConfigParameter = env['ir.config_parameter'].sudo()
        _logger.error("Hej2")
        provider = IrConfigParameter.get_param('46elks.provider', default='')
        _logger.error("provider = " + str(provider))
        if provider == "1":
            return

        return super(SmsSms, self)._send(delete_all=delete_all, raise_exception=raise_exception)

    def _process_queue(self, ids=None):
        env = self.env
        _logger.error(f"{env=}")
        IrConfigParameter = env['ir.config_parameter'].sudo()
        provider = IrConfigParameter.get_param('46elks.provider', default='')
        if provider == "1":
            _logger.error("_process_queue overriden")
            return None

        return super(SmsSms, self)._process_queue(ids)