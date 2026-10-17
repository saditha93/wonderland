"""Private single-node workloads; no local identity or public database/admin ports."""

import hashlib
import json
from scripts.aws.workload_templates import (
    ROOT,
    render as cloud_render,
    secret,
    log_collector,
)
from sqlalchemy.engine import make_url
import yaml


def render(target, deployment, runtime):
    core = dict(
        db_endpoint="postgres",
        queue_url=deployment["queue_url"],
        dead_queue_url=deployment["dead_queue_url"],
        analytics_role_arn="",
        alb_security_group_id="",
    )
    persistent = dict(
        pool_id=deployment["pool_id"],
        client_id=deployment["client_id"],
        frontend_origin=deployment["portals"]["visitor"]["origin"],
        repositories=deployment["repositories"],
    )
    docs = cloud_render(
        {**target, "certificate_arn": ""},
        core,
        persistent,
        runtime["values"],
        runtime["master"],
        runtime["tls"],
    )
    docs = [
        deployment_details
        for deployment_details in docs
        if deployment_details["kind"] != "Ingress"
        and deployment_details["metadata"]["name"] not in {"frontend", "nginx-cloud"}
    ]
    for deployment_details in docs:
        name = deployment_details["metadata"]["name"]
        if deployment_details["kind"] == "ServiceAccount":
            deployment_details["metadata"].pop("annotations", None)
        if name == "rds-ca":
            deployment_details["data"]["global-bundle.pem"] = runtime["tls"]["ca"]
        if deployment_details["kind"] == "Secret":
            for k, v in deployment_details["stringData"].items():
                if v.startswith("postgresql"):
                    deployment_details["stringData"][k] = (
                        make_url(v)
                        .update_query_dict(
                            {"sslrootcert": "/run/rds-ca/global-bundle.pem"}
                        )
                        .render_as_string(hide_password=False)
                    )
        if deployment_details["kind"] not in {"Deployment", "Job"}:
            continue
        pod = deployment_details["spec"]["template"]["spec"]
        if deployment_details["kind"] == "Deployment":
            # Reserve space for Minikube's control plane, HPA and rollout surge.
            for container in pod["containers"]:
                container["resources"]["requests"]["cpu"] = (
                    "100m" if name == "metabase" else "50m"
                )
        pod["imagePullSecrets"] = [{"name": "ecr-pull"}]
        if name != "metabase":
            pod.setdefault("volumes", []).append(
                {"name": "rds-ca", "configMap": {"name": "rds-ca"}}
            )
            for c in pod["containers"]:
                c.setdefault("volumeMounts", []).append(
                    {"name": "rds-ca", "mountPath": "/run/rds-ca", "readOnly": True}
                )
    postgres = list(
        yaml.safe_load_all(
            (ROOT / "infrastructure/kubernetes/local/postgres.yaml").read_text()
        )
    )
    for deployment_details in postgres:
        deployment_details["metadata"]["namespace"] = "wonderland"
    pg = next(
        deployment_details
        for deployment_details in postgres
        if deployment_details["kind"] == "StatefulSet"
    )
    pod = pg["spec"]["template"]["spec"]
    c = pod["containers"][0]
    c["resources"]["requests"]["cpu"] = "100m"
    c["args"] = [
        "-c",
        "ssl=on",
        "-c",
        "ssl_cert_file=/run/tls/tls.crt",
        "-c",
        "ssl_key_file=/run/tls/tls.key",
        "-c",
        "hba_file=/etc/postgres/pg_hba.conf",
    ]
    pod["volumes"] += [
        {"name": "tls", "secret": {"secretName": "postgres-tls", "defaultMode": 0o440}},
        {"name": "hba", "configMap": {"name": "postgres-hba"}},
    ]
    c["volumeMounts"] += [
        {"name": "tls", "mountPath": "/run/tls", "readOnly": True},
        {"name": "hba", "mountPath": "/etc/postgres", "readOnly": True},
    ]
    docs += postgres + [
        secret("postgres-admin", {"password": runtime["master"]["password"]}),
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "postgres-hba", "namespace": "wonderland"},
            "data": {
                "pg_hba.conf": "local all all trust\nhostssl all all 0.0.0.0/0 scram-sha-256\nhostssl all all ::/0 scram-sha-256\n"
            },
        },
    ]
    logs = log_collector(
        target,
        {
            "application_log_group": "/wonderland/wonderland-demo/application",
            "logs_role_arn": "",
        },
    )
    logs[0]["metadata"].pop("annotations", None)
    docs += logs
    docs.append(secret("ingress-ca", {"ca.crt": runtime["tls"]["ca"]}))
    docs += list(
        yaml.safe_load_all(
            (ROOT / "infrastructure/kubernetes/aws/ingress.yaml").read_text()
        )
    )
    next(x for x in docs if x["metadata"]["name"] == "frontend-tls")[
        "type"
    ] = "kubernetes.io/tls"
    # Bind rollouts to final secret contents after adapting the CA mount.
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                deployment_details["metadata"]["name"]: deployment_details["stringData"]
                for deployment_details in docs
                if deployment_details["kind"] == "Secret"
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    for deployment_details in docs:
        if deployment_details["kind"] == "Deployment":
            deployment_details["spec"]["template"]["metadata"].setdefault(
                "annotations", {}
            )["wonderland/runtime-sha256"] = fingerprint
    return docs
