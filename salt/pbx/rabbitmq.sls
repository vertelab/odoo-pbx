# pbx/rabbitmq.sls — Install and configure RabbitMQ

rabbitmq_package:
  pkg.installed:
    - name: rabbitmq-server

rabbitmq_service:
  service.running:
    - name: rabbitmq-server
    - enable: true
    - require:
      - pkg: rabbitmq_package

rabbitmq_vhost:
  rabbitmq_vhost.present:
    - name: pbx
    - require:
      - service: rabbitmq_service

rabbitmq_user:
  rabbitmq_user.present:
    - name: pbx
    - password: {{ pillar.get('mq_password', 'pbx') }}
    - permissions:
      - vhost: pbx
        configure: '.*'
        read: '.*'
        write: '.*'
    - require:
      - rabbitmq_vhost: rabbitmq_vhost
