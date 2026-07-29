# pbx/tenant.sls — Generate and apply tenant config, reload Asterisk

{% set tenant = pillar.get('pbx', {}).get('tenant', {}) %}
{% set domain = tenant.get('domain', '') %}

pbx_tenant_{{ domain }}_pjsip:
  file.managed:
    - name: /etc/asterisk/tenants/{{ domain }}-pjsip.conf
    - source: salt://pbx/files/tenant_pjsip.conf.j2
    - template: jinja
    - context:
        tenant: {{ tenant|tojson }}
    - require:
      - sls: pbx.asterisk

pbx_tenant_{{ domain }}_extensions:
  file.managed:
    - name: /etc/asterisk/tenants/{{ domain }}-extensions.conf
    - source: salt://pbx/files/tenant_extensions.conf.j2
    - template: jinja
    - context:
        tenant: {{ tenant|tojson }}
    - require:
      - sls: pbx.asterisk

pbx_reload_asterisk:
  cmd.run:
    - name: |
        asterisk -rx 'pjsip reload'
        asterisk -rx 'dialplan reload'
        asterisk -rx 'voicemail reload'
    - onchanges:
      - file: pbx_tenant_{{ domain }}_pjsip
      - file: pbx_tenant_{{ domain }}_extensions
