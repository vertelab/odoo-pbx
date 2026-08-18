# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import models

_logger = logging.getLogger(__name__)

try:
    import pika
except ImportError:
    pika = None


class PbxMqPublisher(models.AbstractModel):
    """Publishes messages to the PBX RabbitMQ topic exchange.

    Publish-only with short-lived connections — safe with multiple Odoo
    workers (no persistent consumer threads inside the Odoo process).

    Config via ir.config_parameter:
      pbx.mq.host     (default: företagets pbx_server_host, fallback localhost)
      pbx.mq.port     (default 5672)
      pbx.mq.user     (default pbx)
      pbx.mq.password
      pbx.mq.vhost    (default: företagets pbx_domain, fallback pbx)
    """

    _name = "pbx.mq.publisher"
    _description = "PBX RabbitMQ Publisher"

    # ── Connection ──────────────────────────────────────────────

    def _get_config(self):
        ICP = self.env["ir.config_parameter"].sudo()
        company = self.env.company
        # Host härleds från företagets PBX-server (RabbitMQ körs på samma
        # maskin som Asterisk i standarduppsättningen). Vhost härleds från
        # SIP-domänen (tenant == domän == topic).
        mq_host = ICP.get_param("pbx.mq.host", "")
        if not mq_host:
            mq_host = company.pbx_server_host or "localhost"
        mq_vhost = ICP.get_param("pbx.mq.vhost", "")
        if not mq_vhost:
            mq_vhost = company.pbx_domain or "pbx"
        return {
            "host": mq_host,
            "port": int(ICP.get_param("pbx.mq.port", "5672")),
            "user": ICP.get_param("pbx.mq.user", "pbx"),
            "password": ICP.get_param("pbx.mq.password", "pbx"),
            "vhost": mq_vhost,
        }

    def publish(self, routing_key, payload):
        """Publish a JSON message to the pbx topic exchange."""
        if pika is None:
            _logger.error("pika not installed — cannot publish %s", routing_key)
            return False
        cfg = self._get_config()
        try:
            params = pika.URLParameters(
                "amqp://{user}:{password}@{host}:{port}/{vhost}".format(**cfg)
            )
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.exchange_declare(
                exchange="pbx", exchange_type="topic", durable=True
            )
            channel.basic_publish(
                exchange="pbx",
                routing_key=routing_key,
                body=json.dumps(payload).encode(),
                properties=pika.BasicProperties(
                    content_type="application/json", delivery_mode=2
                ),
            )
            connection.close()
            _logger.info("Published %s", routing_key)
            return True
        except Exception as e:
            _logger.error("MQ publish %s failed: %s", routing_key, e)
            return False

    # ── Actions (Operator Panel → AMI via daemon) ─────────────────────────

    def action_hangup(self, channel, server_id=False):
        return self.publish(
            "pbx.cmd.Action.Hangup", {"Channel": channel}
        )

    def action_redirect(self, channel, context, exten, priority=1):
        return self.publish(
            "pbx.cmd.Action.Redirect",
            {"Channel": channel, "Context": context, "Exten": exten, "Priority": priority},
        )

    def action_chanspy(self, extension, mode="q"):
        return self.publish(
            "pbx.cmd.Action.ChanSpy", {"extension": extension, "mode": mode}
        )

    def action_originate(self, server, channel, context, exten, priority=1):
        return self.publish(
            "pbx.cmd.Action.Originate",
            {"Channel": channel, "Context": context, "Exten": exten, "Priority": priority},
        )

    def action_queue_pause(self, interface, queue, paused=True):
        return self.publish(
            "pbx.cmd.Action.QueuePause",
            {"Interface": interface, "Queue": queue, "Paused": "true" if paused else "false"},
        )

    def action_mixmonitor(self, channel, file, stop=False):
        if stop:
            return self.publish(
                "pbx.cmd.Action.MixMonitor",
                {"Action": "Stop", "Channel": channel},
            )
        return self.publish(
            "pbx.cmd.Action.MixMonitor",
            {"Action": "Start", "Channel": channel, "File": file},
        )

    # ── Config deploy (Odoo-ägd generering → daemon) ────────────

    def publish_config(self, domain, configs, version=None, reload=True):
        """Publish a generated config set for the instance's domain.

        Returns the published version (int) on success, False on failure.
        """
        if version is None:
            version = int(
                self.env["ir.config_parameter"]
                .sudo()
                .get_param(f"pbx.config.version.{domain}", "0")
            ) + 1
            self.env["ir.config_parameter"].sudo().set_param(
                f"pbx.config.version.{domain}", str(version)
            )
        ok = self.publish(
            f"pbx.config.{domain}",
            {
                "domain": domain,
                "version": version,
                "files": configs,
                "reload": reload,
            },
        )
        return version if ok else False
