# odoo-pbx

Asterisk PBX management in a multi-tenant environment, integrated with Odoo.

## Architecture

```
odoo-pbx/
├── pbx_base/           Core: models, plugin interface, config generator
├── pbx_admin/          MSP panel: tenant CRUD, billing API, Zabbix
├── pbx_tenant/         Customer Odoo: inherits OCA voip_oca, FOP2 panel, voicemail
├── pbx_queue/          Plugin: call queues
├── pbx_ivr/            Plugin: IVR menu trees
├── pbx_conference/     Plugin: conference rooms
├── pbx_recording/      Plugin: call recording → S3
├── pbx_crm/            Plugin: CRM integration
├── pbx_helpdesk/       Plugin: helpdesk integration
├── pbx_subscription/   Plugin: billing via Odoo Subscription
├── pbx_ami_daemon/     Python daemon: AMI ↔ RabbitMQ/NATS bridge
├── salt/               SaltStack states for deployment
└── docker/             Development environment
```

## Quick Start

```bash
# Start development environment
docker compose up -d

# Odoo: http://localhost:8069
# RabbitMQ admin: http://localhost:15672 (pbx/pbx)
```

## Requirements

- Odoo 18+
- OCA `connector-telephony/voip_oca`
- Asterisk 20+ with PJSIP
- RabbitMQ or NATS

## Documentation

See `~/plan/odoo-pbx/openspec/` for full design docs and specs.

## Config deploy (pbx-freepbx-core)

Odoo generates the Asterisk configuration and publishes it via RabbitMQ
(`pbx.config.<domain>`); the daemon writes the files and confirms via
`pbx.state.Config.<domain>` (MQ) and a POST to `/pbx/webhook`.

### Config types (the message's `files` list)

| `config_type` | Target directory | Filename |
|---|---|---|
| `tenant` | `tenants/` | `<domain>-<filename>` |
| `manager` | `manager.d/` | `<domain>.conf` |
| `ari` | `ari.d/` | `<domain>.conf` |

The older format (`files` as a dict `{filename: content}`) is accepted as
`tenant` files.

### Version handling

- Odoo increments `pbx.config.version.<domain>` (ICP) on every publish.
- The daemon stores the applied version in `tenants/.state.json`; messages
  with `version <=` the applied version are ignored (ack `skipped`).
- Ack-status: `applied` | `error` | `skipped`.

### Sync state in Odoo (systray/Sync)

- **Sent** (`sent`): published, waiting for confirmation — `config_dirty`
  remains set.
- **Applied** (`applied`): the daemon confirmed the current version via
  webhook → `config_dirty` is cleared.
- **Error** (`error`): the daemon reported an error (the message is stored on
  `res.company.pbx_config_sync_error`).

### Softphone WebSocket (ws_server)

`voip.pbx.ws_server` is derived automatically from `res.company.pbx_server_host`
+ `pbx_sip_ws_port` (default 8089) with the scheme from the browser sub-extension's
transport, e.g. `wss://<host>:8089/ws`. Explicit override:
`res.company.pbx_ws_server` (used verbatim). Self-healing — also written
to an existing voip.pbx on sync.

## Voicemail audio (delivery integrity)

Asterisk 20.6 emits `MessageWaiting` (MWI) not only for a new message but also
on playback, deletion and `new` ⇄ `old` transitions — it is a *state* event.
The daemon therefore tracks, per mailbox, which audio it has already delivered.

### Delivery rule

- Audio (`_audio_base64`) is sent **once per new message, per mailbox**.
- The decision is based on the **content hash** of the audio, not the `msgN`
  filename: Asterisk's own `sha1=` from `msgN.txt` when present, otherwise md5
  of the decoded wav bytes. A file rewritten under a reused number therefore
  still counts as new.
- Repeated MWI events are still published (MQ topic **and** webhook) so state
  consumers see playback/deletion — only the audio is withheld.
- `CallerIDNum` / `Duration` are taken **unconditionally** from the `msgN.txt`
  of the delivered file (event values are fallback only), so audio and caller
  cannot be paired wrongly.

### Marker lifetime

The `MailboxMarker` lives in a cache created **once per daemon process**, next
to `StateCache` — not inside `EventConsumer`, which is re-instantiated on every
AMI reconnect. A shared marker means a dropped connection does not re-deliver
everything as duplicates.

| Event | Behaviour |
|---|---|
| New message (new hash) | `outcome=sent`, audio attached |
| Repeated MWI (same hash) | `outcome=dedup`, no audio, event still published |
| First MWI after daemon restart | `outcome=seed`, **no audio**, marker seeded from newest spool file |
| AMI reconnect | marker retained → no duplicates |

**Restart semantics (fail-safe):** the marker is in memory, so after a restart
it is unknown whether the newest file is new or already delivered. The daemon
then seeds the marker *without* sending audio — silent rather than wrong. The
message stays in the spool and a later MWI delivers it. At most one delivery is
lost per mailbox per restart; no duplicate is ever produced.

### Log format

Every decision is logged with mailbox, spool filename and hash — the line that
was missing when the symptom first appeared:

```
voicemail sent    mailbox=02@vertel.se msg_file=msg0002.wav hash=<h> outcome=sent
voicemail dedup   mailbox=02@vertel.se msg_file=msg0002.wav hash=<h> outcome=dedup
voicemail seed-after-restart mailbox=02@vertel.se msg_file=msg0002.wav hash=<h> outcome=seed (audio omitted)
```

The Odoo side logs the matching hash of what it stored, so a mismatch
localises the fault without touching the database:

```
voicemail stored extension=7001 hash=<h> attachment_id=42 bytes=12345
```

| daemon log | Odoo log | Conclusion |
|---|---|---|
| different hash per message | different hash | healthy |
| different hash | **same** hash | fault on the Odoo side |
| **same** hash | same hash | fault in the daemon |

### Known limitation — tight arrival

When two voicemails arrive faster than the events are processed, the
newest-file heuristic reads the newest file for both events, so the older one
is not delivered separately. Solving it needs a diff over the whole INBOX per
event (a larger rewrite of `_read_voicemail_audio`). It is documented in the
daemon next to the `max()` selection — do not assume per-message delivery
guarantees for that case. Tracked separately, not built.

## License

AGPL-3.0
