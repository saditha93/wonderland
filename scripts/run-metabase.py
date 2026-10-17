"""Run pinned OSS Metabase locally; H2 metadata is development-only.

Download https://downloads.metabase.com/v0.58.35/metabase.jar to
 tmp/metabase/metabase.jar first. No database passwords are passed as CLI args.
"""

import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT / "tmp/metabase"
jar = directory / "metabase.jar"
if not jar.exists():
    raise SystemExit(
        "Download the pinned v0.58.35 JAR described in docs/demo.md#optional-laptop-demonstration first"
    )
directory.mkdir(exist_ok=True, parents=True)
env = {
    **os.environ,
    "MB_JETTY_HOST": "127.0.0.1",
    "MB_JETTY_PORT": "3000",
    "MB_DB_FILE": str(directory / "metadata"),
    "MB_ANON_TRACKING_ENABLED": "false",
    "MB_CHECK_FOR_UPDATES": "false",
    "MB_SITE_URL": "http://localhost:3000",
}
raise SystemExit(
    subprocess.call(
        [
            "java",
            "-Xmx768m",
            "--add-opens",
            "java.base/java.nio=ALL-UNNAMED",
            "-jar",
            str(jar),
        ],
        cwd=directory,
        env=env,
    )
)
