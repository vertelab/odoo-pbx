# pbx/asterisk.sls — Install and configure Asterisk PJSIP

asterisk_package:
  pkg.installed:
    - name: asterisk
    - pkgs:
      - asterisk
      - asterisk-pjsip

asterisk_config_dir:
  file.directory:
    - name: /etc/asterisk/tenants
    - user: asterisk
    - group: asterisk
    - mode: '0755'
    - require:
      - pkg: asterisk_package

asterisk_voicemail_dir:
  file.directory:
    - name: /var/spool/asterisk/voicemail
    - user: asterisk
    - group: asterisk
    - mode: '0750'

asterisk_service:
  service.running:
    - name: asterisk
    - enable: true
    - require:
      - pkg: asterisk_package

# Firewall (optional — for LXD, handled by host)
asterisk_ports_udp:
  iptables.append:
    - table: filter
    - chain: INPUT
    - rule: '-p udp --dport 5060 -j ACCEPT'
    - require:
      - service: asterisk_service

asterisk_wss_port:
  iptables.append:
    - table: filter
    - chain: INPUT
    - rule: '-p tcp --dport 8089 -j ACCEPT'
    - require:
      - service: asterisk_service
