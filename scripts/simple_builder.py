"""Disposable on-node image builder. Registry credentials never enter command logs."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import boto3

config=json.loads(Path(sys.argv[1]).read_text());d=config['deployment'];t=config['target']
s=boto3.Session(region_name=t['region']);sm=s.client('secretsmanager')
secret=json.loads(sm.get_secret_value(SecretId=d['runtime_secret_arn'])['SecretString'])
auth=secret['build_registry_auth'];username,password=base64.b64decode(auth['authorizationToken']).decode().split(':',1)
registry=f"{t['account_id']}.dkr.ecr.{t['region']}.amazonaws.com"
assert auth['proxyEndpoint']=='https://'+registry
root=Path(__file__).resolve().parents[1]
private=Path('/opt/wonderland/build-docker');private.mkdir(mode=0o700,exist_ok=True)
import os
os.umask(0o077);env=dict(os.environ,DOCKER_CONFIG=str(private))
def run(args,**kwargs): return subprocess.run(args,cwd=root,env=env,check=True,**kwargs)
try:
    run(['docker','login','--username',username,'--password-stdin',registry],
        input=password.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    for name in config['missing']:
        image=d['repositories'][name]+':'+t['release']
        dockerfile='frontend/Dockerfile.kubernetes' if name=='frontend' else ('infrastructure/local/Dockerfile.migrate' if name=='migrate' else f'services/{name}/Dockerfile')
        run(['docker','build','--network=host','-f',dockerfile,'-t',image,
             'frontend' if name=='frontend' else '.'])
        run(['docker','push',image])
        print('Published project image:',name,flush=True)
finally:
    run(['docker','logout',registry],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (private/'config.json').unlink(missing_ok=True)
