"""Build and upload public portals on the AWS node; suppress signed URLs."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile
import boto3


def main():
    os.umask(0o077)
    config = json.loads(
        Path("/opt/wonderland/build-source/build-config.json").read_text()
    )
    deployment_details = config["deployment"]
    target_settings = config["target"]
    aws = boto3.Session(region_name=target_settings["region"])
    runtime = json.loads(
        aws.client("secretsmanager").get_secret_value(
            SecretId=deployment_details["runtime_secret_arn"]
        )["SecretString"]
    )
    jobs = runtime["build_hosting_jobs"]
    root = Path("/opt/wonderland/build-source/frontend")
    env = {
        "VITE_AUTH_MODE": "cognito",
        "VITE_COGNITO_USER_POOL_ID": deployment_details["pool_id"],
        "VITE_COGNITO_USER_POOL_CLIENT_ID": deployment_details["client_id"],
        "VITE_API_BASE_URL": deployment_details["api_url"],
        "VITE_METABASE_URL": "",
        "VITE_DEMO_MODE": "false",
    }
    args = [
        "docker",
        "run",
        "--rm",
        "--network=host",
        "-v",
        str(root) + ":/app",
        "-w",
        "/app",
    ]
    for key, value in env.items():
        args += ["-e", key + "=" + value]
    subprocess.run(
        args + ["node:22-alpine", "sh", "-ec", "npm ci && npm run build"], check=True
    )
    for name, job in jobs.items():
        folder = root / ("dist-admin" if name == "admin" else "dist")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for f in folder.rglob("*"):
                if f.is_file():
                    z.write(f, str(f.relative_to(folder)))
        request = urllib.request.Request(
            job["zipUploadUrl"], data=archive.getvalue(), method="PUT"
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            if response.status >= 400:
                raise ValueError("Portal upload failed")
        print("Uploaded server-built portal:", name)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit("Server portal build/upload failed; private signed URLs suppressed.")
