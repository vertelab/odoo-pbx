# pbx/onboarding.sls — Onboard a new customer tenant
# Usage: salt 'lxd-pbx' state.apply pbx.onboarding pillar='{"pbx": {"tenant": {...}}}'

include:
  - pbx.tenant

{% set tenant = pillar.get('pbx', {}).get('tenant', {}) %}
{% set domain = tenant.get('domain', '') %}

pbx_tenant_{{ domain }}_include:
  file.append:
    - name: /etc/asterisk/pjsip.conf
    - text: '#include /etc/asterisk/tenants/{{ domain }}-pjsip.conf'

pbx_extensions_{{ domain }}_include:
  file.append:
    - name: /etc/asterisk/extensions.conf
    - text: '#include /etc/asterisk/tenants/{{ domain }}-extensions.conf'

pbx_notify_onboard_complete:
  cmd.run:
    - name: echo "Tenant {{ domain }} onboarding complete at $(date)"
    - onchanges:
      - file: pbx_tenant_{{ domain }}_pjsip
