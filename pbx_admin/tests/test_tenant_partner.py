# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestTenantAsPartner(TransactionCase):
    """pbx-tenant-as-partner: res.partner + is_pbx_tenant, unikt domain,
    minion-sync (dry-run), felhantering."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = cls.env["pbx.server"].create(
            {"name": "Asterisk 01", "host": "asterisk01"}
        )

    def _make_tenant(self, name="Vertel Test", domain="test.se", **kw):
        vals = {
            "name": name,
            "is_pbx_tenant": True,
            "domain": domain,
            "server_id": self.server.id,
        }
        vals.update(kw)
        return self.env["res.partner"].create(vals)

    def test_tenant_flag(self):
        partner = self._make_tenant()
        self.assertTrue(partner.is_pbx_tenant)
        # visas i tenant-sökningen
        found = self.env["res.partner"].search(
            [("is_pbx_tenant", "=", True)]
        )
        self.assertIn(partner, found)

    def test_non_tenant_not_in_kanban_domain(self):
        normal = self.env["res.partner"].create({"name": "Vanlig kund"})
        tenants = self.env["res.partner"].search([("is_pbx_tenant", "=", True)])
        self.assertNotIn(normal, tenants)

    def test_unique_domain_on_tenants(self):
        self._make_tenant(domain="unik.se")
        with self.cr.savepoint():
            with self.assertRaises(Exception):
                self._make_tenant(name="Dublett", domain="unik.se")

    def test_non_tenant_may_share_empty_domain(self):
        self.env["res.partner"].create({"name": "A", "domain": ""})
        self.env["res.partner"].create({"name": "B", "domain": ""})

    def test_deploy_no_minion_raises(self):
        tenant = self._make_tenant()
        with self.assertRaises(UserError):
            tenant.deploy_config()

    def test_deploy_non_tenant_raises(self):
        normal = self.env["res.partner"].create({"name": "Inte tenant"})
        with self.assertRaises(UserError):
            normal.deploy_config()

    def test_deploy_dry_run(self):
        tenant = self._make_tenant()
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("pbx_admin.salt_dry_run", "true")
        # utan minion → dry-run kräver ändå minion (fel först)
        # sätt en minion utan att salt-api behövs (dry-run bygger bara pillar)
        tenant.minion_id = self.env["salt.minion"].create({"name": "test-minion"}).id
        res = tenant.deploy_config()
        self.assertEqual(res["status"], "dry-run")
        self.assertEqual(tenant.deploy_status, "dry-run")
        self.assertIn("state.apply odoo.pbx", tenant.deploy_log)
        self.assertIn("domain", res["pillar"]["pbx"])
        ICP.set_param("pbx_admin.salt_dry_run", "false")

    def test_build_pillar(self):
        tenant = self._make_tenant(
            domain="pillar.se", server_id=self.server.id
        )
        pillar = tenant._build_pillar()
        self.assertEqual(pillar["pbx"]["domain"], "pillar.se")
        self.assertEqual(pillar["pbx"]["server_host"], "asterisk01")
        self.assertIn("mq", pillar["pbx"])
        self.assertIn("webhook_token", pillar["pbx"])
