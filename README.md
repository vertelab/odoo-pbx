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

Odoo genererar Asterisk-konfig och publicerar den via RabbitMQ
(`pbx.config.<domän>`); daemonen skriver filerna och bekräftar via
`pbx.state.Config.<domän>` (MQ) och POST till `/pbx/webhook`.

### Config-typer (meddelandets `files`-lista)

| `config_type` | Målkatalog | Filnamn |
|---|---|---|
| `tenant` | `tenants/` | `<domän>-<filnamn>` |
| `manager` | `manager.d/` | `<domän>.conf` |
| `ari` | `ari.d/` | `<domän>.conf` |

Äldre format (`files` som dict `{filnamn: innehåll}`) accepteras som
`tenant`-filer.

### Versionshantering

- Odoo räknar upp `pbx.config.version.<domän>` (ICP) vid varje publish.
- Daemonen sparar applicerad version i `tenants/.state.json`; meddelanden
  med `version <=` applicerad ignoreras (ack `skipped`).
- Ack-status: `applied` | `error` | `skipped`.

### Sync-state i Odoo (systray/Sync)

- **Skickat** (`sent`): publicerat, väntar på bekräftelse — `config_dirty`
  kvarstår.
- **Applicerat** (`applied`): daemonen bekräftade aktuell version via
  webhook → `config_dirty` nollställs.
- **Fel** (`error`): daemonen rapporterade fel (meddelandet sparas på
  `res.company.pbx_config_sync_error`).

### Softphone WebSocket (ws_server)

`voip.pbx.ws_server` härleds automatiskt från `res.company.pbx_server_host`
+ `pbx_sip_ws_port` (default 8089) med schema från browser-sub-extensionens
transport, t.ex. `wss://<host>:8089/ws`. Explicit override:
`res.company.pbx_ws_server` (används exakt). Självläkande — skrivs även
på befintlig voip.pbx vid synk.

## License

AGPL-3.0
