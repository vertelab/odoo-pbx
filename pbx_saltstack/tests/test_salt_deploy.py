# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestSaltDeploy(TransactionCase):
    """pbx-saltstack: pillar-bygge, salt-kommando, dry-run, felhantering."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.pbx_domain = "test.se"
        cls.env.company.pbx_server_host = "asterisk01"
        cls.env.company.pbx_api_key = "k123"
        cls.server = cls.env["pbx.server"].create(
            {"name": "Asterisk 01", "host": "asterisk01"}
        )
        cls.tenant = cls.env["pbx.tenant"].create(
            {
                "name": "Vertel Test",
                "domain": "test.se",
                "server_id": cls.server.id,
                "company_id": cls.env.company.id,
                "minion_id": "luke18",
            }
        )

    def test_no_minion_raises(self):
        t = self.env["pbx.tenant"].create(
            {"name": "Utan minion", "domain": "test2.se", "server_id": self.server.id}
        )
        with self.assertRaises(UserError):
            t.deploy_config()

    def test_build_pillar(self):
        pillar = self.tenant._build_pillar()
        self.assertEqual(pillar["pbx"]["domain"], "test.se")
        self.assertEqual(pillar["pbx"]["server_host"], "asterisk01")
        self.assertEqual(pillar["pbx"]["api_key"], "k123")
        self.assertIn("mq", pillar["pbx"])
        self.assertIn("webhook_token", pillar["pbx"])

    def test_salt_command_shape(self):
        pillar = self.tenant._build_pillar()
        cmd = self.tenant._salt_command(pillar)
        self.assertTrue(cmd.startswith("salt 'luke18' state.apply odoo.pbx pillar='"))
        # pillar-json måste finnas i kommandot
        self.assertIn('"domain": "test.se"', cmd)

    def test_dry_run_deploy(self):
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("pbx_saltstack.dry_run", "true")
        res = self.tenant.deploy_config()
        self.assertEqual(res["status"], "dry-run")
        self.assertEqual(self.tenant.deploy_status, "dry-run")
        self.assertIn("salt 'luke18' state.apply", self.tenant.deploy_log)
        ICP.set_param("pbx_saltstack.dry_run", "false")
