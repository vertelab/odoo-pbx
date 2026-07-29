# pbx/init.sls — PBX infrastructure top-level state

include:
  - pbx.asterisk
  - pbx.rabbitmq
  - pbx.daemon
