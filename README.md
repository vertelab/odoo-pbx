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

## License

AGPL-3.0
