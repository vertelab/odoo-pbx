# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

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
        # shown in the tenant search
        found = self.env["res.partner"].search(
            [("is_pbx_tenant", "=", True)]
        )
        self.assertIn(partner, found)

    def test_non_tenant_not_in_kanban_domain(self):
        normal = self.env["res.partner"].create({"name": "Ordinary Customer"})
        tenants = self.env["res.partner"].search([("is_pbx_tenant", "=", True)])
        self.assertNotIn(normal, tenants)

    def test_unique_domain_on_tenants(self):
        self._make_tenant(domain="unik.se")
        with self.cr.savepoint():
            with self.assertRaises(Exception):
                self._make_tenant(name="Dublett", domain="unik.se")

    def test_non_tenant_may_share_empty_domain(self):
        self.env["res.partner"].create({"name": "A", "domain": ""})
        b = self.env["res.partner"].create({"name": "B", "domain": ""})
        self.assertFalse(b.is_pbx_tenant)

    def test_deploy_no_minion_raises(self):
        tenant = self._make_tenant()
        with self.assertRaises(UserError):
            tenant.deploy_config()

    def test_deploy_non_tenant_raises(self):
        normal = self.env["res.partner"].create({"name": "Not a tenant"})
        with self.assertRaises(UserError):
            normal.deploy_config()

    def test_deploy_dry_run(self):
        tenant = self._make_tenant()
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("pbx_admin.salt_dry_run", "true")
        # without a minion → dry-run still requires a minion (error first)
        # set a minion without needing salt-api (dry-run only builds the pillar)
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

    # ------------------------------------------------------------------
    # 5.3 (was: manual click-through in luke18) — the tenant UI contract
    # ------------------------------------------------------------------

    def test_tenant_is_partner_with_chatter_and_archive(self):
        """A tenant is a res.partner: chatter, archive ribbon and Notes.

        The manual click-through (kanban -> form -> chatter -> Notes ->
        archive ribbon) is replaced by asserting the data contract the views
        rely on: the model inherits mail.thread (chatter), has `active`
        (archive ribbon) and `comment` (the Notes page), and the tenant form
        view renders those fields.
        """
        tenant = self._make_tenant(name="Chatter AB", domain="chatter.se")
        model_fields = tenant._fields
        self.assertIn("message_ids", model_fields)
        self.assertIn("message_follower_ids", model_fields)
        self.assertIn("activity_ids", model_fields)
        self.assertIn("active", model_fields)
        self.assertIn("comment", model_fields)

        # chatter works on a tenant record
        tenant.message_post(body="Tenant created")
        self.assertTrue(tenant.message_ids)

        # archive ribbon: archiving keeps the record but drops it from the
        # tenant kanban (active_test on the action domain)
        tenant.action_archive()
        self.assertFalse(tenant.active)
        self.assertNotIn(
            tenant,
            self.env["res.partner"].search([("is_pbx_tenant", "=", True)]),
        )
        self.assertIn(
            tenant,
            self.env["res.partner"].with_context(active_test=False).search(
                [("is_pbx_tenant", "=", True)]
            ),
        )

        # the tenant form view exposes the Notes page bound to `comment`
        form = self.env.ref("pbx_admin.pbx_tenant_form")
        self.assertIn('name="comment"', form.arch_db)
        self.assertIn('string="Notes"', form.arch_db)
        self.assertIn('name="deploy_config"', form.arch_db)

        # the kanban view is the one the Tenants action opens first
        action = self.env.ref("pbx_admin.pbx_tenant_act_window")
        self.assertEqual(action.view_mode.split(",")[0], "kanban")
        self.assertIn("is_pbx_tenant", action.domain)

    # ------------------------------------------------------------------
    # 6.2 (was: E2E minion-sync -> salt -> odoo/pbx.sls) — the salt contract
    # ------------------------------------------------------------------

    def test_deploy_salt_payload(self):
        """The Minion-sync payload is exactly what odoo/pbx.sls consumes.

        The E2E (real minion, real state.apply, real Odoo DB on the minion) is
        a deployment question. Here we pin the contract on our side: the
        salt-api call shape and the pillar keys the state reads.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("pbx.mq.host", "")
        ICP.set_param("pbx.mq.port", "5672")
        ICP.set_param("pbx.mq.user", "")
        ICP.set_param("pbx.mq.password", "")
        ICP.set_param("pbx.mq.vhost", "")
        ICP.set_param("pbx.webhook.token", "wh-token-123")
        ICP.set_param("pbx.turn.server", "turn.test.se:3478")
        ICP.set_param("pbx_admin.salt_db_name", "odoo")
        ICP.set_param("pbx_admin.salt_dry_run", "false")

        company = self.env.company
        company.pbx_api_key = "api-key-abc"
        tenant = self._make_tenant(domain="payload.se", company_id=company.id)
        tenant.minion_id = self.env["salt.minion"].create(
            {"name": "payload-minion"}
        ).id

        calls = []

        def fake_call_salt_api(client, tgt, fun, *args, **kwargs):
            calls.append(
                {
                    "client": client,
                    "tgt": tgt,
                    "fun": fun,
                    "args": args,
                    "kwargs": kwargs,
                }
            )
            return {"return": [{"payload-minion": {"result": True}}]}

        tenant.minion_id._call_salt_api = fake_call_salt_api
        res = tenant.deploy_config()

        # 1. the salt-api call shape (same as bifrost_saltstack)
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call["client"], "local")
        self.assertEqual(call["tgt"], "payload-minion")
        self.assertEqual(call["fun"], "state.apply")
        self.assertEqual(call["args"], ("odoo.pbx",))
        self.assertIn("pillar", call["kwargs"])

        # 2. the pillar keys odoo/pbx.sls writes into the minion's Odoo
        pbx = call["kwargs"]["pillar"]["pbx"]
        self.assertEqual(
            sorted(pbx),
            [
                "api_key",
                "db_name",
                "domain",
                "mq",
                "server_host",
                "turn_server",
                "webhook_token",
            ],
        )
        self.assertEqual(pbx["domain"], "payload.se")
        self.assertEqual(pbx["server_host"], "asterisk01")
        self.assertEqual(pbx["api_key"], "api-key-abc")
        self.assertEqual(pbx["webhook_token"], "wh-token-123")
        self.assertEqual(pbx["turn_server"], "turn.test.se:3478")
        self.assertEqual(pbx["db_name"], "odoo")
        self.assertEqual(
            sorted(pbx["mq"]), ["host", "password", "port", "user", "vhost"]
        )
        # RabbitMQ derives host/vhost/user from the SIP domain when unset
        self.assertEqual(pbx["mq"]["host"], "asterisk01")
        self.assertEqual(pbx["mq"]["port"], "5672")
        self.assertEqual(pbx["mq"]["user"], "payload.se")
        self.assertEqual(pbx["mq"]["vhost"], "payload.se")
        self.assertEqual(pbx["mq"]["password"], "api-key-abc")

        # 3. the pillar is JSON-serialisable (it is sent over HTTP)
        json.dumps(call["kwargs"]["pillar"])

        # 4. status is recorded on the tenant partner
        self.assertEqual(res["status"], "ok")
        self.assertEqual(tenant.deploy_status, "ok")
        self.assertTrue(tenant.last_deploy)
        self.assertIn("payload-minion", tenant.deploy_log)

    def test_deploy_salt_error_is_recorded(self):
        """A failing state.apply lands on the tenant as status=error + log."""
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("pbx_admin.salt_dry_run", "false")
        tenant = self._make_tenant(domain="fail.se")
        tenant.minion_id = self.env["salt.minion"].create(
            {"name": "fail-minion"}
        ).id

        def boom(*args, **kwargs):
            raise RuntimeError("salt-api unreachable")

        tenant.minion_id._call_salt_api = boom
        res = tenant.deploy_config()
        self.assertEqual(res["status"], "error")
        self.assertEqual(tenant.deploy_status, "error")
        self.assertIn("salt-api unreachable", tenant.deploy_log)
