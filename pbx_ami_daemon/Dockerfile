FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/odoo-pbx

COPY pbx_ami_daemon/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pbx_ami_daemon/ .

RUN useradd --system --no-create-home pbx
USER pbx

EXPOSE 8080

ENTRYPOINT ["python", "-m", "pbx_ami_daemon.daemon"]
CMD ["--config", "/etc/pbx-ami-daemon/config.yaml"]
