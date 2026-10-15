"""Small AWS demo operator. Credentials/state stay in ignored private files."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import boto3
from botocore.exceptions import ClientError
from scripts.cloud import aws_environment, GuardError
from scripts.deployment_policy import policies

PRIVATE = ROOT / 'secrets/simple-cloud'
TFROOT = ROOT / 'infrastructure/terraform/simple'
TF = str(ROOT / 'tmp/tools/terraform')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, indent=2) + '\n')
    path.chmod(0o600)


def target():
    value = json.loads((PRIVATE / 'target.json').read_text())
    if value['region'] != 'us-east-1' or value['name'] != 'wonderland-demo' or not re.fullmatch(r'\d{12}', value['account_id']):
        raise GuardError('Unexpected demo target')
    if value['instance_type'] != 'm7i-flex.large' or value.get('architecture') != 'amd64':
        raise GuardError('Unreviewed instance size')
    if not re.fullmatch(r'[a-z0-9-]{1,40}', value['release']):
        raise GuardError('Invalid immutable release identifier')
    return value


def session(t):
    s = boto3.Session(region_name=t['region'], **aws_environment(t))
    identity = s.client('sts').get_caller_identity()
    if identity['Account'] != t['account_id'] or identity['Arn'] != f"arn:aws:iam::{t['account_id']}:user/wonderland":
        raise GuardError('Deploy using the reviewed non-root wonderland IAM user')
    return s


def free_plan(s):
    account = s.client('freetier').get_account_plan_state()
    if account.get('accountPlanType') != 'FREE' or account.get('accountPlanStatus') != 'ACTIVE':
        raise GuardError('Expected an active AWS Free plan; no automatic upgrade is permitted')
    return account


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)


def tf(*args, capture=False):
    env = {**os.environ, 'TF_IN_AUTOMATION':'true', 'AWS_EC2_METADATA_DISABLED':'true'}
    return run([TF, '-chdir='+str(TFROOT), *args], env=env,
               stdout=subprocess.PIPE if capture else None,
               stderr=subprocess.PIPE if capture else None)


def source_hash():
    digest = hashlib.sha256()
    for directory in ('infrastructure/simple','infrastructure/terraform/simple','scripts','frontend','services','wonderland_common'):
        for path in sorted((ROOT/directory).rglob('*')):
            if not path.is_file() or any(part in {'.terraform','__pycache__','node_modules','dist','dist-admin'} for part in path.parts):
                continue
            if path.suffix in {'.pyc','.tfstate'}: continue
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def plan(s,t):
    if (TFROOT/'cleanup_override.tf.json').exists():
        raise GuardError('Remove/review the interrupted cleanup override before a deployment plan')
    free_plan(s)
    ec2 = s.client('ec2')
    selected=ec2.describe_instance_types(InstanceTypes=[t['instance_type']])['InstanceTypes'][0]
    if not selected.get('FreeTierEligible') or selected['MemoryInfo']['SizeInMiB'] < 8192:
        raise GuardError('Selected size must be Free-plan eligible and have at least 8 GiB for this complete demo')
    image=ec2.describe_images(ImageIds=[t['ami_id']])['Images']
    if len(image)!=1 or image[0]['State']!='available' or image[0]['Architecture']!='x86_64' or image[0]['OwnerId']!='099720109477':
        raise GuardError('Expected an available official Ubuntu x86-64 image')
    offers = ec2.describe_instance_type_offerings(LocationType='availability-zone',Filters=[{'Name':'instance-type','Values':[t['instance_type']]}])['InstanceTypeOfferings']
    zones = {z['ZoneName'] for z in ec2.describe_availability_zones(Filters=[{'Name':'state','Values':['available']}])['AvailabilityZones']}
    possible = sorted(o['Location'] for o in offers if o['Location'] in zones)
    if not possible: raise GuardError('No available zone supports the selected instance')
    t.setdefault('availability_zone',possible[0])
    if t['availability_zone'] not in possible: raise GuardError('Pinned zone is unavailable')
    save(PRIVATE/'target.json', t)
    tokenfile = PRIVATE/'origin-token.json'
    if not tokenfile.exists():
        import secrets
        save(tokenfile, {'token':secrets.token_urlsafe(48)})
    bootstrap = (ROOT/'infrastructure/simple/bootstrap.sh').read_text().replace('__K3S_VERSION__',t['k3s_version'])
    variables = {k:t[k] for k in ('account_id','ami_id','availability_zone','instance_type')}
    variables.update(bootstrap_script=bootstrap, runtime_policy=json.dumps(policies(t['account_id'])['WonderlandRuntimeBoundary']),origin_token=json.loads(tokenfile.read_text())['token'])
    save(PRIVATE/'terraform.tfvars.json', variables)
    tf('init','-input=false','-reconfigure')
    tf('plan','-input=false','-no-color','-var-file='+str(PRIVATE/'terraform.tfvars.json'),'-out='+str(PRIVATE/'deployment.tfplan'))
    p = PRIVATE/'deployment.tfplan'; p.chmod(0o600)
    document = json.loads(tf('show','-json',str(p),capture=True).stdout)
    changes = [{'address':c['address'],'actions':c['change']['actions']} for c in document.get('resource_changes',[]) if c['change']['actions'] != ['no-op']]
    # A later deployment may not silently replace the server/database or delete resources.
    if any('delete' in c['actions'] for c in changes):
        raise GuardError('Plan includes deletion/replacement; backup and separate review required')
    review = {'plan_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source_sha256':source_hash(),'target':t,'changes':changes,'created_at':int(time.time())}
    save(PRIVATE/'review.json',review)
    print('\nSaved reviewed plan:',review['plan_sha256'])
    print('Observed compute quote: $0.09576/hour for eligible m7i-flex.large (8 GiB); storage, IPv4 and AWS services are additional. Credits/Free plan are not a zero-cost guarantee.')
    print('Compute automatically stops six hours after boot. Storage and IPv4 remain allocated.')
    print('Apply exactly this plan: ./cloud.sh deploy --approve '+review['plan_sha256'])


def deployment():
    return json.loads((PRIVATE/'deployment.json').read_text())


def deploy(s,t,approved):
    review=json.loads((PRIVATE/'review.json').read_text()); p=PRIVATE/'deployment.tfplan'
    if approved != review['plan_sha256'] or hashlib.sha256(p.read_bytes()).hexdigest() != approved:
        raise GuardError('Supply the exact saved plan digest shown by ./cloud.sh plan')
    if review['source_sha256'] != source_hash() or review['target'] != t or time.time()-review['created_at'] > 3600:
        raise GuardError('Source/target changed or plan is older than one hour; run plan again')
    free_plan(s)
    tf('apply','-input=false','-no-color',str(p))
    for f in PRIVATE.glob('*.tfstate*'): f.chmod(0o600)
    value=json.loads(tf('output','-json',capture=True).stdout)['deployment']['value']
    save(PRIVATE/'deployment.json',value)
    print('AWS resources created. Run ./cloud.sh release to install and verify the application.')


def status(s,t):
    d=deployment(); rows=s.client('ec2').describe_instances(InstanceIds=[d['instance_id']])['Reservations']
    instance=rows[0]['Instances'][0]
    print('Server:',instance['State']['Name'],'IP:',d['server_ip'])
    for name, portal in d['portals'].items(): print(name.capitalize()+':',portal['origin'])
    print('API:',d['api_url']); print('Metabase: ./cloud.sh monitoring (private tunnel)')


def power(s,t,action):
    free_plan(s); d=deployment(); ec2=s.client('ec2')
    instance=ec2.describe_instances(InstanceIds=[d['instance_id']])['Reservations'][0]['Instances'][0]
    tags={x['Key']:x['Value'] for x in instance.get('Tags',[])}
    if tags.get('Project')!='wonderland' or tags.get('Stack')!='wonderland-demo':
        raise GuardError('Instance ownership tags differ')
    getattr(ec2,action+'_instances')(InstanceIds=[d['instance_id']])
    print(action.capitalize()+' requested; database and address are preserved.')


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['plan','deploy','release','verify','status','start','stop','monitoring','backup','destroy','cleanup-check'])
    p.add_argument('--approve')
    args=p.parse_args(); t=target(); s=session(t)
    if args.action=='plan': plan(s,t)
    elif args.action=='deploy': deploy(s,t,args.approve)
    elif args.action=='status': status(s,t)
    elif args.action in {'start','stop'}: power(s,t,args.action)
    elif args.action in {'backup','destroy','cleanup-check'}:
        from scripts.simple_cleanup import backup,destroy,audit
        if args.action=='cleanup-check': audit(s,t)
        elif args.action=='backup': backup(s,t,deployment())
        else:
            value=json.loads(tf('output','-json',capture=True).stdout).get('deployment',{}).get('value')
            destroy(s,t,value,args.approve)
    else:
        from scripts.simple_release import release, verify, monitoring
        {'release':release,'verify':verify,'monitoring':monitoring}[args.action](s,t,deployment())

if __name__=='__main__':
    try: main()
    except ClientError as exc:
        raise SystemExit('AWS refused the operation: '+exc.response['Error']['Code']+'. No plan upgrade or broad permission fallback was attempted.') from None
    except (GuardError,FileNotFoundError,ValueError) as exc:
        raise SystemExit(str(exc)) from None
    except subprocess.CalledProcessError:
        raise SystemExit('Cloud command failed. AWS changes may be partial; inspect the private operation log and use cleanup-check before assuming resources are gone.') from None
