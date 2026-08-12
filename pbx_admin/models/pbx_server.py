# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PbxServer(models.Model):
    _name = "pbx.server"
    _description = "PBX Server"

    name = fields.Char(required=True)
    host = fields.Char(required=True, default="localhost")
    ami_port = fields.Integer(default=5038)
    ami_user = fields.Char()
    ami_secret = fields.Char(groups="base.group_system")
    config_path = fields.Char(default="/etc/asterisk")
    spool_path = fields.Char(default="/var/spool/asterisk")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", string="Company")

    def reload_asterisk(self):
        """Ladda om Asterisk (pjsip) via MQ → daemonen (AMI Command)."""
        self.ensure_one()
        mq = self.env["pbx.mq.publisher"]
        ok = mq.publish("pbx.cmd.Action.Reload", {"Command": "pjsip reload"})
        return {"ok": bool(ok)}
