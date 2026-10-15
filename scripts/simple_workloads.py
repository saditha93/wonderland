"""Private single-node workloads; no local identity or public database/admin ports."""
import hashlib
import json
from scripts.aws_workloads import ROOT, render as cloud_render, secret, log_collector
from sqlalchemy.engine import make_url
import yaml


def render(target, deployment, runtime):
    core = dict(db_endpoint='postgres', queue_url=deployment['queue_url'],
                dead_queue_url=deployment['dead_queue_url'], analytics_role_arn='',
                alb_security_group_id='')
    persistent = dict(pool_id=deployment['pool_id'], client_id=deployment['client_id'],
                      frontend_origin=deployment['portals']['visitor']['origin'],
                      repositories=deployment['repositories'])
    docs = cloud_render({**target,'certificate_arn':''}, core, persistent,
                        runtime['values'],runtime['master'],runtime['tls'])
    docs = [d for d in docs if d['kind'] != 'Ingress']
    for d in docs:
        name = d['metadata']['name']
        if d['kind']=='ServiceAccount': d['metadata'].pop('annotations',None)
        if name=='rds-ca': d['data']['global-bundle.pem']=runtime['tls']['ca']
        if d['kind']=='Secret':
            for k,v in d['stringData'].items():
                if v.startswith('postgresql'):
                    d['stringData'][k]=make_url(v).update_query_dict({'sslrootcert':'/run/rds-ca/global-bundle.pem'}).render_as_string(hide_password=False)
        if d['kind']=='Service' and name=='frontend':
            d['spec']['type']='NodePort'
            d['spec']['ports'][0].update(nodePort=30443,targetPort='http')
        if d['kind'] not in {'Deployment','Job'}: continue
        pod=d['spec']['template']['spec']
        pod['imagePullSecrets']=[{'name':'ecr-pull'}]
        if name!='metabase':
            pod.setdefault('volumes',[]).append({'name':'rds-ca','configMap':{'name':'rds-ca'}})
            for c in pod['containers']:
                c.setdefault('volumeMounts',[]).append({'name':'rds-ca','mountPath':'/run/rds-ca','readOnly':True})
    postgres=list(yaml.safe_load_all((ROOT/'infrastructure/kubernetes/local/postgres.yaml').read_text()))
    for d in postgres: d['metadata']['namespace']='wonderland'
    pg=next(d for d in postgres if d['kind']=='StatefulSet')
    pod=pg['spec']['template']['spec']; c=pod['containers'][0]
    c['args']=['-c','ssl=on','-c','ssl_cert_file=/run/tls/tls.crt',
               '-c','ssl_key_file=/run/tls/tls.key','-c','hba_file=/etc/postgres/pg_hba.conf']
    pod['volumes'] += [{'name':'tls','secret':{'secretName':'postgres-tls','defaultMode':0o440}},
                       {'name':'hba','configMap':{'name':'postgres-hba'}}]
    c['volumeMounts'] += [{'name':'tls','mountPath':'/run/tls','readOnly':True},
                          {'name':'hba','mountPath':'/etc/postgres','readOnly':True}]
    docs += postgres + [secret('postgres-admin',{'password':runtime['master']['password']}),
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'postgres-hba','namespace':'wonderland'},
         'data':{'pg_hba.conf':'local all all trust\nhostssl all all 0.0.0.0/0 scram-sha-256\nhostssl all all ::/0 scram-sha-256\n'}}]
    logs=log_collector(target,{'application_log_group':'/wonderland/wonderland-demo/application','logs_role_arn':''})
    logs[0]['metadata'].pop('annotations',None)
    docs += logs
    # Bind rollouts to final secret contents after adapting the CA mount.
    fingerprint=hashlib.sha256(json.dumps({d['metadata']['name']:d['stringData'] for d in docs if d['kind']=='Secret'},sort_keys=True).encode()).hexdigest()
    for d in docs:
        if d['kind']=='Deployment':
            d['spec']['template']['metadata'].setdefault('annotations',{})['wonderland/runtime-sha256']=fingerprint
    return docs
