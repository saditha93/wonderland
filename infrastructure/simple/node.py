"""Run as root via SSM. Fetch runtime secrets in memory, never in SSM parameters."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import gzip
import hashlib
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer

os.umask(0o077)
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import boto3
import yaml
from scripts.simple_workloads import render
ROOT=Path('/opt/wonderland')


def command(args,**kwargs):
    result=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
    if result.returncode:
        diagnostic=ROOT/'last-error.log'
        diagnostic.write_text(result.stdout+'\n'+result.stderr)
        diagnostic.chmod(0o600)
        raise ValueError('Private diagnostic saved on the host')
    return result


def kube(*args,input=None):
    return command(['/usr/local/bin/kubectl','-n','wonderland',*args],input=input)


def apply(docs):
    if docs: command(['/usr/local/bin/kubectl','apply','--server-side','--field-manager=wonderland-demo','-f','-'],input=yaml.safe_dump_all(docs))


def refresh(s,d):
    auth=s.client('ecr').get_authorization_token()['authorizationData'][0]
    username,password=base64.b64decode(auth['authorizationToken']).decode().split(':',1)
    registry=auth['proxyEndpoint'].removeprefix('https://')
    data=json.dumps({'auths':{registry:{'username':username,'password':password,'auth':auth['authorizationToken']}}})
    apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':'ecr-pull','namespace':'wonderland'},
            'type':'kubernetes.io/dockerconfigjson','stringData':{'.dockerconfigjson':data}}])


def configure_proxy(d,runtime):
    ca=ROOT/'internal-ca.pem'; ca.write_text(runtime['tls']['ca']); ca.chmod(0o600)
    token=runtime['origin_token']
    if not all(ch.isalnum() or ch in '-_' for ch in token): raise ValueError('Unexpected origin token')
    for public in ['/var/www/acme','/var/www/acme/.well-known','/var/www/acme/.well-known/acme-challenge']:
        path=Path(public);path.mkdir(parents=True,exist_ok=True);path.chmod(0o755)
    cert='/etc/letsencrypt/live/wonderland-ip'
    if not Path(cert+'/fullchain.pem').exists():
        command([str(ROOT/'certbot/bin/certbot'),'certonly','--non-interactive','--agree-tos',
                 '--register-unsafely-without-email','--preferred-profile','shortlived',
                 '--webroot','--webroot-path','/var/www/acme','--ip-address',d['server_ip'],
                 '--cert-name','wonderland-ip'])
    nginx=f'''server {{
    listen 80 default_server;
    server_name _;
    location ^~ /.well-known/acme-challenge/ {{ root /var/www/acme; }}
    location / {{ return 404; }}
}}
server {{
    listen 443 ssl default_server;
    server_name _;
    ssl_certificate {cert}/fullchain.pem;
    ssl_certificate_key {cert}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    location /api/ {{
        if ($http_x_wonderland_gateway != "{token}") {{ return 403; }}
        proxy_pass https://127.0.0.1:30443;
        proxy_ssl_verify on;
        proxy_ssl_trusted_certificate {ca};
        proxy_ssl_server_name on;
        proxy_ssl_name frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Wonderland-Gateway "";
    }}
    location / {{ return 404; }}
}}
'''
    Path('/etc/nginx/sites-available/wonderland').write_text(nginx)
    command(['nginx','-t']); command(['systemctl','reload','nginx'])
    renewal='''[Unit]
Description=Renew Wonderland short-lived IP TLS certificate
[Service]
Type=oneshot
ExecStart=/opt/wonderland/certbot/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx"
'''
    Path('/etc/systemd/system/wonderland-cert-renew.service').write_text(renewal)
    Path('/etc/systemd/system/wonderland-cert-renew.timer').write_text('''[Unit]
Description=Check demo TLS renewal twice daily
[Timer]
OnBootSec=5min
OnUnitActiveSec=12h
Persistent=true
[Install]
WantedBy=timers.target
''')


def install_units(config):
    source=Path(__file__).resolve()
    for name,execstart,kind in [
        ('metabase-forward','/usr/local/bin/kubectl -n wonderland port-forward --address=127.0.0.1 service/metabase 3000:3000','simple'),
        ('ecr-refresh',f'/opt/wonderland/runtime/bin/python {source} refresh --config {config}','oneshot')]:
        unit=f'[Unit]\nDescription=Wonderland {name}\nAfter=k3s.service network-online.target\n[Service]\nType={kind}\nExecStart={execstart}\n'
        if kind=='simple': unit+='Restart=always\nRestartSec=5\n'
        unit+='[Install]\nWantedBy=multi-user.target\n'
        Path('/etc/systemd/system/wonderland-'+name+'.service').write_text(unit)
    Path('/etc/systemd/system/wonderland-ecr-refresh.timer').write_text('''[Unit]
Description=Refresh node ECR pull token
[Timer]
OnBootSec=1min
OnUnitActiveSec=6h
[Install]
WantedBy=timers.target
''')
    command(['systemctl','daemon-reload'])
    command(['systemctl','enable','--now','wonderland-metabase-forward','wonderland-ecr-refresh.timer','wonderland-cert-renew.timer'])


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['install','refresh','status','backup','serve-backup'])
    parser.add_argument('--config',type=Path,required=True); args=parser.parse_args()
    config=json.loads(args.config.read_text()); t=config['target']; d=config['deployment']
    s=boto3.Session(region_name=t['region'])
    if args.action=='backup':
        if not kube('get','statefulset','postgres','--ignore-not-found','-o','name').stdout.strip():
            print(json.dumps({'database_absent':True}));return
        sql=kube('exec','postgres-0','--','pg_dumpall','-U','wonderland_owner','--clean','--if-exists').stdout
        if 'PostgreSQL database cluster dump' not in sql: raise ValueError('Unexpected backup output')
        data=gzip.compress(sql.encode(),mtime=0)
        folder=ROOT/'backups'; folder.mkdir(exist_ok=True,mode=0o700)
        (folder/'database.sql.gz').write_bytes(data)
        meta={'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),'path':'/'+secrets.token_urlsafe(32)}
        (folder/'transfer.json').write_text(json.dumps(meta))
        command(['systemd-run','--unit=wonderland-backup-transfer','--property=RuntimeMaxSec=300',
                 '/opt/wonderland/runtime/bin/python',str(Path(__file__).resolve()),'serve-backup','--config',str(args.config)])
        print(json.dumps(meta)); return
    if args.action=='serve-backup':
        folder=ROOT/'backups'; meta=json.loads((folder/'transfer.json').read_text())
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path!=meta['path']:
                    self.send_error(404); return
                data=(folder/'database.sql.gz').read_bytes()
                self.send_response(200); self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(data)
            def log_message(self,*args): pass
        HTTPServer(('127.0.0.1',8765),Handler).serve_forever()
        return
    if args.action=='status':
        print(kube('get','pods,deploy,statefulset,hpa,svc','-o','wide').stdout)
        return
    if args.action=='refresh': refresh(s,d); return
    for _ in range(180):
        if (ROOT/'bootstrap-ready').exists(): break
        time.sleep(5)
    else: raise ValueError('Bootstrap did not finish')
    runtime=json.loads(s.client('secretsmanager').get_secret_value(SecretId=d['runtime_secret_arn'])['SecretString'])
    docs=render(t,d,runtime)
    apply([x for x in docs if x['kind']=='Namespace'])
    refresh(s,d)
    apply([x for x in docs if x['kind'] in {'Secret','ConfigMap','ServiceAccount','Service','StatefulSet'}])
    kube('rollout','status','statefulset/postgres','--timeout=300s')
    jobs=[x for x in docs if x['kind']=='Job']
    for job in jobs:
        name=job['metadata']['name']
        old=kube('get','job',name,'--ignore-not-found','-o','json').stdout
        if not old: apply([job])
        kube('wait','--for=condition=complete','job/'+name,'--timeout=240s')
    kube('delete','secret','migration-config','--ignore-not-found')
    apply([x for x in docs if x['kind'] in {'Deployment','HorizontalPodAutoscaler','DaemonSet'}])
    for x in docs:
        if x['kind']=='Deployment': kube('rollout','status','deployment/'+x['metadata']['name'],'--timeout=600s')
    command(['/usr/local/bin/kubectl','-n','kube-system','rollout','status','daemonset/wonderland-logs','--timeout=180s'])
    configure_proxy(d,runtime)
    install_units(args.config)
    print('Workloads ready; TLS proxy and private Metabase forwarding configured.')

if __name__=='__main__':
    try: main()
    except Exception:
        raise SystemExit('Node operation failed; private command output suppressed. Inspect host logs via SSM without sharing secret contents.') from None
