"""Offline-first cloud lifecycle. No account call without explicit CLI authorization.

All mutations additionally require a concrete saved-plan/action digest. The
agent must obtain human approval before passing those flags; Phase 6 does not.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.aws_workloads import render, tls_material
from dotenv import dotenv_values
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
import boto3
import httpx
import yaml


class GuardError(ValueError):
    """A fixed, safe-to-display authorization/configuration refusal."""


STAGES = {"bootstrap", "persistent", "demo", "edge"}
TF = shutil.which("terraform") or str(ROOT / "tmp/tools/terraform")
KUBE = ROOT / "secrets/aws.kubeconfig"


def private_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, indent=2)
    os.chmod(path, 0o600)


def digest(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def target_config(path):
    data = json.loads(Path(path).read_text())
    allowed = {
        "account_id",
        "region",
        "name",
        "release",
        "profile",
        "state_bucket",
        "operator_role_arn",
        "operator_cidr",
        "azs",
        "eks_version",
        "rds_engine_version",
        "alarm_email",
        "tls_server_name",
        "hosted_zone_id",
        "node_instance_type",
        "db_instance_class",
        "allow_database_destroy",
        "retain_final_snapshot",
        "final_snapshot_suffix",
    }
    if set(data) - allowed:
        raise GuardError(
            "Target contains unsupported fields; credentials belong in the named AWS profile/private secret files"
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", data.get("profile", "")):
        raise GuardError("Use a named AWS profile")
    for key, pattern in {
        "account_id": r"[0-9]{12}",
        "region": r"[a-z]{2}-[a-z]+-[0-9]",
        "name": r"[a-z][a-z0-9-]{2,24}",
        "release": r"[a-z][a-z0-9-]{2,30}",
    }.items():
        if not re.fullmatch(pattern, data.get(key, "")):
            raise GuardError("Invalid target field: " + key)
    if data["region"].startswith("cn-"):
        raise GuardError("This configuration supports commercial AWS regions only")
    if not str(data.get("operator_role_arn", "")).startswith(
        "arn:aws:iam::" + data["account_id"] + ":role/"
    ):
        raise GuardError("Use a non-root operator IAM role in the selected account")
    return data


def source_digest():
    paths = []
    for dirname in ["wonderland_common", "services", "frontend/src"]:
        paths += [
            p
            for p in (ROOT / dirname).rglob("*")
            if p.is_file() and "__pycache__" not in str(p)
        ]
    paths += [
        ROOT / p
        for p in [
            "requirements.lock",
            "frontend/package.json",
            "frontend/package-lock.json",
            "frontend/vite.config.ts",
            "frontend/index.html",
            "frontend/admin/index.html",
            "frontend/Dockerfile.kubernetes",
            "frontend/nginx.conf",
            "scripts/cloud_migrate.py",
            "scripts/db_migrate.py",
            "scripts/aws_workloads.py",
            "scripts/cloud.py",
            "scripts/provision-metabase.py",
            "scripts/local_phase3.py",
            "scripts/configure-compose.py",
            "infrastructure/kubernetes/aws/metrics-server.yaml",
            "analytics/dashboard.json",
        ]
    ]
    return digest({str(p.relative_to(ROOT)): file_sha(p) for p in sorted(paths)})


def review_spec(target, action):
    spec = {
        "action": action,
        "target": target,
        "source_sha256": source_digest(),
        "namespace": "wonderland",
        "persistent_destroy_allowed": False,
    }
    if action == "update-payment":
        spec["private_input_sha256"] = digest(stripe_values())
    return spec


def approve_action(args, target):
    expected = digest(review_spec(target, args.action))
    if args.approve_action != expected or not args.acknowledge_costs:
        raise GuardError(
            "Review this action first; supply its exact digest and acknowledge costs"
        )


def account_session(args, target):
    if not args.allow_account_access:
        raise GuardError(
            "AWS account access is not authorized; no AWS session/client was created"
        )
    credentials = aws_environment(target)
    session = boto3.Session(region_name=target["region"],
                            **(credentials or {"profile_name": target["profile"]}))
    client = session.client(
        "sts",
        config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 1}),
    )
    identity = client.get_caller_identity()
    if identity["Account"] != target["account_id"] or identity["Arn"].endswith(":root"):
        raise GuardError("AWS identity is root or belongs to another account")
    # Require the exact role configured for EKS access; reject broad administrator credentials from another principal.
    role = target["operator_role_arn"].split(":role/", 1)[1].split("/")[-1]
    arn = identity["Arn"]
    if arn != target["operator_role_arn"] and not re.search(
        r":assumed-role/" + re.escape(role) + r"/[^/]+$", arn
    ):
        raise GuardError("Assume the configured operator role first")
    return session


def aws_environment(target):
    """Read only cloud credentials, without importing unrelated app settings."""
    values = dotenv_values(ROOT / ".env", interpolate=False)
    keys = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]
    selected = dict(values if any(values.get(k) for k in keys) else os.environ)
    if not any(selected.get(k) for k in keys):
        return {}
    if not all(selected.get(k) for k in keys[:2]):
        raise GuardError("Provide both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
    region = selected.get("AWS_REGION") or selected.get("AWS_DEFAULT_REGION")
    if region and region != target["region"]:
        raise GuardError("AWS environment region must match the reviewed target")
    for key in keys:
        os.environ.pop(key, None)
        if selected.get(key):
            os.environ[key] = selected[key]
    os.environ.pop("AWS_PROFILE", None)
    os.environ.pop("AWS_DEFAULT_PROFILE", None)
    return {"aws_access_key_id": selected[keys[0]],
            "aws_secret_access_key": selected[keys[1]],
            "aws_session_token": selected.get(keys[2]) or None}


def cloud_profile(target):
    """Environment credentials also serve Terraform, Helm and the token plugin."""
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        return {}
    return {"AWS_PROFILE": target["profile"]}


def stripe_values():
    keys = ["APP_STRIPE_SECRET_KEY", "APP_STRIPE_WEBHOOK_SECRET"]
    primary = dotenv_values(ROOT / ".env", interpolate=False)
    values = primary if any(primary.get(k) for k in keys) else dotenv_values(
        ROOT / "secrets/stripe.env", interpolate=False)
    if not (values.get(keys[0]) or "").startswith("sk_test_") or not (
        values.get(keys[1]) or "").startswith("whsec_"):
        raise GuardError("Configure Stripe test and webhook signing secrets in .env")
    return {key: values[key] for key in keys}


def command(argv, **kwargs):
    return subprocess.run(argv, cwd=ROOT, check=True, text=True, **kwargs)


def tf(stage, *args, **kwargs):
    env = {
        **os.environ,
        "AWS_EC2_METADATA_DISABLED": "true",
        "TF_DATA_DIR": str(ROOT / "secrets/terraform-data" / stage),
        "TF_IN_AUTOMATION": "true",
    }
    return command(
        [TF, "-chdir=" + str(ROOT / "infrastructure/terraform" / stage), *args],
        env=env,
        **kwargs,
    )


def outputs(stage):
    data = json.loads(tf(stage, "output", "-json", capture_output=True).stdout)
    return {k: v["value"] for k, v in data.items()}


def backend(target, stage):
    return {
        "bucket": target["state_bucket"],
        "key": "wonderland/" + target["name"] + "/" + stage + ".tfstate",
        "region": target["region"],
        "encrypt": True,
        "use_lockfile": True,
        **({"profile": target["profile"]} if cloud_profile(target) else {}),
        "allowed_account_ids": [target["account_id"]],
    }


def tfvars(target, stage):
    values = {k: target[k] for k in ["region", "account_id", "name"]}
    values["stage"] = stage
    if stage == "bootstrap":
        values["state_bucket"] = target["state_bucket"]
    if stage == "persistent":
        values.update(
            tls_server_name=target["tls_server_name"],
            hosted_zone_id=target["hosted_zone_id"],
        )
    if stage == "demo":
        for k in [
            "azs",
            "operator_cidr",
            "operator_role_arn",
            "eks_version",
            "rds_engine_version",
            "alarm_email",
        ]:
            values[k] = target[k]
        values["frontend_origin"] = outputs("persistent")["frontend_origin"]
        for k in [
            "node_instance_type",
            "db_instance_class",
            "allow_database_destroy",
            "retain_final_snapshot",
            "final_snapshot_suffix",
        ]:
            if k in target:
                values[k] = target[k]
    if stage == "edge":
        core = outputs("demo")
        persistent = outputs("persistent")
        edge = json.loads((ROOT / "secrets/edge-discovery.json").read_text())
        values.update(
            vpc_id=core["vpc_id"],
            private_subnets=core["private_subnets"],
            frontend_origin=persistent["frontend_origin"],
            admin_origin=persistent["admin_origin"],
            tls_server_name=target["tls_server_name"],
            **edge,
        )
    return values


def initialize(target, stage):
    os.environ.update(cloud_profile(target))
    os.environ["AWS_REGION"] = target["region"]
    args = ["init", "-input=false", "-no-color"]
    if (
        stage != "bootstrap"
        or (ROOT / "infrastructure/terraform/bootstrap/backend_override.tf").exists()
    ):
        p = ROOT / "secrets" / f"{stage}.backend.json"
        private_json(p, backend(target, stage))
        args += ["-backend-config=" + str(p)]
    tf(stage, *args)


def plan(args, target):
    initialize(target, args.stage)
    p = ROOT / "secrets" / f"{args.stage}.tfvars.json"
    private_json(p, tfvars(target, args.stage))
    binary = ROOT / "secrets" / f"{args.stage}.tfplan"
    tf(
        args.stage,
        "plan",
        "-input=false",
        "-no-color",
        "-var-file=" + str(p),
        "-out=" + str(binary),
        *(["-destroy"] if args.destroy else []),
    )
    metadata = {
        "stage": args.stage,
        "target_digest": digest(target),
        "plan_sha256": file_sha(binary),
        "source_sha256": source_digest(),
        "terraform_sha256": terraform_digest(),
        "destroy": args.destroy,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    private_json(binary.with_suffix(".review.json"), metadata)
    # Native Terraform text suppresses sensitive values; keep plan JSON private, never serialize it publicly.
    print("Saved plan SHA-256:", metadata["plan_sha256"])
    print("Review plan and pricing before approving this exact hash.")


def terraform_digest():
    return digest(
        {
            str(p.relative_to(ROOT)): file_sha(p)
            for p in sorted((ROOT / "infrastructure/terraform").rglob("*.tf"))
            if ".terraform" not in p.parts
        }
    )


def checked_plan(args, target):
    if args.stage not in STAGES:
        raise GuardError("Unknown stage")
    path = ROOT / "secrets" / f"{args.stage}.tfplan"
    metadata = json.loads(path.with_suffix(".review.json").read_text())
    expected = file_sha(path)
    if (
        not args.acknowledge_costs
        or args.approve_plan != expected
        or metadata["plan_sha256"] != expected
    ):
        raise GuardError("Exact saved plan approval and cost acknowledgment required")
    if (
        metadata["stage"] != args.stage
        or metadata["target_digest"] != digest(target)
        or metadata["source_sha256"] != source_digest()
        or metadata["terraform_sha256"] != terraform_digest()
    ):
        raise GuardError("Target or source changed since review; generate a new plan")
    if datetime.now(timezone.utc) - datetime.fromisoformat(
        metadata["created_at"]
    ) > timedelta(hours=24):
        raise GuardError("Plan review expired after 24 hours")
    if args.action == "destroy" and (
        not metadata["destroy"] or args.stage not in {"edge", "demo"}
    ):
        raise GuardError("Only reviewed temporary edge/demo destruction is allowed")
    if (
        args.action == "destroy"
        and args.stage == "demo"
        and not target.get("allow_database_destroy", False)
    ):
        raise GuardError(
            "Review and apply a deletion-protection update before the core destroy plan"
        )
    if args.action == "apply" and metadata["destroy"]:
        raise GuardError("Use the explicit destroy action for a destruction plan")
    return path


def kube(target, *args, **kwargs):
    context = "wonderland-aws-" + target["name"]
    config = yaml.safe_load(KUBE.read_text())
    entry = next(c["context"] for c in config["contexts"] if c["name"] == context)
    cluster = next(
        c["cluster"] for c in config["clusters"] if c["name"] == entry["cluster"]
    )
    expected = json.loads((ROOT / "secrets/aws-cluster.json").read_text())
    if (
        cluster["server"] != expected["endpoint"]
        or expected["name"] != target["name"]
        or expected["account_id"] != target["account_id"]
    ):
        raise ValueError("AWS Kubernetes context does not match the approved target")
    return command(
        [
            "kubectl",
            "--kubeconfig",
            str(KUBE),
            "--context",
            context,
            "-n",
            "wonderland",
            *args,
        ],
        env={
            **os.environ,
            **cloud_profile(target),
            "AWS_REGION": target["region"],
        },
        **kwargs,
    )


def connect_cluster(session, target):
    cluster = session.client("eks").describe_cluster(name=target["name"])["cluster"]
    context = "wonderland-aws-" + target["name"]
    # Dedicated kubeconfig with an exec token plugin; never display token/certificate credentials.
    config = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": context,
                "cluster": {
                    "server": cluster["endpoint"],
                    "certificate-authority-data": cluster["certificateAuthority"][
                        "data"
                    ],
                },
            }
        ],
        "contexts": [
            {
                "name": context,
                "context": {
                    "cluster": context,
                    "user": context,
                    "namespace": "wonderland",
                },
            }
        ],
        "users": [
            {
                "name": context,
                "user": {
                    "exec": {
                        "apiVersion": "client.authentication.k8s.io/v1beta1",
                        "command": "aws",
                        "args": [
                            "eks",
                            "get-token",
                            "--cluster-name",
                            target["name"],
                            "--region",
                            target["region"],
                            *(["--profile", target["profile"]] if cloud_profile(target) else []),
                        ],
                        "interactiveMode": "Never",
                    }
                },
            }
        ],
        "current-context": context,
    }
    private_json(KUBE, config)
    private_json(
        ROOT / "secrets/aws-cluster.json",
        {
            "endpoint": cluster["endpoint"],
            "name": target["name"],
            "account_id": target["account_id"],
        },
    )


def publish(session, target):
    repositories = outputs("persistent")["repositories"]
    ecr = session.client("ecr")
    auth = ecr.get_authorization_token()["authorizationData"][0]
    import base64

    user, password = base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
    # Docker login reads its token on stdin; capture output and never log the auth response.
    command(
        [
            "docker",
            "login",
            "--username",
            user,
            "--password-stdin",
            auth["proxyEndpoint"],
        ],
        input=password,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for name, url in repositories.items():
            dockerfile = (
                "frontend/Dockerfile.kubernetes"
                if name == "frontend"
                else (
                    "infrastructure/local/Dockerfile.migrate"
                    if name == "migrate"
                    else f"services/{name}/Dockerfile"
                )
            )
            image = url + ":" + target["release"]
            command(
                [
                    "docker",
                    "build",
                    "--platform",
                    "linux/arm64",
                    "-f",
                    dockerfile,
                    "-t",
                    image,
                    "frontend" if name == "frontend" else ".",
                ]
            )
            command(["docker", "push", image])
    finally:
        command(
            ["docker", "logout", auth["proxyEndpoint"]],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )


def runtime_values(session, target, core):
    sm = session.client("secretsmanager")
    try:
        values = json.loads(
            sm.get_secret_value(SecretId=core["runtime_secret_arn"])["SecretString"]
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        values = None
    if values is None:
        path = ROOT / "secrets/cloud-runtime.env"
        command(
            [sys.executable, "scripts/configure-compose.py", "--output", str(path)],
            stdout=subprocess.DEVNULL,
        )
        values = dict(dotenv_values(path))
        values["LOCAL_METABASE_ROLE_PASSWORD"] = __import__("secrets").token_urlsafe(36)
        stripe = stripe_values()
        values.update(
            {
                k: stripe[k]
                for k in ["APP_STRIPE_SECRET_KEY", "APP_STRIPE_WEBHOOK_SECRET"]
            }
        )
        sm.put_secret_value(
            SecretId=core["runtime_secret_arn"], SecretString=json.dumps(values)
        )
    if not values["APP_STRIPE_SECRET_KEY"].startswith("sk_test_"):
        raise ValueError("Production payment keys prohibited")
    return values


def deploy(session, target):
    connect_cluster(session, target)
    core = outputs("demo")
    persistent = outputs("persistent")
    values = runtime_values(session, target, core)
    master = json.loads(
        session.client("secretsmanager").get_secret_value(
            SecretId=core["db_master_secret_arn"]
        )["SecretString"]
    )
    tls_path = ROOT / "secrets/cloud-tls.json"
    tls = json.loads(tls_path.read_text()) if tls_path.exists() else tls_material()
    private_json(tls_path, tls)
    target = {**target, "certificate_arn": persistent["certificate_arn"]}
    docs = render(target, core, persistent, values, master, tls)
    from scripts.aws_workloads import db_url

    reporting = ROOT / "secrets/cloud-reporting.env"
    fd = os.open(reporting, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(
            "BI_DATABASE_URL="
            + db_url(values["BI_DATABASE_URL"], core["db_endpoint"])
            + "\n"
        )
    # Reviewable private render; no secret YAML on stdout or command line.
    rendered = ROOT / "secrets/aws-rendered.yaml"
    fd = os.open(rendered, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        yaml.safe_dump_all(docs, f, sort_keys=False)
    kube(
        target,
        "apply",
        "-f",
        "-",
        input=yaml.safe_dump(next(d for d in docs if d["kind"] == "Namespace")),
    )
    secrets_docs = [
        d for d in docs if d["kind"] in {"Secret", "ConfigMap", "ServiceAccount"}
    ]
    kube(
        target,
        "apply",
        "--server-side",
        "--field-manager=wonderland-cloud",
        "-f",
        "-",
        input=yaml.safe_dump_all(secrets_docs),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    job = next(d for d in docs if d["kind"] == "Job")
    kube(target, "apply", "-f", "-", input=yaml.safe_dump(job))
    kube(
        target,
        "wait",
        "--for=condition=complete",
        "job/" + job["metadata"]["name"],
        "--timeout=300s",
    )
    kube(
        target,
        "delete",
        "secret",
        "migration-config",
        "--ignore-not-found=true",
        stdout=subprocess.DEVNULL,
    )
    kube(
        target,
        "apply",
        "-f",
        "-",
        input=yaml.safe_dump_all(
            [
                d
                for d in docs
                if d["kind"]
                not in {"Secret", "ConfigMap", "ServiceAccount", "Job", "Namespace"}
            ]
        ),
    )
    for name in [
        "attractions-service-blue",
        "booking-service",
        "gate-ride-service",
        "analytics-worker",
        "frontend",
        "metabase",
    ]:
        kube(target, "rollout", "status", "deployment/" + name, "--timeout=600s")
    print(
        "AWS workload rollout completed; run discovery, edge planning, hosting and actual verification next."
    )


def controller(session, target):
    connect_cluster(session, target)
    core = outputs("demo")
    # Pinned chart and vendored official v2.14.1 IAM policy; no installation during Phase 6.
    command(["helm", "repo", "add", "eks", "https://aws.github.io/eks-charts"])
    command(["helm", "repo", "update", "eks"])
    command(
        [
            "helm",
            "upgrade",
            "--install",
            "aws-load-balancer-controller",
            "eks/aws-load-balancer-controller",
            "--version",
            "1.14.1",
            "--namespace",
            "kube-system",
            "--kubeconfig",
            str(KUBE),
            "--kube-context",
            "wonderland-aws-" + target["name"],
            "--set",
            "clusterName=" + target["name"],
            "--set",
            "enableBackendSecurityGroup=false",
            "--set",
            "region=" + target["region"],
            "--set",
            "vpcId=" + core["vpc_id"],
            "--set",
            "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn="
            + core["alb_role_arn"],
            "--wait",
            "--timeout",
            "300s",
        ],
        env={**os.environ, **cloud_profile(target)},
    )
    command(
        [
            "kubectl",
            "--kubeconfig",
            str(KUBE),
            "--context",
            "wonderland-aws-" + target["name"],
            "apply",
            "-f",
            str(ROOT / "infrastructure/kubernetes/aws/metrics-server.yaml"),
        ]
    )

    from scripts.aws_workloads import log_collector

    command(
        [
            "kubectl",
            "--kubeconfig",
            str(KUBE),
            "--context",
            "wonderland-aws-" + target["name"],
            "apply",
            "-f",
            "-",
        ],
        input=yaml.safe_dump_all(log_collector(target, core)),
        env={**os.environ, **cloud_profile(target)},
    )


def update_payment(session, target):
    core = outputs("demo")
    sm = session.client("secretsmanager")
    values = json.loads(
        sm.get_secret_value(SecretId=core["runtime_secret_arn"])["SecretString"]
    )
    keys = stripe_values()
    values.update(
        {k: keys[k] for k in ["APP_STRIPE_SECRET_KEY", "APP_STRIPE_WEBHOOK_SECRET"]}
    )
    sm.put_secret_value(
        SecretId=core["runtime_secret_arn"], SecretString=json.dumps(values)
    )
    deploy(session, target)


def discover(session, target):
    connect_cluster(session, target)
    ingress = json.loads(
        kube(
            target, "get", "ingress", "wonderland", "-o", "json", capture_output=True
        ).stdout
    )
    hostname = ingress["status"]["loadBalancer"]["ingress"][0]["hostname"]
    elb = session.client("elbv2")
    found = [
        lb
        for page in elb.get_paginator("describe_load_balancers").paginate()
        for lb in page["LoadBalancers"]
        if lb["DNSName"] == hostname
        and lb["VpcId"] == outputs("demo")["vpc_id"]
        and lb["Scheme"] == "internal"
    ]
    if len(found) != 1:
        raise ValueError("Expected one internal ALB in the approved VPC")
    lb = found[0]
    if outputs("demo")["alb_security_group_id"] not in lb["SecurityGroups"]:
        raise ValueError(
            "Load balancer does not use its reviewed Terraform security group"
        )
    listeners = elb.describe_listeners(LoadBalancerArn=lb["LoadBalancerArn"])[
        "Listeners"
    ]
    listener = next(
        l for l in listeners if l["Port"] == 443 and l["Protocol"] == "HTTPS"
    )
    private_json(
        ROOT / "secrets/edge-discovery.json",
        {
            "listener_arn": listener["ListenerArn"],
            "alb_security_group_id": outputs("demo")["alb_security_group_id"],
        },
    )
    private_json(
        ROOT / "secrets/alb-inventory.json",
        {"arn": lb["LoadBalancerArn"], "dns": hostname},
    )
    print(
        "Discovered approved internal HTTPS listener; edge variables saved privately."
    )


def hosting(session, target):
    persistent = outputs("persistent")
    api = outputs("edge")["api_url"]
    env = {
        **{k: v for k, v in os.environ.items()
           if not k.startswith(("AWS_", "APP_STRIPE_"))},
        "VITE_AUTH_MODE": "cognito",
        "VITE_COGNITO_USER_POOL_ID": persistent["pool_id"],
        "VITE_COGNITO_USER_POOL_CLIENT_ID": persistent["client_id"],
        "VITE_API_BASE_URL": api,
        "VITE_METABASE_URL": "",
        "VITE_DEMO_MODE": "false",
    }
    command(["npm", "--prefix", "frontend", "run", "build"], env=env)
    portals = [
        ("visitor", "dist", "amplify_app_id", "frontend_origin"),
        ("admin", "dist-admin", "admin_amplify_app_id", "admin_origin"),
    ]
    for _, directory, app_key, origin_key in portals:
        if not (ROOT / "frontend" / directory / "index.html").is_file():
            raise GuardError("Both visitor and admin builds must contain index.html")
        if not persistent.get(app_key) or not persistent.get(origin_key):
            raise GuardError("Apply the persistent stage with both hosting targets first")
    for portal, directory, app_key, origin_key in portals:
        deploy_portal(session, portal, ROOT / "frontend" / directory,
                      persistent[app_key], persistent[origin_key])


def deploy_portal(session, portal, directory, app_id, origin):
    archive = ROOT / "secrets" / f"{portal}-deploy.zip"
    archive.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in directory.rglob("*"):
            if p.is_file():
                z.write(p, str(p.relative_to(directory)))
    archive.chmod(0o600)
    amplify = session.client("amplify")
    job = amplify.create_deployment(
        appId=app_id, branchName="demo"
    )
    import httpx

    with archive.open("rb") as f:
        r = httpx.put(job["zipUploadUrl"], content=f.read(), timeout=120)
    if r.status_code >= 400:
        raise ValueError("Amplify artifact upload failed; signed URL suppressed")
    amplify.start_deployment(
        appId=app_id, branchName="demo", jobId=job["jobId"]
    )
    for _ in range(60):
        status = amplify.get_job(
            appId=app_id, branchName="demo", jobId=job["jobId"]
        )["job"]["summary"]["status"]
        if status == "SUCCEED":
            print(f"Amplify {portal} deployment succeeded:", origin)
            return
        if status in {"FAILED", "CANCELLED"}:
            raise ValueError(f"Amplify {portal} deployment failed")
        time.sleep(5)
    raise ValueError(
        "Amplify deployment did not finish in 300 seconds; no success claimed"
    )


def verify(session, target):
    connect_cluster(session, target)
    core = outputs("demo")
    url = outputs("edge")["api_url"]
    import httpx

    persistent = outputs("persistent")
    for key in ["frontend_origin", "admin_origin"]:
        origin = persistent[key]
        if httpx.get(origin, timeout=15).status_code != 200:
            raise GuardError("Hosted portal unavailable: " + key)
        response = httpx.options(
            url + "/api/booking/bookings",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                     "Access-Control-Request-Headers": "authorization,content-type"},
            timeout=15,
        )
        if response.status_code not in {200, 204} or response.headers.get(
            "access-control-allow-origin"
        ) != origin:
            raise GuardError("Hosted portal CORS failed: " + key)
    denied = httpx.options(
        url + "/api/booking/bookings",
        headers={"Origin": "https://unapproved.invalid",
                 "Access-Control-Request-Method": "POST"}, timeout=15,
    )
    if denied.headers.get("access-control-allow-origin"):
        raise GuardError("API allowed an unapproved browser origin")
    for name in ["attractions", "booking", "gate", "analytics"]:
        r = httpx.get(url + "/api/" + name + "/health/ready", timeout=15)
        if r.status_code != 200:
            raise ValueError("Cloud API readiness failed: " + name)
    for name in ["booking", "gate", "analytics"]:
        path = {
            "booking": "bookings",
            "gate": "visits",
            "analytics": "admin/analytics",
        }[name]
        if httpx.get(url + "/api/" + name + "/" + path, timeout=10).status_code != 401:
            raise ValueError("Anonymous authorization boundary failed")
    attrs = session.client("sqs").get_queue_attributes(
        QueueUrl=core["dead_queue_url"], AttributeNames=["ApproximateNumberOfMessages"]
    )["Attributes"]
    print(
        "Cloud readiness and anonymous denial verified; approximate DLQ messages:",
        attrs["ApproximateNumberOfMessages"],
    )
    print(
        "Authenticated signup/admin/Stripe/webhook/Metabase/fault evidence still requires the Phase 7 rehearsal; no end-to-end success inferred."
    )


def teardown(session, target):
    connect_cluster(session, target)
    # Edge must already be destroyed; otherwise abort before controller-managed deletion.
    state = tf("edge", "state", "list", capture_output=True).stdout.strip()
    if state:
        raise ValueError("Destroy reviewed edge state before removing its ALB")
    inventory = json.loads((ROOT / "secrets/alb-inventory.json").read_text())
    kube(target, "delete", "ingress", "wonderland", "--wait=true", "--timeout=300s")
    session.client("elbv2").get_waiter("load_balancers_deleted").wait(
        LoadBalancerArns=[inventory["arn"]],
        WaiterConfig={"Delay": 10, "MaxAttempts": 30},
    )
    kube(target, "delete", "namespace", "wonderland", "--wait=true", "--timeout=300s")
    print(
        "Workloads removed and ALB deletion confirmed. Generate/review the core destroy plan next; database protection must be explicitly changed first."
    )


def audit(session, target):
    # Account-wide tagging lookup plus service inventories catches deleted/retained untagged dependents.
    result = {
        "tagged": [],
        "eks": session.client("eks").list_clusters()["clusters"],
        "rds": [],
        "snapshots": [],
        "volumes": [],
        "load_balancers": [],
        "queues": [],
    }
    for page in (
        session.client("resourcegroupstaggingapi")
        .get_paginator("get_resources")
        .paginate(TagFilters=[{"Key": "Project", "Values": ["wonderland"]}])
    ):
        result["tagged"] += page["ResourceTagMappingList"]
    for page in session.client("rds").get_paginator("describe_db_instances").paginate():
        result["rds"] += [
            d["DBInstanceIdentifier"]
            for d in page["DBInstances"]
            if d["DBInstanceIdentifier"].startswith(target["name"])
        ]
    for page in (
        session.client("rds")
        .get_paginator("describe_db_snapshots")
        .paginate(SnapshotType="manual")
    ):
        result["snapshots"] += [
            d["DBSnapshotIdentifier"]
            for d in page["DBSnapshots"]
            if d["DBInstanceIdentifier"].startswith(target["name"])
        ]
    for page in (
        session.client("ec2")
        .get_paginator("describe_volumes")
        .paginate(Filters=[{"Name": "tag:Project", "Values": ["wonderland"]}])
    ):
        result["volumes"] += [v["VolumeId"] for v in page["Volumes"]]
    for page in (
        session.client("elbv2").get_paginator("describe_load_balancers").paginate()
    ):
        result["load_balancers"] += [
            lb["LoadBalancerArn"]
            for lb in page["LoadBalancers"]
            if lb["LoadBalancerName"].startswith(("k8s-wonderla", target["name"]))
        ]
    result["queues"] = (
        session.client("sqs")
        .list_queues(QueueNamePrefix=target["name"])
        .get("QueueUrls", [])
    )
    inventory = ROOT / "secrets/destroyed-demo-inventory.json"
    if inventory.exists():
        previous = json.loads(inventory.read_text())
        if (
            previous["account_id"] != target["account_id"]
            or previous["name"] != target["name"]
        ):
            raise ValueError("Audit inventory belongs to another target")
        vpc = previous["outputs"]["vpc_id"]
        ec2 = session.client("ec2")
        result["network_interfaces"] = [
            e["NetworkInterfaceId"]
            for e in ec2.describe_network_interfaces(
                Filters=[{"Name": "vpc-id", "Values": [vpc]}]
            )["NetworkInterfaces"]
        ]
        result["nat_gateways"] = [
            e["NatGatewayId"]
            for e in ec2.describe_nat_gateways(
                Filter=[{"Name": "vpc-id", "Values": [vpc]}]
            )["NatGateways"]
        ]
        result["vpc_endpoints"] = [
            e["VpcEndpointId"]
            for e in ec2.describe_vpc_endpoints(
                Filters=[{"Name": "vpc-id", "Values": [vpc]}]
            )["VpcEndpoints"]
        ]
        result["vpc_security_groups"] = [
            e["GroupId"]
            for e in ec2.describe_security_groups(
                Filters=[{"Name": "vpc-id", "Values": [vpc]}]
            )["SecurityGroups"]
        ]
    result["remaining_instances"] = [
        {
            "id": i["InstanceId"],
            "state": i["State"]["Name"],
            "public_ipv4": i.get("PublicIpAddress"),
        }
        for page in session.client("ec2")
        .get_paginator("describe_instances")
        .paginate(
            Filters=[
                {"Name": "tag:Project", "Values": ["wonderland"]},
                {
                    "Name": "instance-state-name",
                    "Values": ["pending", "running", "stopping", "stopped"],
                },
            ]
        )
        for r in page["Reservations"]
        for i in r["Instances"]
    ]
    result["public_ipv4_allocations"] = [
        a["AllocationId"]
        for a in session.client("ec2").describe_addresses(
            Filters=[{"Name": "tag:Project", "Values": ["wonderland"]}]
        )["Addresses"]
    ]
    result["persistent_repositories"] = [
        r["repositoryName"]
        for page in session.client("ecr")
        .get_paginator("describe_repositories")
        .paginate()
        for r in page["repositories"]
        if r["repositoryName"].startswith(target["name"] + "/")
    ]
    private_json(ROOT / "secrets/cleanup-audit.json", result)
    print(
        "Audit saved privately; review retained snapshots, KMS pending deletion, secrets, state/ECR/Cognito/Amplify and any remaining tagged resources. No zero-cost claim made."
    )


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=[
            "review",
            "preflight",
            "plan",
            "apply",
            "destroy",
            "publish",
            "controller",
            "deploy",
            "discover",
            "hosting",
            "verify",
            "teardown",
            "audit",
            "migrate-state",
            "update-payment",
        ],
    )
    parser.add_argument(
        "--target", type=Path, default=ROOT / "secrets/cloud-target.json"
    )
    parser.add_argument("--stage", choices=sorted(STAGES), default="demo")
    parser.add_argument("--review-action", default="deploy")
    parser.add_argument("--allow-account-access", action="store_true")
    parser.add_argument("--acknowledge-costs", action="store_true")
    parser.add_argument("--approve-plan")
    parser.add_argument("--approve-action")
    parser.add_argument("--destroy", action="store_true")
    args = parser.parse_args()
    target = target_config(args.target)
    if args.action == "review":
        spec = review_spec(target, args.review_action)
        print(json.dumps(spec, indent=2))
        print("Action SHA-256:", digest(spec))
        return
    path = None
    if args.action in {"apply", "destroy"}:
        path = checked_plan(args, target)
    if args.action in {
        "publish",
        "controller",
        "deploy",
        "hosting",
        "teardown",
        "migrate-state",
        "update-payment",
    }:
        approve_action(args, target)
    session = account_session(args, target)
    if args.action == "preflight":
        eks = session.client("eks").describe_cluster_versions(
            clusterVersions=[target["eks_version"]]
        )["clusterVersions"]
        if not eks or any(
            v.get("versionStatus", v.get("status"))
            not in {"STANDARD_SUPPORT", "standard-support"}
            for v in eks
        ):
            raise ValueError("Select an EKS version in standard support")
        if not session.client("rds").describe_db_engine_versions(
            Engine="postgres", EngineVersion=target["rds_engine_version"]
        )["DBEngineVersions"]:
            raise ValueError("Selected RDS patch is unavailable")
        available = {
            z["ZoneName"]
            for z in session.client("ec2").describe_availability_zones(
                Filters=[{"Name": "state", "Values": ["available"]}]
            )["AvailabilityZones"]
        }
        if not set(target["azs"]).issubset(available):
            raise GuardError("Choose two available AZs in the approved region")
        db_options = session.client("rds").describe_orderable_db_instance_options(
            Engine="postgres",
            EngineVersion=target["rds_engine_version"],
            DBInstanceClass=target.get("db_instance_class", "db.t4g.small"),
        )["OrderableDBInstanceOptions"]
        if not db_options:
            raise GuardError(
                "The selected RDS engine/class combination is not orderable in this region"
            )
        offered = {
            v["Location"]
            for v in session.client("ec2").describe_instance_type_offerings(
                LocationType="availability-zone",
                Filters=[
                    {
                        "Name": "instance-type",
                        "Values": [target.get("node_instance_type", "m7g.large")],
                    },
                    {"Name": "location", "Values": target["azs"]},
                ],
            )["InstanceTypeOfferings"]
        }
        if not set(target["azs"]).issubset(offered):
            raise GuardError(
                "The selected worker type is not offered in both chosen AZs"
            )
        print(
            "Explicit role/account, supported service versions, AZs and instance offerings verified; capacity/quotas/prices still require review."
        )
    elif args.action == "plan":
        plan(args, target)
    elif args.action in {"apply", "destroy"}:
        os.environ.update(cloud_profile(target))
        os.environ["AWS_REGION"] = target["region"]
        if args.action == "destroy" and args.stage == "demo":
            if tf("edge", "state", "list", capture_output=True).stdout.strip():
                raise ValueError("Destroy edge integration first")
            cluster_exists = True
            try:
                connect_cluster(session, target)
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                    raise
                cluster_exists = False
            if (
                cluster_exists
                and kube(
                    target,
                    "get",
                    "namespace",
                    "wonderland",
                    "--ignore-not-found",
                    "-o",
                    "name",
                    capture_output=True,
                ).stdout.strip()
            ):
                raise ValueError(
                    "Run approved workload/ALB teardown before core destruction"
                )
            try:
                db = session.client("rds").describe_db_instances(
                    DBInstanceIdentifier=target["name"]
                )["DBInstances"][0]
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "DBInstanceNotFound":
                    raise
                db = None
            if db and db["DeletionProtection"]:
                raise ValueError("Apply the reviewed database protection update first")
            current = outputs("demo")
            inventory = ROOT / "secrets/destroyed-demo-inventory.json"
            if not current.get("vpc_id") and inventory.exists():
                current = json.loads(inventory.read_text())["outputs"]
            if current.get("vpc_id"):
                if any(
                    lb["VpcId"] == current["vpc_id"]
                    for page in session.client("elbv2")
                    .get_paginator("describe_load_balancers")
                    .paginate()
                    for lb in page["LoadBalancers"]
                ):
                    raise ValueError(
                        "Load balancer still exists in the demo VPC; audit and remove it before core destruction"
                    )
        if args.action == "destroy" and outputs(args.stage):
            private_json(
                ROOT / "secrets" / ("destroyed-" + args.stage + "-inventory.json"),
                {
                    "account_id": target["account_id"],
                    "name": target["name"],
                    "outputs": outputs(args.stage),
                },
            )
        tf(args.stage, "apply", "-input=false", str(path))
    elif args.action == "migrate-state":
        p = ROOT / "infrastructure/terraform/bootstrap/backend_override.tf"
        if p.exists():
            raise ValueError(
                "Bootstrap backend is already configured; inspect state before migration"
            )
        try:
            session.client("s3").head_object(
                Bucket=target["state_bucket"],
                Key=backend(target, "bootstrap")["key"],
                ExpectedBucketOwner=target["account_id"],
            )
        except ClientError as exc:
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
                raise
        else:
            raise ValueError("Remote bootstrap state exists; refusing to overwrite it")
        p.write_text('terraform {\n backend "s3" {}\n}\n')
        config = ROOT / "secrets/bootstrap.backend.json"
        private_json(config, backend(target, "bootstrap"))
        os.environ.update(cloud_profile(target))
        tf(
            "bootstrap",
            "init",
            "-migrate-state",
            "-force-copy",
            "-input=false",
            "-backend-config=" + str(config),
        )
        tf("bootstrap", "state", "list")
    else:
        {
            "publish": publish,
            "controller": controller,
            "deploy": deploy,
            "discover": discover,
            "hosting": hosting,
            "verify": verify,
            "teardown": teardown,
            "audit": audit,
            "update-payment": update_payment,
        }[args.action](session, target)


if __name__ == "__main__":
    try:
        main()
    except GuardError as exc:
        raise SystemExit("Cloud operation refused: " + str(exc)) from None
    except (
        ValueError,
        KeyError,
        FileNotFoundError,
        subprocess.CalledProcessError,
        BotoCoreError,
        ClientError,
        httpx.HTTPError,
    ):
        # Error payloads can contain signed URLs, passwords, SQL and token material.
        raise SystemExit(
            "Cloud operation stopped. Check configuration/explicit authorization and private diagnostics; sensitive details suppressed. No success inferred."
        ) from None
