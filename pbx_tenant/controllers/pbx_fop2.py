# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PbxFop2(http.Controller):
    """FOP2 operator panel — data + actions.

    Grid: extensions + queues + IVR as virtual extensions, scoped by role
    (receptionist sees everything, agent sees own queues).
    Actions: published to RabbitMQ `pbx.cmd.Action.#` via pbx.mq.publisher.
    """

    # ── helpers ──────────────────────────────────────────────────

    def _current_tenant(self):
        user = request.env.user
        ext = user.pbx_extension_id
        if ext and ext.tenant_id:
            return ext.tenant_id
        return request.env["pbx.tenant"].search(
            [("company_id", "=", user.company_id.id)], limit=1
        )

    def _is_receptionist(self):
        ext = request.env.user.pbx_extension_id
        return bool(ext and ext.is_receptionist)

    # ── data ─────────────────────────────────────────────────────

    @http.route("/pbx/fop2/grid", type="json", auth="user", methods=["POST"])
    def fop2_grid(self, **kwargs):
        tenant = self._current_tenant()
        if not tenant:
            return {"extensions": [], "queues": [], "ivrs": [], "is_receptionist": False}

        is_receptionist = self._is_receptionist()
        user_ext = request.env.user.pbx_extension_id

        extensions = request.env["pbx.extension"].search(
            [("tenant_id", "=", tenant.id), ("active", "=", True)]
        )
        queues = request.env["pbx.queue"].search(
            [("tenant_id", "=", tenant.id), ("active", "=", True)]
        )
        ivrs = request.env["pbx.ivr"].search(
            [("tenant_id", "=", tenant.id), ("active", "=", True)]
        )

        if not is_receptionist and user_ext:
            # Agent: own extension + queues the user is a member of
            member_queues = request.env["pbx.queue.member"].search(
                [("extension_id", "=", user_ext.id)]
            ).queue_id
            queues = queues & member_queues
            extensions = extensions.filtered(lambda e: e.id == user_ext.id)
            ivrs = request.env["pbx.ivr"].search([("id", "=", False)])

        return {
            "domain": tenant.domain,
            "extensions": [
                {
                    "key": e.public_number,
                    "type": "extension",
                    "description": e.description or e.callerid_name or e.user_id.name or e.public_number,
                    "is_receptionist": e.is_receptionist,
                }
                for e in extensions
            ],
            "queues": [
                {
                    "key": q.extension,
                    "type": "queue",
                    "description": q.name,
                    "is_manual": q.is_manual,
                    "timeout": q.timeout_seconds,
                }
                for q in queues
            ],
            "ivrs": [
                {
                    "key": i.extension,
                    "type": "ivr",
                    "description": i.name,
                }
                for i in ivrs
            ],
            "is_receptionist": is_receptionist,
        }

    @http.route("/pbx/fop2/widgets", type="json", auth="user", methods=["POST"])
    def fop2_widgets(self, **kwargs):
        """Collect FOP2 widget declarations from all pbx.plugin models."""
        tenant = self._current_tenant()
        if not tenant:
            return {"widgets": []}
        widgets = []
        for plugin in request.env["pbx.plugin"].search([]):
            widgets += plugin.get_fop2_widgets()
        return {"widgets": widgets}

    # ── actions (Odoo → MQ → daemon → AMI) ───────────────────────

    @http.route("/pbx/fop2/hangup", type="json", auth="user", methods=["POST"])
    def fop2_hangup(self, channel=None, **kwargs):
        if not channel:
            return {"status": "error", "error": "missing channel"}
        ok = request.env["pbx.mq.publisher"].action_hangup(channel)
        return {"status": "ok" if ok else "error"}

    @http.route("/pbx/fop2/redirect", type="json", auth="user", methods=["POST"])
    def fop2_redirect(self, channel=None, context=None, exten=None, priority=1, **kwargs):
        if not channel or not context or not exten:
            return {"status": "error", "error": "missing channel/context/exten"}
        ok = request.env["pbx.mq.publisher"].action_redirect(channel, context, exten, priority)
        return {"status": "ok" if ok else "error"}

    @http.route("/pbx/fop2/chanspy", type="json", auth="user", methods=["POST"])
    def fop2_chanspy(self, extension=None, mode="q", **kwargs):
        if not extension:
            return {"status": "error", "error": "missing extension"}
        ok = request.env["pbx.mq.publisher"].action_chanspy(extension, mode)
        return {"status": "ok" if ok else "error"}

    @http.route("/pbx/fop2/originate", type="json", auth="user", methods=["POST"])
    def fop2_originate(self, target=None, **kwargs):
        """Click-to-call: ring the operator's device, then the target.

        target = extension number, queue (queue:<name>) or external number.
        """
        user = request.env.user
        ext = user.pbx_extension_id
        tenant = self._current_tenant()
        if not ext or not tenant:
            return {"status": "error", "error": "no extension/tenant"}
        if not target:
            return {"status": "error", "error": "missing target"}

        domain = tenant.domain
        context = f"{domain}-internal"
        if target.startswith("queue:"):
            queue_name = target.split(":", 1)[1]
            q = request.env["pbx.queue"].search(
                [("tenant_id", "=", tenant.id), ("name", "=", queue_name)], limit=1
            )
            if not q:
                return {"status": "error", "error": "queue not found"}
            qname = q.name.lower().replace(" ", "-")
            ok = request.env["pbx.mq.publisher"].action_originate(
                tenant.server_id,
                f"SIP/{domain}-{ext.public_number}",
                f"{domain}-queue-{qname}",
                "s",
            )
            return {"status": "ok" if ok else "error"}
        else:
            target_ext = request.env["pbx.extension"].search(
                [("tenant_id", "=", tenant.id), ("public_number", "=", target)], limit=1
            )
            if target_ext:
                context = f"{domain}-internal"
                exten = target
            elif target.startswith("conference:"):
                conf_name = target.split(":", 1)[1]
                qname = conf_name.lower().replace(" ", "-")
                context = f"{domain}-conf-{qname}"
                exten = "s"
            else:
                # external number via default trunk context
                context = f"{domain}-outbound"
                exten = target
            ok = request.env["pbx.mq.publisher"].action_originate(
                tenant.server_id, f"SIP/{domain}-{ext.public_number}", context, exten
            )
            return {"status": "ok" if ok else "error"}

    @http.route("/pbx/fop2/queue_pause", type="json", auth="user", methods=["POST"])
    def fop2_queue_pause(self, queue=None, paused=True, **kwargs):
        user = request.env.user
        ext = user.pbx_extension_id
        if not ext or not queue:
            return {"status": "error", "error": "missing queue/extension"}
        ok = request.env["pbx.mq.publisher"].action_queue_pause(
            f"SIP/{ext.tenant_id.domain}-{ext.public_number}", queue, paused
        )
        return {"status": "ok" if ok else "error"}

    @http.route("/pbx/fop2/mixmonitor", type="json", auth="user", methods=["POST"])
    def fop2_mixmonitor(self, channel=None, file="recording", stop=True, **kwargs):
        """Start/stop MixMonitor recording on a channel."""
        if not channel:
            return {"status": "error", "error": "missing channel"}
        ok = request.env["pbx.mq.publisher"].action_mixmonitor(channel, file, stop)
        return {"status": "ok" if ok else "error"}

    @http.route("/pbx/fop2/deploy_config", type="json", auth="user", methods=["POST"])
    def fop2_deploy_config(self, **kwargs):
        """Regenerate + deploy tenant config via MQ (Odoo-ägd)."""
        tenant = self._current_tenant()
        if not tenant:
            return {"status": "error", "error": "no tenant"}
        ok = request.env["pbx.config.generator"].write_config(tenant)
        return {"status": "ok" if ok else "error"}
