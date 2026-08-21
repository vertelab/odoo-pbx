# -*- coding: utf-8 -*-
"""Tester för pbx-ai-extension-coworker — coworker-as-extension.

Körs med: odoo --test-enable -u pbx_ai (eller checkmodule -t).
"""

from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestCoworkerExtension(common.TransactionCase):
    """7.1: extension-härledning (coworker → employee → user → ext)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['ai.agent'].create({'name': 'Test-Agent'})
        cls.coworker = cls.env['ai.coworker'].create({
            'name': 'Test-Coworker',
            'model_ids': [(6, 0, [cls.env['ir.model']._get('project.task').id])],
        })
        # Leader-agent-koppling
        cls.env['ai.coworker.agent'].create({
            'coworker_id': cls.coworker.id,
            'agent_id': cls.agent.id,
            'role': 'leader',
        })
        # Anställd (is_ai) + användare med personal_coworker_id
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test-Coworker',
            'is_ai': True,
            'ai_coworker_id': cls.coworker.id,
        })
        cls.user = cls.env['res.users'].create({
            'name': 'Test-Coworker User',
            'login': 'ai-test-coworker@example.com',
            'email': 'ai-test-coworker@example.com',
            'personal_coworker_id': cls.coworker.id,
        })
        cls.coworker.write({'employee_id': cls.employee.id})
        cls.extension = cls.env['pbx.extension'].create({
            'public_number': '6099',
            'callerid_name': 'Test-AI-ext',
            'user_id': cls.user.id,
        })

    def test_get_pbx_extension(self):
        """Coworkerns anknytning härleds ur personen."""
        ext = self.coworker._get_pbx_extension()
        self.assertEqual(ext.id, self.extension.id)

    def test_get_pbx_extension_number(self):
        self.assertEqual(
            self.coworker._get_pbx_extension_number(),
            '6099')

    def test_is_ai_extension(self):
        self.assertTrue(self.extension._is_ai_extension())
        self.assertEqual(
            self.extension._get_ai_coworker().id, self.coworker.id)

    def test_inactive_coworker_not_ai(self):
        self.coworker.write({'active': False})
        self.assertFalse(self.extension._is_ai_extension())
        self.coworker.write({'active': True})


@tagged('post_install', '-at_install')
class TestCoworkerDialplan(common.TransactionCase):
    """7.2: dialplan-generator Stasis(coworker) + follow-me-AI."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['ai.agent'].create({'name': 'Test-Agent2'})
        cls.coworker = cls.env['ai.coworker'].create({
            'name': 'Test-Coworker2',
            'model_ids': [(6, 0, [cls.env['ir.model']._get('project.task').id])],
        })
        cls.env['ai.coworker.agent'].create({
            'coworker_id': cls.coworker.id,
            'agent_id': cls.agent.id,
            'role': 'leader',
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test-Coworker2',
            'is_ai': True,
            'ai_coworker_id': cls.coworker.id,
        })
        cls.user = cls.env['res.users'].create({
            'name': 'Test-Coworker2 User',
            'login': 'ai-test-coworker2@example.com',
            'email': 'ai-test-coworker2@example.com',
            'personal_coworker_id': cls.coworker.id,
        })
        cls.coworker.write({'employee_id': cls.employee.id})
        cls.extension = cls.env['pbx.extension'].create({
            'public_number': '6098',
            'callerid_name': 'Test-AI-ext2',
            'user_id': cls.user.id,
            'follow_me_ai_coworker_id': cls.coworker.id,
        })

    def test_internal_dialplan_stasis(self):
        """AI-anknytning → Stasis(coworker,<id>) i internal dialplan."""
        pbx_ai = self.env['pbx.ai']
        dialplan = pbx_ai.get_internal_dialplan('testdomain', self.env.company)
        self.assertIn(
            f"Stasis(coworker,{self.coworker.id})", dialplan)

    def test_follow_me_fallback_ai(self):
        """Follow-me-fallback → Stasis(coworker) när AI-destination satt."""
        generator = self.env['pbx.config.generator']
        fallback = generator._follow_me_fallback(
            self.extension, 'testdomain')
        self.assertIn('Stasis(coworker,', fallback)

    def test_follow_me_fallback_voicemail_default(self):
        """Utan AI-destination → voicemail som vanligt."""
        generator = self.env['pbx.config.generator']
        ext = self.env['pbx.extension'].create({
            'public_number': '6097',
            'callerid_name': 'Test-plain',
        })
        fallback = generator._follow_me_fallback(ext, 'testdomain')
        self.assertIn('Voicemail(', fallback)
