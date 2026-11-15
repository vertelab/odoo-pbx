# odoo-pbx — gren 19.0

> **Denna gren är avsiktligt tom.** Modulerna är INTE portade till Odoo 19.
> Grenen finns så att dev-miljöer (`hansolo19`) kan klona den utan att falla,
> men den påstår ingenting om att koden är portad.

## Baseline

| | |
|---|---|
| Källa | `20.0` |
| Moduler | **14** |
| Grenar i repot | `18.0`, `20.0` |

## Moduler

- `pbx_46elks`
- `pbx_admin`
- `pbx_ai`
- `pbx_base`
- `pbx_conference`
- `pbx_crm`
- `pbx_helpdesk`
- `pbx_hr`
- `pbx_ivr`
- `pbx_provisioning`
- `pbx_queue`
- `pbx_recording`
- `pbx_tenant`
- `pbx_time_condition`

## Blockerare

**2 externa beroenden saknas** i Odoo 19-kärnan och OCA 19.0:

| Beroende | Behövs av |
|---|---|
| `helpdesk` | `pbx_helpdesk` |
| `saltstack` | `pbx_admin` |

### Prioritering

Ett beroende som blockerar många moduler ger mest nytta att lösa först:

- `helpdesk` — frisläpper **1** modul(er)
- `saltstack` — frisläpper **1** modul(er)

## Nästa steg

Portering sker på `*-pfile`-maskin med versionsagnostisk kod
(`.p.py` / `.p.xml`). Se `/skill:odoo-pfiles`.
