# pbx/daemon.sls — Install pbx_ami_daemon

pbx_ami_daemon_install:
  git.latest:
    - name: https://github.com/vertelab/odoo-pbx
    - target: /opt/odoo-pbx
    - rev: main

pbx_ami_daemon_venv:
  pip.virtualenv:
    - path: /opt/odoo-pbx/venv
    - python: python3.12
    - requirements: /opt/odoo-pbx/pbx_ami_daemon/requirements.txt
    - require:
      - git: pbx_ami_daemon_install

pbx_ami_daemon_config:
  file.managed:
    - name: /etc/pbx-ami-daemon/config.yaml
    - source: salt://pbx/files/config.yaml.j2
    - template: jinja
    - user: pbx
    - group: pbx
    - mode: '0600'

pbx_ami_daemon_user:
  user.present:
    - name: pbx
    - system: true
    - shell: /usr/sbin/nologin

pbx_ami_daemon_unit:
  file.managed:
    - name: /etc/systemd/system/pbx-ami-daemon.service
    - source: /opt/odoo-pbx/pbx_ami_daemon/pbx-ami-daemon.service
    - user: root
    - group: root
    - mode: '0644'
    - require:
      - git: pbx_ami_daemon_install

pbx_ami_daemon_service:
  service.running:
    - name: pbx-ami-daemon
    - enable: true
    - watch:
      - file: pbx_ami_daemon_config
      - file: pbx_ami_daemon_unit
