#!/usr/bin/env python3
# Copyright 2026 Vertel AB
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
pbx_ami_daemon — Bridges Asterisk AMI with RabbitMQ/NATS.

Connects to Asterisk Manager Interface, listens for telephony events,
filters by tenant domain, and publishes to RabbitMQ/NATS topics.
Also subscribes to command topics and translates them to AMI actions.

Usage:
    pbx-ami-daemon --config /etc/pbx-ami-daemon/config.yaml
"""

import argparse
import base64
import asyncio
import json
import logging
import os
import re
import signal
import socket
import sys
import time
import urllib.request
from typing import Optional

import yaml

try:
    import aio_pika
except ImportError:
    aio_pika = None

logger = logging.getLogger("pbx_ami_daemon")

# ──────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────


def load_config(path: str) -> dict:
    with open(path) as f:
        raw = f.read()
    # Expand ${ENV_VAR} placeholders
    raw = os.path.expandvars(raw)
    return yaml.safe_load(raw)


# ──────────────────────────────────────────────────────────────────
# State Cache
# ──────────────────────────────────────────────────────────────────


class StateCache:
    """In-memory cache of device states, published on change."""

    def __init__(self, publisher):
        self._states: dict[str, dict] = {}
        self._publisher = publisher

    def set(self, extension: str, state: str):
        old = self._states.get(extension, {}).get("state")
        if old != state:
            self._states[extension] = {"state": state, "updated": int(time.time())}
            asyncio.ensure_future(
                self._publisher(
                    f"pbx.state.Device.{extension}",
                    {"extension": extension, "state": state},
                )
            )

    def get(self, extension: str) -> Optional[str]:
        entry = self._states.get(extension)
        return entry["state"] if entry else None

    def all(self) -> dict:
        return dict(self._states)


# ──────────────────────────────────────────────────────────────────
# AMI Connection
# ──────────────────────────────────────────────────────────────────


class AMIConnection:
    """Persistent TCP connection to Asterisk Manager Interface."""

    def __init__(self, host: str, port: int, user: str, secret: str):
        self.host = host
        self.port = port
        self.user = user
        self.secret = secret
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._buffer = b""
        self._event_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self):
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port
        )
        # Read banner
        banner = await asyncio.wait_for(self._reader.readline(), 5)
        logger.info("AMI connected: %s", banner.decode().strip())

        # Login
        self._writer.write(
            f"Action: Login\r\nUsername: {self.user}\r\nSecret: {self.secret}\r\n\r\n".encode()
        )
        await self._writer.drain()
        response = await asyncio.wait_for(self._reader.readuntil(b"\r\n\r\n"), 5)
        if b"Success" not in response:
            raise ConnectionError(f"AMI login failed: {response.decode()}")

        logger.info("AMI authenticated")

    async def disconnect(self):
        if self._writer:
            self._writer.write(b"Action: Logoff\r\n\r\n")
            await self._writer.drain()
            self._writer.close()
            self._writer = None
            self._reader = None

    async def send_action(self, action: str, wait_response: bool = True, **params) -> dict:
        """Send an AMI action and return the parsed response.

        ``wait_response=False`` sends fire-and-forget (write only) — used by
        the config consumer for reloads, because ``read_events`` keeps a
        pending ``readline()`` on the same stream and a concurrent read would
        raise "readuntil() called while another coroutine is already waiting
        for incoming data". Responses to fire-and-forget actions are consumed
        by the event loop and dropped silently (no ``Event`` header).
        """
        if not self._writer:
            raise ConnectionError("Not connected")

        msg = f"Action: {action}\r\n"
        for k, v in params.items():
            msg += f"{k}: {v}\r\n"
        msg += "\r\n"

        self._writer.write(msg.encode())
        await self._writer.drain()

        if not wait_response:
            return {}

        # Read response
        response = await asyncio.wait_for(self._reader.readuntil(b"\r\n\r\n"), 10)
        return self._parse_ami_message(response.decode())

    async def read_events(self):
        """Generator yielding parsed AMI events."""
        while self._reader:
            try:
                line = await asyncio.wait_for(self._reader.readline(), 30)
                if not line:
                    raise ConnectionError("AMI connection closed")

                self._buffer += line
                if line == b"\r\n":
                    raw = self._buffer.decode("utf-8", errors="replace")
                    self._buffer = b""
                    if raw.strip():
                        yield self._parse_ami_message(raw)
            except asyncio.TimeoutError:
                # Send keepalive
                pass
            except Exception:
                break

    @staticmethod
    def _parse_ami_message(raw: str) -> dict:
        result = {}
        for line in raw.strip().split("\r\n"):
            if ": " in line:
                key, _, value = line.partition(": ")
                result[key.strip()] = value.strip()
        return result


# ──────────────────────────────────────────────────────────────────
# Tenant Detection
# ──────────────────────────────────────────────────────────────────


def _load_known_domains(config_path: str) -> set:
    """Kända domäner från tenant-config-filerna (tenants/<domän>-*.conf).

    Använder suffix-strippning (inte split på bindestreck) eftersom domänen
    själv kan innehålla bindestreck (t.ex. pbx-test.vertel.se).
    """
    suffixes = (
        "-extensions.conf",
        "-pjsip_wizard.conf",
        "-voicemail.conf",
    )
    domains = set()
    try:
        for name in os.listdir(config_path):
            for suffix in suffixes:
                if name.endswith(suffix):
                    domains.add(name[: -len(suffix)])
    except OSError:
        pass
    return domains


def extract_tenant_from_event(
    event: dict, known_domains: Optional[set] = None
) -> Optional[str]:
    """Extract tenant domain from an AMI event.

    Endpoints/channels är nu PJSIP/u<username>-… (utan domän), så domänen
    kan inte längre hämtas från kanalnamnet. Prioritet:
    1. Kända domäner (från tenants/<domän>-*.conf på disk) som prefix på
       Context/DestinationContext/Channel — Context fält är alltid
       <domän>-internal/ext/vm/…
    2. @domän-suffix (CallerIDNum/Mailbox m.m.)
    3. SIP/domän-prefix (legacy kanalnamn)
    """
    candidates = [
        event.get("Context", ""),
        event.get("DestinationContext", ""),
        event.get("Channel", ""),
        event.get("CallerIDNum", ""),
        event.get("Mailbox", ""),
        event.get("DestChannel", ""),
    ]

    if known_domains:
        for candidate in candidates:
            for domain in known_domains:
                if candidate.startswith(domain):
                    return domain

    # @domain suffix — med kända domäner accepteras bara exakt match
    # (Local-kanaler är "Local/01@<context>;<uniqueid>" — får inte tolkas
    # som domän)
    for candidate in candidates:
        at_match = re.search(r"@(\S+)", candidate)
        if at_match:
            domain = at_match.group(1)
            if re.match(r"\d+\.\d+\.\d+\.\d+", domain):
                continue
            if known_domains:
                if domain in known_domains:
                    return domain
            else:
                return domain

    # Legacy SIP/domain-… prefix
    for candidate in candidates:
        sip_match = re.match(r"SIP/([^@-]+)-[0-9]+", candidate)
        if sip_match:
            return sip_match.group(1)

    return None


# ──────────────────────────────────────────────────────────────────
# Webhook Publisher
# ──────────────────────────────────────────────────────────────────


def _read_voicemail_audio(event: dict) -> Optional[str]:
    """Läs voicemail-inspelningen (msg0001.wav) från spool-katalogen och
    returnera base64 — Odoo ligger på annan maskin och kan inte läsa filen.
    """
    spool_dir = event.get("Dir", "") or ""
    if not spool_dir:
        return None
    path = os.path.join(spool_dir, "msg0001.wav")
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except OSError as e:
        logger.warning("Could not read voicemail audio %s: %s", path, e)
        return None


class WebhookPublisher:
    """POSTs events to the tenant Odoo /pbx/webhook endpoint.

    Uses urllib in a worker thread to avoid a new async dependency.
    Empty url disables the webhook leg (MQ publishing still works).
    """

    def __init__(self, url: str = "", token: str = "", tokens: Optional[dict] = None):
        self.url = url
        self.token = token
        self.tokens = tokens or {}

    def _token_for(self, tenant: str) -> str:
        return self.tokens.get(tenant, self.token)

    def post(self, tenant: str, routing_key: str, data: dict):
        if not self.url:
            return
        token = self._token_for(tenant)
        payload = json.dumps(
            {"tenant": tenant, "topic": routing_key, "event": data}
        ).encode()
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception as e:
            logger.warning("Webhook POST failed: %s", e)

    async def publish(self, tenant: str, routing_key: str, data: dict):
        await asyncio.to_thread(self.post, tenant, routing_key, data)


# ──────────────────────────────────────────────────────────────────
# Event Consumer
# ──────────────────────────────────────────────────────────────────


class EventConsumer:
    """Consumes AMI events, filters by tenant, publishes to RabbitMQ."""

    INTERESTING_EVENTS = {
        "Newchannel",
        "Hangup",
        "Dial",
        "Bridge",
        "DeviceStateChange",
        "QueueEntry",
        "QueueMemberStatus",
        "PeerStatus",
        "VoicemailMessage",
        "Newstate",
        "UserEvent",
        "Cdr",
    }

    def __init__(
        self, ami: AMIConnection, publisher, state_cache: StateCache,
        webhook=None, known_domains: Optional[set] = None,
    ):
        self.ami = ami
        self.publisher = publisher
        self.state_cache = state_cache
        self.webhook = webhook or WebhookPublisher()
        self.known_domains = known_domains or set()

    async def run(self):
        async for event in self.ami.read_events():
            event_name = event.get("Event", "")
            if event_name not in self.INTERESTING_EVENTS:
                continue

            tenant = extract_tenant_from_event(event, self.known_domains)
            if not tenant:
                continue

            # Special handling for device state
            if event_name in ("DeviceStateChange", "PeerStatus"):
                device = event.get("Device", "")
                state = event.get("State", "Unknown")
                # Extract extension number from device name
                ext_match = re.search(rf"{tenant}-(\d+)", device)
                if ext_match:
                    ext_number = ext_match.group(1)
                    self.state_cache.set(ext_number, state)

            # Publish to tenant-specific topic
            topic = f"pbx.event.{tenant}.AMI.{event_name}"
            await self.publisher(topic, event)
            if event_name == "VoicemailMessage":
                # Bifoga ljudet (base64) — Odoo läser inte spool-filen lokalt
                payload = dict(event)
                audio = _read_voicemail_audio(event)
                if audio:
                    payload["_audio_base64"] = audio
                await self.webhook.publish(tenant, topic, payload)
            else:
                await self.webhook.publish(tenant, topic, event)


# ──────────────────────────────────────────────────────────────────
# Command Server
# ──────────────────────────────────────────────────────────────────


class CommandServer:
    """Subscribes to RabbitMQ command topics, executes AMI actions."""

    AMI_ACTION_MAP = {
        "pbx.cmd.Action.Originate": "Originate",
        "pbx.cmd.Action.Hangup": "Hangup",
        "pbx.cmd.Action.Redirect": "Redirect",
        "pbx.cmd.Action.QueuePause": "QueuePause",
        "pbx.cmd.Action.MixMonitor": "MixMonitor",
        "pbx.cmd.Action.Reload": "Command",
    }

    def __init__(self, ami: AMIConnection):
        self.ami = ami

    async def handle_command(self, routing_key: str, body: dict):
        action = self.AMI_ACTION_MAP.get(routing_key)
        if not action:
            logger.warning("Unknown command topic: %s", routing_key)
            return

        params = body.copy()
        params.pop("routing_key", None)

        if routing_key == "pbx.cmd.Action.Reload":
            params["Command"] = "pjsip reload"

        if routing_key == "pbx.cmd.Action.ChanSpy":
            action = "Originate"
            # ChanSpy is an Originate to a special application
            extension = params.pop("extension", "")
            mode = params.pop("mode", "q")
            params["Application"] = "ChanSpy"
            params["Data"] = f"SIP/{extension},{mode}"

        try:
            # Fire-and-forget: read_events() has a pending readline() on the same
            # stream — a concurrent readuntil() would raise "readuntil() called
            # while another coroutine is already waiting for incoming data".
            # Response is consumed by the event loop and dropped (no Event header).
            response = await self.ami.send_action(action, wait_response=False, **params)
            logger.debug("AMI action %s response: %s", action, response)
            return response
        except Exception as e:
            logger.error("AMI action %s failed: %s", action, e)
            return None


# ──────────────────────────────────────────────────────────────────
# Config Consumer
# ──────────────────────────────────────────────────────────────────


class ConfigConsumer:
    """Applies Asterisk config delivered by Odoo via pbx.config.#.

    Message body (new format):
        {
          "domain": "vertel.se",
          "version": 42,
          "files": [
            {"name": "pjsip_wizard.conf", "config_type": "tenant",
             "content": "..."},
            {"name": "vertel.se.conf", "config_type": "manager",
             "content": "..."},
            {"name": "vertel.se.conf", "config_type": "ari",
             "content": "..."}
          ],
          "reload": true
        }

    Legacy format (dict) is still accepted: ``{"filename": "content"}`` —
    all files are treated as tenant config.

    Files are routed by ``config_type``:
      - tenant  → ``{config_path}/tenants/<domain>-<name>``
      - manager → ``{manager_path}/<name>``  (must be ``<domain>.conf``)
      - ari     → ``{ari_path}/<name>``      (must be ``<domain>.conf``)

    Versioning: the last applied version per domain is kept in
    ``{config_path}/.state.json``; messages with version <= applied are
    ignored (acked as ``skipped``).
    """

    CONFIG_TYPES = ("tenant", "manager", "ari")

    def __init__(
        self, ami, config_path, publisher=None, webhook=None,
        manager_path=None, ari_path=None,
    ):
        self.ami = ami
        self.config_path = config_path
        self.manager_path = manager_path or os.path.join(
            os.path.dirname(config_path), "manager.d"
        )
        self.ari_path = ari_path or os.path.join(
            os.path.dirname(config_path), "ari.d"
        )
        self.publisher = publisher
        self.webhook = webhook
        self._state_path = os.path.join(config_path, ".state.json")
        self._state_lock = asyncio.Lock()

    # ── Version state ─────────────────────────────────────────────

    def _load_state(self) -> dict:
        try:
            with open(self._state_path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    async def _save_state(self, domain: str, version: int):
        async with self._state_lock:
            state = self._load_state()
            if int(state.get(domain, {}).get("version", 0) or 0) >= version:
                return
            state[domain] = {"version": version}
            tmp = self._state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state, f)
            os.replace(tmp, self._state_path)

    def _last_applied(self, domain: str) -> int:
        return int(
            self._load_state().get(domain, {}).get("version", 0) or 0
        )

    # ── Parsing & routing ─────────────────────────────────────────

    @staticmethod
    def _parse_files(files) -> list:
        """Accept new list format or legacy dict; return list of
        {"name", "config_type", "content"}."""
        if isinstance(files, dict):
            return [
                {"name": name, "config_type": "tenant", "content": content}
                for name, content in files.items()
            ]
        if isinstance(files, list):
            return [
                {
                    "name": item.get("name", ""),
                    "config_type": item.get("config_type", "tenant"),
                    "content": item.get("content", ""),
                }
                for item in files
                if isinstance(item, dict)
            ]
        return []

    def _target_for(self, domain: str, item: dict):
        """Return (abs_path, display) or None if the file must be skipped."""
        name = os.path.basename(item.get("name", "") or "")
        config_type = item.get("config_type", "tenant")
        if not name:
            return None
        if config_type not in self.CONFIG_TYPES:
            logger.warning("Unknown config_type %s for %s — skipped", config_type, name)
            return None
        if config_type == "tenant":
            return os.path.join(self.config_path, f"{domain}-{name}"), name
        # manager/ari: instansen får bara skriva sin egen fil
        expected = f"{domain}.conf"
        if name != expected:
            logger.warning(
                "%s file %s does not match instance prefix %s — skipped",
                config_type, name, expected,
            )
            return None
        base = self.manager_path if config_type == "manager" else self.ari_path
        return os.path.join(base, name), name

    async def _publish_ack(self, domain, version, status, error="", skipped=False):
        ack = {"domain": domain, "version": version, "status": status}
        if error:
            ack["error"] = error
        if skipped:
            ack["skipped"] = True
        if self.publisher:
            try:
                await self.publisher(f"pbx.state.Config.{domain}", ack)
            except Exception as e:
                logger.debug("Ack publish failed: %s", e)
        if self.webhook:
            try:
                await self.webhook.publish(
                    domain, f"pbx.state.Config.{domain}", ack
                )
            except Exception as e:
                logger.debug("Webhook ack failed: %s", e)

    async def apply_config(self, message):
        body = json.loads(message.body.decode())
        domain = body.get("domain")
        version = int(body.get("version", 0) or 0)
        files = body.get("files", {})
        if not domain or not isinstance(files, (dict, list)):
            logger.warning("Config message missing domain/files")
            return

        # Stale version → ignore (ack skipped)
        if version and version <= self._last_applied(domain):
            logger.info(
                "Ignoring stale config %s v%s (applied v%s)",
                domain, version, self._last_applied(domain),
            )
            await self._publish_ack(domain, version, "skipped", skipped=True)
            return

        written = []
        try:
            os.makedirs(self.config_path, exist_ok=True)
            os.makedirs(self.manager_path, exist_ok=True)
            os.makedirs(self.ari_path, exist_ok=True)
            for item in self._parse_files(files):
                target = self._target_for(domain, item)
                if not target:
                    continue
                filepath, display = target
                tmp = filepath + ".tmp"
                with open(tmp, "w") as f:
                    f.write(item.get("content") or "")
                os.replace(tmp, filepath)
                written.append((display, item.get("config_type", "tenant")))
                logger.info("Wrote %s (version %s)", filepath, version)

            if body.get("reload", True) and written:
                reload_cmds = ["pjsip reload", "dialplan reload", "voicemail reload"]
                types_written = {t for _, t in written}
                if "manager" in types_written:
                    reload_cmds.append("manager reload")
                if "ari" in types_written:
                    reload_cmds.append("module reload res_ari.so")
                for cmd in reload_cmds:
                    try:
                        await self.ami.send_action("Command", Command=cmd, wait_response=False)
                    except Exception as e:
                        logger.error("Reload %s failed: %s", cmd, e)

            await self._save_state(domain, version)
            await self._publish_ack(domain, version, "applied")
        except Exception as e:
            logger.error("Config apply failed for %s: %s", domain, e)
            await self._publish_ack(domain, version, "error", error=str(e))


# ──────────────────────────────────────────────────────────────────
# Health Check Server
# ──────────────────────────────────────────────────────────────────


async def health_check_handler(reader, writer):
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n")
    writer.write(b'{"status": "ok"}\r\n')
    await writer.drain()
    writer.close()


async def start_health_server(port: int):
    server = await asyncio.start_server(health_check_handler, "0.0.0.0", port)
    logger.info("Health check server on port %d", port)
    return server


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────


async def amain(config_path: str):
    config = load_config(config_path)

    # Setup logging
    log_level = config.get("daemon", {}).get("log_level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg_ami = config["asterisk"]
    cfg_mq = config["messaging"]
    cfg_daemon = config.get("daemon", {})
    cfg_tenants = config.get("tenants", {})
    cfg_webhook = config.get("webhook", {})
    reconnect_interval = cfg_daemon.get("reconnect_interval", 5)
    health_port = cfg_daemon.get("health_port", 8080)
    tenants_config_path = cfg_tenants.get("config_path", "/etc/asterisk/tenants/")

    webhook = WebhookPublisher(
        url=cfg_webhook.get("url", ""),
        token=cfg_webhook.get("token", ""),
        tokens=cfg_webhook.get("tokens", {}) or {},
    )

    # Connect to AMI
    ami = AMIConnection(
        cfg_ami["host"], cfg_ami["port"], cfg_ami["user"], cfg_ami["secret"]
    )

    # Setup messaging (RabbitMQ or NATS)
    mq_type = cfg_mq.get("type", "rabbitmq")

    if mq_type == "rabbitmq" and aio_pika:
        # RabbitMQ publisher
        connection = await aio_pika.connect_robust(
            host=cfg_mq["host"],
            port=cfg_mq["port"],
            login=cfg_mq["user"],
            password=cfg_mq["secret"],
            virtualhost=cfg_mq.get("vhost", "/"),
        )
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            "pbx", aio_pika.ExchangeType.TOPIC, durable=True
        )

        async def publisher(routing_key: str, data: dict):
            message = aio_pika.Message(
                body=json.dumps(data).encode(),
                content_type="application/json",
            )
            await exchange.publish(message, routing_key=routing_key)

        # Command subscriber
        cmd_queue = await channel.declare_queue("pbx-ami-daemon-commands", durable=True)
        await cmd_queue.bind(exchange, routing_key="pbx.cmd.Action.#")

        cmd_server = CommandServer(ami)

        async def on_command(message: aio_pika.IncomingMessage):
            async with message.process():
                body = json.loads(message.body.decode())
                await cmd_server.handle_command(message.routing_key, body)

        await cmd_queue.consume(on_command)

        # Config subscriber (Odoo-ägd config-generering → filer + reload)
        cfg_queue = await channel.declare_queue("pbx-ami-daemon-config", durable=True)
        await cfg_queue.bind(exchange, routing_key="pbx.config.#")

        config_consumer = ConfigConsumer(
            ami,
            tenants_config_path,
            publisher,
            webhook=webhook,
            manager_path=cfg_tenants.get("manager_path"),
            ari_path=cfg_tenants.get("ari_path"),
        )

        async def on_config(message: aio_pika.IncomingMessage):
            async with message.process():
                await config_consumer.apply_config(message)

        await cfg_queue.consume(on_config)

    elif mq_type == "rabbitmq" and not aio_pika:
        logger.error("aio_pika not installed. Install with: pip install aio-pika")
        sys.exit(1)

    else:
        # Fallback: log-only publisher (for testing without RabbitMQ)
        async def publisher(routing_key: str, data: dict):
            logger.debug("[%s] %s", routing_key, json.dumps(data)[:200])

        logger.warning("No messaging backend configured — events are logged only")

    # State cache
    state_cache = StateCache(publisher)

    # Health check
    health_server = await start_health_server(health_port)

    # ── ARI (nivå 2 — smart receptionist) ──
    # Startar ARI-klienten parallellt med AMI (om aktiverad i config).
    ari_task = None
    cfg_ari = config.get("ari", {})
    if cfg_ari.get("enabled", False):
        try:
            from .ari import ARIClient, Receptionist

            api_key = cfg_ari.get("api_key", "")
            if not api_key:
                ari_user = cfg_ari.get("user", "receptionist")
                ari_secret = cfg_ari.get("secret", "")
                api_key = f"{ari_user}:{ari_secret}"
            client = ARIClient(
                base_url=cfg_ari.get("base_url", "http://localhost:8088"),
                ws_url=cfg_ari.get("ws_url", "ws://localhost:8089"),
                app=cfg_ari.get("app", "receptionist"),
                api_key=api_key,
            )
            receptionist = Receptionist(
                client=client,
                odoo_url=cfg_ari.get("odoo_url", ""),
                webhook_token=cfg_ari.get("webhook_token", ""),
                coworker_id=int(cfg_ari.get("coworker_id", 0) or 0),
            )
            client.on_stasis_start = receptionist.on_stasis_start
            client.on_dtmf = receptionist.on_dtmf
            client.on_stasis_end = receptionist.on_stasis_end
            ari_task = asyncio.create_task(client.run())
            logger.info("ARI enabled — Stasis app=%s", cfg_ari.get("app"))
        except Exception as e:
            logger.error("ARI init failed: %s", e)

    # Main loop: connect AMI, run event consumer, reconnect on failure
    while True:
        try:
            await ami.connect()
            consumer = EventConsumer(
                ami, publisher, state_cache, webhook,
                known_domains=_load_known_domains(tenants_config_path),
            )
            logger.info("Event consumer started (webhook=%s)", webhook.url or "disabled")
            await consumer.run()
        except (ConnectionError, OSError) as e:
            logger.error("AMI connection error: %s. Reconnecting in %ds...", e, reconnect_interval)
            await ami.disconnect()
            await asyncio.sleep(reconnect_interval)
        except asyncio.CancelledError:
            break

    if ari_task:
        ari_task.cancel()

    health_server.close()


def main():
    parser = argparse.ArgumentParser(description="PBX AMI Daemon")
    parser.add_argument("--config", "-c", default="/etc/pbx-ami-daemon/config.yaml")
    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main_task = loop.create_task(amain(args.config))

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        main_task.cancel()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
