#!/usr/bin/env bash
set -euo pipefail
umask 077
# Public bootstrap only: no database, AWS or payment credentials in user data.
MINIKUBE_VERSION=v1.39.0
KUBERNETES_VERSION=v1.36.5
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
apt-get -o Acquire::Retries=5 install -y ca-certificates curl nginx python3-venv python3-boto3 jq docker.io conntrack
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
# Minikube runs a Docker node as ubuntu; the EC2 host needs no nested VM.
systemctl enable --now docker
usermod -aG docker ubuntu
install -d -m 755 /opt/wonderland/downloads
cd /opt/wonderland/downloads
curl -fL --retry 5 -o minikube "https://github.com/kubernetes/minikube/releases/download/${MINIKUBE_VERSION}/minikube-linux-amd64"
curl -fL --retry 5 -o minikube.sha256 "https://github.com/kubernetes/minikube/releases/download/${MINIKUBE_VERSION}/minikube-linux-amd64.sha256"
echo "$(cat minikube.sha256)  minikube" | sha256sum -c -
install -m 755 minikube /usr/local/bin/minikube
curl -fL --retry 5 -o kubectl-real "https://dl.k8s.io/release/${KUBERNETES_VERSION}/bin/linux/amd64/kubectl"
curl -fL --retry 5 -o kubectl.sha256 "https://dl.k8s.io/release/${KUBERNETES_VERSION}/bin/linux/amd64/kubectl.sha256"
echo "$(cat kubectl.sha256)  kubectl-real" | sha256sum -c -
install -m 755 kubectl-real /usr/local/bin/kubectl-real
# Root SSM commands and ubuntu SSH sessions use the same private cluster.
cat > /usr/local/bin/kubectl <<'KUBECTL'
#!/bin/sh
exec /usr/local/bin/kubectl-real --kubeconfig=/home/ubuntu/.kube/config "$@"
KUBECTL
chmod 755 /usr/local/bin/kubectl
cat > /etc/systemd/system/wonderland-minikube.service <<UNIT
[Unit]
Description=Wonderland Minikube cluster
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target
[Service]
Type=oneshot
RemainAfterExit=yes
User=ubuntu
Group=ubuntu
SupplementaryGroups=docker
Environment=HOME=/home/ubuntu
Environment=PATH=/usr/local/bin:/usr/bin:/bin
TimeoutStartSec=1200
TimeoutStopSec=180
ExecStart=/usr/local/bin/minikube start -p wonderland --driver=docker --container-runtime=containerd --cpus=2 --memory=5120 --kubernetes-version=${KUBERNETES_VERSION} --addons=ingress,metrics-server
ExecStop=/usr/local/bin/minikube stop -p wonderland
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
install -d -m 755 /var/www/acme /var/www/acme/.well-known /var/www/acme/.well-known/acme-challenge
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
systemctl enable --now wonderland-minikube wonderland-autostop.timer nginx
nginx -t
systemctl reload nginx
touch /opt/wonderland/bootstrap-ready
