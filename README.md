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

## License

AGPL-3.0
