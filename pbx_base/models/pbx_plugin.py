# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class PbxPlugin(models.AbstractModel):
    _name = "pbx.plugin"
    _description = "PBX Plugin Interface"

    def get_config_snippets(self, tenant):
        """Return Asterisk config snippets for a tenant.

        Returns dict: {filename: content}
        Called during config generation for each active plugin.
        """
        self.ensure_one()
        return {}

    def get_internal_dialplan(self, tenant):
        """Return dialplan lines contributed to the tenant's [domain-internal] context.

        Returns str with lines like 'exten => 20,1,Goto(domain-queue-support,s,1)'.
        Makes queues, IVRs and conferences reachable by their internal number.
        """
        self.ensure_one()
        return ""

    def get_ami_handlers(self):
        """Return AMI event -> handler mappings.

        Returns dict: {ami_event_name: handler_method_name}
        """
        self.ensure_one()
        return {}

    def get_operator_widgets(self):
        """Return OWL components for the admin operator panel.

        Returns list of {name, component, props}
        """
        self.ensure_one()
        return []

    def get_fop2_widgets(self):
        """Return OWL components for the customer FOP2 panel.

        Returns list of {name, component, props}
        """
        self.ensure_one()
        return []

    def get_notification_handlers(self):
        """Return RabbitMQ/NATS event -> handler mappings.

        Returns dict: {event_type: handler_method_name}
        """
        self.ensure_one()
        return []
