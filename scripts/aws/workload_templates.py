"""Render real EKS workloads without contacting AWS. Never print secret manifests."""

import base64
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy.engine import make_url
import yaml

ROOT = Path(__file__).resolve().parents[2]
SERVICES = {
    "attractions-service": "ATTRACTIONS_DATABASE_URL",
    "booking-service": "BOOKING_DATABASE_URL",
    "gate-ride-service": "GATE_DATABASE_URL",
    "analytics-worker": "ANALYTICS_DATABASE_URL",
}


def db_url(url, host):
    return (
        make_url(url)
        .set(host=host, port=5432)
        .update_query_dict(
            {
                "sslmode": "verify-full",
                "sslrootcert": "/app/wonderland_common/rds-global-bundle.pem",
            }
        )
        .render_as_string(hide_password=False)
    )


def secret(name, data):
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": name, "namespace": "wonderland"},
        "type": "Opaque",
        "stringData": data,
    }


def tls_material(extra_names=()):
    now = datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Wonderland demo internal CA")]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    result = {
        "ca": ca.public_bytes(serialization.Encoding.PEM).decode(),
        "services": {},
    }
    for name in [*SERVICES, "frontend", *extra_names]:
        leafkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        leaf = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
            .issuer_name(subject)
            .public_key(leafkey.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName(name),
                        x509.DNSName(name + ".wonderland.svc.cluster.local"),
                        x509.DNSName("localhost"),
                    ]
                ),
                critical=False,
            )
            .add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        result["services"][name] = {
            "tls.crt": leaf.public_bytes(serialization.Encoding.PEM).decode(),
            "tls.key": leafkey.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode(),
        }
    return result


