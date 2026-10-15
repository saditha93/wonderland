"""Disposable Docker check of the cloud database's TLS and key permissions."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.aws_workloads import ROOT,tls_material


def run(args,**kwargs):
    return subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)


def main():
    name='wonderland-tls-check-'+secrets.token_hex(4)
    with tempfile.TemporaryDirectory(prefix='tls-check-',dir=ROOT/'secrets') as tmp:
        directory=Path(tmp); tls=tls_material(['postgres'])
        files={**tls['services']['postgres'],'ca.crt':tls['ca'],
               'pg_hba.conf':'local all all trust\nhostssl all all 0.0.0.0/0 scram-sha-256\nhostssl all all ::/0 scram-sha-256\n'}
        for filename,content in files.items():
            path=directory/filename; path.write_text(content); path.chmod(0o600)
        envfile=directory/'postgres.env'
        envfile.write_text('POSTGRES_USER=wonderland_owner\nPOSTGRES_DB=wonderland\nPOSTGRES_PASSWORD='+secrets.token_urlsafe(36)+'\n'); envfile.chmod(0o600)
        script='mkdir -p /run/tls; cp /input/tls.crt /input/tls.key /input/ca.crt /input/pg_hba.conf /run/tls/; chown 0:70 /run/tls/*; chmod 440 /run/tls/*; exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/run/tls/tls.crt -c ssl_key_file=/run/tls/tls.key -c hba_file=/run/tls/pg_hba.conf'
        try:
            created=run(['docker','run','-d','--name',name,'--env-file',str(envfile),
                         '--mount','type=bind,source='+str(directory)+',target=/input,readonly',
                         '--entrypoint','/bin/sh','postgres:17.11-alpine','-ec',script])
            if created.returncode: raise ValueError('Could not start disposable PostgreSQL TLS check')
            for _ in range(90):
                if run(['docker','exec',name,'pg_isready','-U','wonderland_owner','-d','wonderland']).returncode==0: break
                time.sleep(1)
            else: raise ValueError('PostgreSQL did not become ready with root-owned group-readable key')
            base=['docker','exec',name,'/bin/sh','-ec']
            query='PGPASSWORD="$POSTGRES_PASSWORD" psql "host=localhost user=wonderland_owner dbname=wonderland sslmode=verify-full sslrootcert=/run/tls/ca.crt" -Atc "SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()"'
            result=run([*base,query])
            if result.returncode or result.stdout.strip()!='t': raise ValueError('Verified database TLS query failed')
            plain=query.replace('sslmode=verify-full','sslmode=disable')
            if run([*base,plain]).returncode==0: raise ValueError('Database accepted plaintext TCP')
            wrong=query.replace('sslrootcert=/run/tls/ca.crt','sslrootcert=/run/tls/tls.crt')
            if run([*base,wrong]).returncode==0: raise ValueError('Database accepted an untrusted root certificate')
            print('PASS: real PostgreSQL accepts verified TLS; denies plaintext and an untrusted CA; root-owned 0440/group-70 key works. No ports published; disposable data removed.')
        finally: run(['docker','rm','-f',name])

if __name__=='__main__':
    try: main()
    except ValueError as exc: raise SystemExit(str(exc)) from None
