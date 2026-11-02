# Copyright 2026 Vertel Sverige AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged


@tagged("-post_install", "at_install")
class TestCrmClickToCallViews(TransactionCase):
    """pbx-click-to-call 3.2 — the ring icon is on the phone fields.

    The manual check ("open a lead, look for the icon") is replaced by
    asserting the rendered view arch the web client actually receives:
    `get_views()` returns the inherited arch, so the assertion fails if the
    view inheritance is dropped.
    """

    def _arch(self, model):
        views = self.env[model].get_views([(False, "form")])
        return views["views"]["form"]["arch"]

    def test_crm_lead_phone_fields_have_call_widget(self):
        arch = self._arch("crm.lead")
        for field in ("phone", "mobile"):
            self.assertIn(
                'widget="pbx_call"',
                arch,
                "crm.lead.%s must carry the click-to-call widget" % field,
            )

    def test_partner_phone_fields_have_call_widget(self):
        arch = self._arch("res.partner")
        for field in ("phone", "mobile"):
            self.assertIn(
                'widget="pbx_call"',
                arch,
                "res.partner.%s must carry the click-to-call widget" % field,
            )