def render(target, core, persistent, values, master, tls):
    docs = []
    for name in ["namespace.yaml", "services.yaml", "frontend.yaml", "hpa.yaml"]:
        docs.extend(
            yaml.safe_load_all(
                (ROOT / "infrastructure/kubernetes/base" / name).read_text()
            )
        )
    cm = {
        "APP_ENVIRONMENT": "aws",
        "APP_VERSION": target["release"],
        "APP_AUTH_MODE": "cognito",
        "APP_COGNITO_REGION": target["region"],
        "APP_COGNITO_USER_POOL_ID": persistent["pool_id"],
        "APP_COGNITO_CLIENT_ID": persistent["client_id"],
        "APP_ATTRACTIONS_URL": "https://attractions-service:8000",
        "APP_INTERNAL_CA_PATH": "/run/internal-ca/ca.crt",
        "APP_DATABASE_POOL_SIZE": "2",
        "APP_DATABASE_MAX_OVERFLOW": "2",
        "APP_FRONTEND_URL": persistent["frontend_origin"],
    }
    docs.append(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "app-config"},
            "data": cm,
        }
    )
    docs.append(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "internal-ca"},
            "data": {"ca.crt": tls["ca"]},
        }
    )
    docs.append(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "rds-ca"},
            "data": {
                "global-bundle.pem": (
                    ROOT / "wonderland_common/rds-global-bundle.pem"
                ).read_text()
            },
        }
    )
    role_names = {
        "attractions-service": "attractions-db",
        "booking-service": "booking-db",
        "gate-ride-service": "visits-db",
        "analytics-worker": "reporting-db",
    }
    for name, key in SERVICES.items():
        docs.append(
            secret(
                role_names[name],
                {"database-url": db_url(values[key], core["db_endpoint"])},
            )
        )
    docs.extend(
        [
            secret(
                "booking-ticket", {"private-key": values["APP_TICKET_PRIVATE_KEY_B64"]}
            ),
            secret("gate-ticket", {"public-key": values["APP_TICKET_PUBLIC_KEY_B64"]}),
            secret("ticket-owner", {"owner-secret": values["APP_TICKET_OWNER_SECRET"]}),
            secret(
                "booking-payment",
                {
                    "stripe-secret": values["APP_STRIPE_SECRET_KEY"],
                    "stripe-webhook": values["APP_STRIPE_WEBHOOK_SECRET"],
                },
            ),
        ]
    )
    for name, data in tls["services"].items():
        docs.append(secret(name + "-tls", data))
    migration = {k: v for k, v in values.items() if k.startswith("LOCAL_")}
    from sqlalchemy.engine import URL

    migration["MIGRATION_DATABASE_URL"] = db_url(
        URL.create(
            "postgresql+psycopg",
            username=master["username"],
            password=master["password"],
            host=core["db_endpoint"],
            port=5432,
            database="wonderland",
        ),
        core["db_endpoint"],
    )
    docs.append(secret("migration-config", migration))
    migration_job = next(
        yaml.safe_load_all(
            (ROOT / "infrastructure/kubernetes/local/migrate.yaml").read_text()
        )
    )
    migration_job["metadata"]["name"] = "schema-migrate-" + target["release"]
    migration_job["spec"]["ttlSecondsAfterFinished"] = 300
    mc = migration_job["spec"]["template"]["spec"]["containers"][0]
    mc["image"] = persistent["repositories"]["migrate"] + ":" + target["release"]
    mc["imagePullPolicy"] = "IfNotPresent"
    mc["command"] = ["python", "scripts/cloud_migrate.py"]
    docs.append(migration_job)
    for deployment_details in docs:
        if deployment_details["kind"] != "Namespace":
            deployment_details.setdefault("metadata", {})["namespace"] = "wonderland"
        if (
            deployment_details["kind"] == "Service"
            and deployment_details["metadata"]["name"] == "frontend"
        ):
            deployment_details["spec"]["ports"] = [
                p for p in deployment_details["spec"]["ports"] if p["name"] == "http"
            ]
        if deployment_details["kind"] != "Deployment":
            continue
        pod = deployment_details["spec"]["template"]["spec"]
        container = pod["containers"][0]
        name = deployment_details["metadata"]["name"]
        domain = "attractions-service" if name == "attractions-service-blue" else name
        container["image"] = (
            persistent["repositories"][domain] + ":" + target["release"]
        )
        container["imagePullPolicy"] = "IfNotPresent"
        pod["securityContext"]["fsGroup"] = 101 if domain == "frontend" else 10001
        pod.setdefault("volumes", []).extend(
            [
                {
                    "name": "tls",
                    "secret": {"secretName": domain + "-tls", "defaultMode": 0o440},
                },
                {"name": "internal-ca", "configMap": {"name": "internal-ca"}},
            ]
        )
        container.setdefault("volumeMounts", []).extend(
            [
                {"name": "tls", "mountPath": "/run/tls", "readOnly": True},
                {
                    "name": "internal-ca",
                    "mountPath": "/run/internal-ca",
                    "readOnly": True,
                },
            ]
        )
        for probe in ["startupProbe", "readinessProbe", "livenessProbe"]:
            if probe in container:
                container[probe]["httpGet"]["scheme"] = "HTTPS"
        if domain == "frontend":
            container["ports"] = [p for p in container["ports"] if p["name"] == "http"]
            pod["volumes"].append(
                {"name": "nginx-config", "configMap": {"name": "nginx-cloud"}}
            )
            container["volumeMounts"].append(
                {
                    "name": "nginx-config",
                    "mountPath": "/etc/nginx/conf.d",
                    "readOnly": True,
                }
            )
            container["ports"][0]["containerPort"] = 8443
            continue
        # Cloud identity comes from Cognito; no local signing secret is distributed.
        container["env"] = [
            e
            for e in container["env"]
            if e["name"]
            not in {
                "APP_AUTH_SECRET",
                "APP_LOCAL_WEBHOOK_SECRET",
                "APP_LOCAL_ACCOUNTS_JSON",
            }
        ]
        if domain == "booking-service":
            container["env"] += [
                {"name": "APP_PAYMENT_PROVIDER", "value": "stripe"},
                {
                    "name": "APP_STRIPE_SECRET_KEY",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "booking-payment",
                            "key": "stripe-secret",
                        }
                    },
                },
                {
                    "name": "APP_STRIPE_WEBHOOK_SECRET",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "booking-payment",
                            "key": "stripe-webhook",
                        }
                    },
                },
            ]
        container["args"] = [
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--no-access-log",
            "--ssl-keyfile",
            "/run/tls/tls.key",
            "--ssl-certfile",
            "/run/tls/tls.crt",
        ]
        container["command"] = ["/usr/local/bin/python", "-m"]
        # python -m uvicorn, not a shell; mounted certificates never appear in args.
        if domain == "analytics-worker":
            container["env"] += [
                {"name": "APP_ANALYTICS_TRANSPORT", "value": "sqs"},
                {"name": "APP_SQS_QUEUE_URL", "value": core["queue_url"]},
                {"name": "APP_SQS_DEAD_QUEUE_URL", "value": core["dead_queue_url"]},
                {"name": "APP_AWS_REGION", "value": target["region"]},
            ]
            pod["serviceAccountName"] = "analytics-worker"
        if domain == "booking-service":
            deployment_details["spec"]["replicas"] = 2
    # Exact TLS upstream names are verified against the privately generated CA.
    nginx = (
        (ROOT / "frontend/nginx.conf")
        .read_text()
        .split("# Local administrator app", 1)[0]
        .replace(
            "listen 8080;",
            "listen 8443 ssl;\n    ssl_certificate /run/tls/tls.crt;\n    ssl_certificate_key /run/tls/tls.key;\n    ssl_protocols TLSv1.2 TLSv1.3;\n    proxy_ssl_verify on;\n    proxy_ssl_trusted_certificate /run/internal-ca/ca.crt;\n    proxy_ssl_server_name on;",
        )
    )
    for name in SERVICES:
        nginx = nginx.replace(
            "proxy_pass http://" + name + ":8000/;",
            "proxy_pass https://" + name + ":8000/; proxy_ssl_name " + name + ";",
        )
    docs.append(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "nginx-cloud", "namespace": "wonderland"},
            "data": {"default.conf": nginx},
        }
    )
    docs.append(
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": "analytics-worker",
                "namespace": "wonderland",
                "annotations": {
                    "eks.amazonaws.com/role-arn": core["analytics_role_arn"]
                },
            },
        }
    )
    docs.append(
        {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": "wonderland",
                "namespace": "wonderland",
                "annotations": {
                    "alb.ingress.kubernetes.io/scheme": "internal",
                    "alb.ingress.kubernetes.io/target-type": "ip",
                    "alb.ingress.kubernetes.io/listen-ports": '[{"HTTPS":443}]',
                    "alb.ingress.kubernetes.io/certificate-arn": target[
                        "certificate_arn"
                    ],
                    "alb.ingress.kubernetes.io/backend-protocol": "HTTPS",
                    "alb.ingress.kubernetes.io/healthcheck-protocol": "HTTPS",
                    "alb.ingress.kubernetes.io/healthcheck-path": "/health",
                    "alb.ingress.kubernetes.io/ssl-policy": "ELBSecurityPolicy-TLS13-1-2-2021-06",
                    "alb.ingress.kubernetes.io/security-groups": core[
                        "alb_security_group_id"
                    ],
                    "alb.ingress.kubernetes.io/manage-backend-security-group-rules": "false",
                    "alb.ingress.kubernetes.io/tags": "Project=wonderland,Stage=demo",
                },
            },
            "spec": {
                "ingressClassName": "alb",
                "rules": [
                    {
                        "http": {
                            "paths": [
                                {
                                    "path": "/",
                                    "pathType": "Prefix",
                                    "backend": {
                                        "service": {
                                            "name": "frontend",
                                            "port": {"number": 8080},
                                        }
                                    },
                                }
                            ]
                        }
                    }
                ],
            },
        }
    )
    # Metabase remains private; access over the encrypted Kubernetes API port-forward.
    metadata_url = f"jdbc:postgresql://{core['db_endpoint']}:5432/wonderland_metadata?sslmode=verify-full&sslrootcert=/run/rds-ca/global-bundle.pem"
    docs.append(
        secret(
            "metabase-db",
            {"uri": metadata_url, "password": values["LOCAL_METABASE_ROLE_PASSWORD"]},
        )
    )
    docs.append(
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "metabase", "namespace": "wonderland"},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": "metabase"}},
                "template": {
                    "metadata": {"labels": {"app": "metabase"}},
                    "spec": {
                        "automountServiceAccountToken": False,
                        "containers": [
                            {
                                "name": "metabase",
                                "image": "metabase/metabase:v0.58.35",
                                "ports": [{"name": "http", "containerPort": 3000}],
                                "env": [
                                    {"name": "MB_DB_TYPE", "value": "postgres"},
                                    {
                                        "name": "MB_DB_USER",
                                        "value": "wonderland_metabase",
                                    },
                                    {
                                        "name": "MB_DB_PASS",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "name": "metabase-db",
                                                "key": "password",
                                            }
                                        },
                                    },
                                    {
                                        "name": "MB_DB_CONNECTION_URI",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "name": "metabase-db",
                                                "key": "uri",
                                            }
                                        },
                                    },
                                    {
                                        "name": "MB_ANON_TRACKING_ENABLED",
                                        "value": "false",
                                    },
                                    {"name": "MB_CHECK_FOR_UPDATES", "value": "false"},
                                    {"name": "JAVA_TOOL_OPTIONS", "value": "-Xmx768m"},
                                ],
                                "resources": {
                                    "requests": {"cpu": "250m", "memory": "1024Mi"},
                                    "limits": {"cpu": "1000m", "memory": "1536Mi"},
                                },
                                "readinessProbe": {
                                    "httpGet": {"path": "/api/health", "port": "http"},
                                    "periodSeconds": 10,
                                },
                                "startupProbe": {
                                    "httpGet": {"path": "/api/health", "port": "http"},
                                    "periodSeconds": 10,
                                    "failureThreshold": 60,
                                },
                                "volumeMounts": [
                                    {
                                        "name": "rds-ca",
                                        "mountPath": "/run/rds-ca",
                                        "readOnly": True,
                                    }
                                ],
                            }
                        ],
                        "volumes": [
                            {"name": "rds-ca", "configMap": {"name": "rds-ca"}}
                        ],
                    },
                },
            },
        }
    )
    docs.append(
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "metabase", "namespace": "wonderland"},
            "spec": {
                "selector": {"app": "metabase"},
                "ports": [{"name": "http", "port": 3000, "targetPort": "http"}],
            },
        }
    )
    metabase = next(
        deployment_details
        for deployment_details in docs
        if deployment_details["kind"] == "Deployment"
        and deployment_details["metadata"]["name"] == "metabase"
    )
    mp = metabase["spec"]["template"]["spec"]
    mp["securityContext"] = {
        "runAsNonRoot": True,
        "runAsUser": 2000,
        "runAsGroup": 2000,
        "fsGroup": 2000,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    mc = mp["containers"][0]
    mc["workingDir"] = "/tmp"
    mc["securityContext"] = {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    mp["volumes"].extend(
        [{"name": "tmp", "emptyDir": {}}, {"name": "plugins", "emptyDir": {}}]
    )
    mc["volumeMounts"].extend(
        [
            {"name": "tmp", "mountPath": "/tmp"},
            {"name": "plugins", "mountPath": "/plugins"},
        ]
    )
    secrets_by_name = {
        deployment_details["metadata"]["name"]: deployment_details["stringData"]
        for deployment_details in docs
        if deployment_details["kind"] == "Secret"
    }
    for deployment_details in docs:
        if deployment_details["kind"] != "Deployment":
            continue
        pod = deployment_details["spec"]["template"]["spec"]
        names = {
            v["secret"]["secretName"] for v in pod.get("volumes", []) if "secret" in v
        }
        for c in pod["containers"]:
            names.update(
                e["valueFrom"]["secretKeyRef"]["name"]
                for e in c.get("env", [])
                if "secretKeyRef" in e.get("valueFrom", {})
            )
        fingerprint = hashlib.sha256(
            json.dumps(
                {n: secrets_by_name[n] for n in sorted(names)}, sort_keys=True
            ).encode()
        ).hexdigest()
        deployment_details["spec"]["template"]["metadata"].setdefault(
            "annotations", {}
        )["wonderland/secret-config-hash"] = fingerprint
        if deployment_details["spec"]["replicas"] > 1:
            pod["affinity"] = {
                "podAntiAffinity": {
                    "preferredDuringSchedulingIgnoredDuringExecution": [
                        {
                            "weight": 100,
                            "podAffinityTerm": {
                                "topologyKey": "kubernetes.io/hostname",
                                "labelSelector": {
                                    "matchLabels": deployment_details["spec"][
                                        "selector"
                                    ]["matchLabels"]
                                },
                            },
                        }
                    ]
                }
            }
    return docs


def log_collector(target, core):
    """Only sanitized application API stdout; no vendor/migration/secret logs."""
    config = f"""[SERVICE]
    Flush 1
    Daemon Off
    Log_Level warn
    Parsers_File /fluent-bit/custom/parsers.conf
[INPUT]
    Name tail
    Path /var/log/containers/*_wonderland_api-*.log
    Tag app.*
    Parser cri
    DB /var/state/tail.db
    Mem_Buf_Limit 10MB
    Skip_Long_Lines On
    Read_from_Head On
[OUTPUT]
    Name cloudwatch_logs
    Match app.*
    region {target["region"]}
    log_group_name {core["application_log_group"]}
    log_stream_prefix node-
    log_key log
    auto_create_group false
"""
    parser = """[PARSER]
    Name cri
    Format regex
    Regex ^(?<time>[^ ]+) (?<stream>stdout|stderr) (?<_p>[^ ]*) (?<log>.*)$
    Time_Key time
    Time_Format %Y-%m-%dT%H:%M:%S.%L%z
"""
    return [
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": "wonderland-logs",
                "namespace": "kube-system",
                "annotations": {"eks.amazonaws.com/role-arn": core["logs_role_arn"]},
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "wonderland-logs", "namespace": "kube-system"},
            "data": {"fluent-bit.conf": config, "parsers.conf": parser},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "DaemonSet",
            "metadata": {"name": "wonderland-logs", "namespace": "kube-system"},
            "spec": {
                "selector": {"matchLabels": {"app": "wonderland-logs"}},
                "template": {
                    "metadata": {"labels": {"app": "wonderland-logs"}},
                    "spec": {
                        "serviceAccountName": "wonderland-logs",
                        "automountServiceAccountToken": False,
                        "securityContext": {
                            "runAsUser": 0,
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "containers": [
                            {
                                "name": "logs",
                                "image": "public.ecr.aws/aws-observability/aws-for-fluent-bit:2.34.3.20261001",
                                "command": ["/fluent-bit/bin/fluent-bit"],
                                "args": ["-c", "/fluent-bit/custom/fluent-bit.conf"],
                                "resources": {
                                    "requests": {"cpu": "50m", "memory": "64Mi"},
                                    "limits": {"cpu": "200m", "memory": "128Mi"},
                                },
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                                "volumeMounts": [
                                    {
                                        "name": "logs",
                                        "mountPath": "/var/log",
                                        "readOnly": True,
                                    },
                                    {"name": "state", "mountPath": "/var/state"},
                                    {
                                        "name": "config",
                                        "mountPath": "/fluent-bit/custom",
                                        "readOnly": True,
                                    },
                                ],
                            }
                        ],
                        "volumes": [
                            {
                                "name": "logs",
                                "hostPath": {"path": "/var/log", "type": "Directory"},
                            },
                            {"name": "state", "emptyDir": {}},
                            {
                                "name": "config",
                                "configMap": {"name": "wonderland-logs"},
                            },
                        ],
                    },
                },
            },
        },
    ]
