# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from odoo.addons.pbx_base.models.pbx_destination_mixin import destination_models


def _company_id(company):
    """Acceptera recordset eller int — plugin-anrop får recordset."""
    return company.id if isinstance(company, models.Model) else company


class PbxQueue(models.Model):
    _name = "pbx.queue"
    _inherit = ["pbx.plugin", "pbx.destination.mixin"]
    _description = "PBX Call Queue"

    name = fields.Char(required=True)
    extension = fields.Char(
        required=True,
        default=lambda self: self._default_extension(),
        help="Internt anknytningsnummer för kön. Auto-genereras i tjänste-"
             "intervallet (4xx — separat från användarextensionerna) vid ny kö.",
    )
    strategy = fields.Selection(
        [
            ("ringall", "Ring All"),
            ("leastrecent", "Least Recent"),
            ("fewestcalls", "Fewest Calls"),
            ("random", "Random"),
            ("rrmemory", "Round Robin Memory"),
            ("linear", "Linear"),
            ("wrandom", "Weighted Random"),
        ],
        default="ringall",
    )
    timeout = fields.Integer(default=60, help="Seconds before trying next agent")
    max_wait_time = fields.Integer(default=300, help="Max wait time before overflow")
    overflow_destination_id = fields.Reference(
        selection=destination_models,
        string="Overflow Destination",
        help="Destination on overflow (extension, IVR, voicemail)",
    )
    join_empty = fields.Boolean(default=True, help="Accept calls when no agents are logged in?")
    announce_position = fields.Boolean(default=False)
    is_ring_group = fields.Boolean(
        default=False,
        help="When True: strategy forced to ringall, timeout=0, no overflow. Simple ring group."
    )
    is_manual = fields.Boolean(
        string="Manual/Reception Queue",
        help="Calls here need manual handling — Operator Panel visar dem med [Hantera]",
    )
    timeout_seconds = fields.Integer(
        string="Timeout (s)",
        default=0,
        help="Caller max wait in queue (0 = använd max_wait_time). Efter timeout → timeout_action",
    )
    timeout_action = fields.Selection(
        [
            ("route_to_manual_queue", "Route to manual queue"),
            ("hangup", "Hangup"),
        ],
        string="Timeout Action",
        default="route_to_manual_queue",
    )
    manual_target_queue_id = fields.Many2one(
        "pbx.queue",
        string="Manual Target Queue",
        help="Reception-kö som timeoutade samtal hamnar i",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company,
    )
    member_ids = fields.One2many("pbx.queue.member", "queue_id", string="Agents")

    @api.model
    def _default_extension(self):
        """Lägsta lediga nummer i köernas tjänsteintervall (4xx)."""
        if "pbx.numbering" not in self.env:
            return ""
        return (
            self.env["pbx.numbering"]._next_free_service_number(
                self.env.company, "queue"
            )
            or ""
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("extension"):
                company_id = vals.get("company_id") or self.env.company.id
                company = self.env["res.company"].browse(company_id)
                number = self.env["pbx.numbering"]._next_free_service_number(
                    company, "queue"
                )
                if number:
                    vals["extension"] = number
            if vals.get("company_id") and vals.get("extension"):
                company = self.env["res.company"].browse(vals["company_id"])
                self.env["pbx.numbering"]._check_dialable_number(
                    company, vals["extension"]
                )
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("extension") or vals.get("company_id"):
            for rec in self:
                company = (
                    self.env["res.company"].browse(vals["company_id"])
                    if vals.get("company_id")
                    else rec.company_id
                )
                number = vals.get("extension", rec.extension)
                self.env["pbx.numbering"]._check_dialable_number(
                    company, number, exclude=rec
                )
        return super().write(vals)

    def get_config_snippets(self, domain, company):
        queues = self.search([("company_id", "=", _company_id(company)), ("active", "=", True)])
        if not queues:
            return {}
        return {
            "queues.conf": self._generate_queues_conf(domain, queues),
            "extensions_queue.conf": self._generate_queue_dialplan(domain, queues),
        }

    def get_internal_dialplan(self, domain, company):
        """Make queues reachable by their internal extension number."""
        lines = []
        queues = self.search([("company_id", "=", _company_id(company)), ("active", "=", True)])
        for q in queues:
            lines.append(
                "exten => %s,1,Goto(%s-queue-%s,s,1)"
                % (q.extension, domain, self._slug(q.name))
            )
        return "\n".join(lines)

    def get_dialplan_target(self):
        self.ensure_one()
        domain = self.company_id.pbx_domain or ""
        return ("%s-queue-%s" % (domain, self._slug(self.name)), "s", "1")

    @staticmethod
    def _slug(name):
        return (name or "").lower().replace(" ", "-")

    def _generate_queue_dialplan(self, domain, queues):
        """Per-queue originate context (Operator Panel drag&drop / click-to-call).

        Redirect/Originate to Context=<domain>-queue-<name>, Exten=s.
        Timeout (t) → UserEvent(ManualRequired) + route to manual queue.
        """
        lines = [f"; Auto-generated by pbx_queue — domain: {domain}"]
        for q in queues:
            qname = q.name.lower().replace(" ", "-")
            full = f"{domain}-{qname}"
            lines.append(f"\n[{full}]")
            queue_call = f"Queue({full},t)" if q.timeout_seconds else f"Queue({full})"
            lines.append(f"exten => s,1,{queue_call}")
            lines.append("same => n,Hangup()")
            if q.timeout_seconds:
                if q.timeout_action == "route_to_manual_queue" and q.manual_target_queue_id:
                    tqname = q.manual_target_queue_id.name.lower().replace(" ", "-")
                    lines.append(f"exten => t,1,UserEvent(ManualRequired,source=queue_timeout,queue={full},target={domain}-{tqname})")
                    lines.append(f"exten => t,n,Queue({domain}-{tqname})")
                    lines.append("exten => t,n,Hangup()")
                else:
                    lines.append("exten => t,1,Hangup()")
        return "\n".join(lines)

    def _generate_queues_conf(self, domain, queues):
        lines = [f"; Auto-generated by pbx_queue — domain: {domain}"]
        for q in queues:
            strategy = "ringall" if q.is_ring_group else q.strategy
            timeout = 0 if q.is_ring_group else q.timeout
            lines.append(f"\n[{domain}-{q.name.lower().replace(' ', '-')}]")
            lines.append(f"strategy = {strategy}")
            lines.append(f"timeout = {timeout}")
            if q.is_manual:
                lines.append("; Manual/reception queue — kräver manuell hantering i Operator Panel")
            if not q.is_ring_group:
                max_wait = q.timeout_seconds or q.max_wait_time
                lines.append(f"max-wait-time = {max_wait}")
                lines.append(f"joinempty = {'no' if not q.join_empty else 'yes'}")
            for member in q.member_ids.filtered(lambda m: m.extension_id.active):
                lines.append(
                    f"member => PJSIP/{domain}-{member.extension_id.public_number},{member.penalty}"
                )
        return "\n".join(lines)

    def get_operator_panel_widgets(self):
        widgets = []
        queues = self.search(
            [("company_id", "=", self.env.user.company_id.id), ("active", "=", True)]
        )
        for q in queues:
            widgets.append(
                {
                    "name": f"queue_panel_{q.id}",
                    "component": "PbxQueuePanel",
                    "props": {
                        "queue": {
                            "key": q.extension,
                            "name": q.name,
                            "is_manual": q.is_manual,
                            "members": [
                                m.extension_id.public_number
                                for m in q.member_ids
                                if m.extension_id.active
                            ],
                        }
                    },
                }
            )
        return widgets


class PbxQueueMember(models.Model):
    _name = "pbx.queue.member"
    _description = "Queue Member (Agent)"

    queue_id = fields.Many2one("pbx.queue", required=True, ondelete="cascade")
    extension_id = fields.Many2one("pbx.extension", required=True, string="Agent Extension")
    penalty = fields.Integer(default=0, help="Lower = higher priority")
    paused = fields.Boolean(default=False)
    company_id = fields.Many2one(related="queue_id.company_id", store=True)
