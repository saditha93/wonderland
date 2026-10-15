#!/usr/bin/env bash
set -euo pipefail
umask 077
# Public bootstrap only: no database, AWS or payment credentials in user data.
K3S_VERSION=__K3S_VERSION__
install -d -m 700 /opt/wonderland
# Wait for Terraform to associate the fixed public address before apt/downloads.
TOKEN=$(curl -fsS -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 21600' http://169.254.169.254/latest/api/token)
for attempt in $(seq 1 120); do
  if curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 >/dev/null; then break; fi
  sleep 5
done
unset TOKEN
export DEBIAN_FRONTEND=noninteractive
apt-get -o Acquire::Retries=5 update
apt-get -o Acquire::Retries=5 install -y ca-certificates curl nginx python3-venv python3-boto3 jq
systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent.service || {
  snap install amazon-ssm-agent --classic
  snap start amazon-ssm-agent
}
modprobe overlay
modprobe br_netfilter
cat > /etc/sysctl.d/90-wonderland.conf <<'SYSCTL'
net.ipv4.ip_forward=1
net.bridge.bridge-nf-call-iptables=1
net.bridge.bridge-nf-call-ip6tables=1
SYSCTL
sysctl --system >/dev/null
mkdir -p /opt/wonderland/k3s-download
cd /opt/wonderland/k3s-download
curl -fL --retry 5 -o k3s-arm64 "https://github.com/k3s-io/k3s/releases/download/${K3S_VERSION}/k3s-arm64"
curl -fL --retry 5 -o checksums.txt "https://github.com/k3s-io/k3s/releases/download/${K3S_VERSION}/sha256sum-arm64.txt"
grep ' k3s-arm64$' checksums.txt | sha256sum -c -
install -m 755 k3s-arm64 /usr/local/bin/k3s
ln -sf /usr/local/bin/k3s /usr/local/bin/kubectl
cat > /etc/systemd/system/k3s.service <<'UNIT'
[Unit]
Description=Wonderland single-node Kubernetes
After=network-online.target
Wants=network-online.target
[Service]
Type=notify
Delegate=yes
KillMode=process
LimitNOFILE=1048576
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
TimeoutStartSec=0
Restart=always
RestartSec=5
ExecStart=/usr/local/bin/k3s server --node-name=wonderland-demo --disable=traefik --disable=servicelb --secrets-encryption --write-kubeconfig-mode=600 --kube-proxy-arg=nodeport-addresses=127.0.0.1/32
[Install]
WantedBy=multi-user.target
UNIT
# Stop compute automatically six hours after every boot; keep disk and address.
cat > /etc/systemd/system/wonderland-autostop.service <<'UNIT'
[Unit]
Description=Stop the demo server after its bounded runtime
[Service]
Type=oneshot
ExecStart=/usr/sbin/shutdown -h now
UNIT
cat > /etc/systemd/system/wonderland-autostop.timer <<'UNIT'
[Unit]
Description=Six-hour Wonderland demo runtime
[Timer]
OnBootSec=6h
Unit=wonderland-autostop.service
[Install]
WantedBy=timers.target
UNIT
mkdir -p /var/www/acme/.well-known/acme-challenge
rm -f /etc/nginx/sites-enabled/default
cat > /etc/nginx/sites-available/wonderland <<'NGINX'
server {
    listen 80 default_server;
    server_name _;
    location ^~ /.well-known/acme-challenge/ { root /var/www/acme; }
    location = /health { default_type application/json; return 200 '{"stage":"bootstrap"}'; }
    location / { return 404; }
}
NGINX
ln -sf /etc/nginx/sites-available/wonderland /etc/nginx/sites-enabled/wonderland
python3 -m venv /opt/wonderland/certbot
/opt/wonderland/certbot/bin/pip install --disable-pip-version-check certbot==5.4.0
systemctl daemon-reload
systemctl enable --now k3s wonderland-autostop.timer nginx
nginx -t
systemctl reload nginx
touch /opt/wonderland/bootstrap-ready
