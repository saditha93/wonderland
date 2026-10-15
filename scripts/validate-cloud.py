"""Public provider downloads + offline schema/mock tests; no AWS credentials/API."""

from pathlib import Path
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
binary = shutil.which("terraform") or str(ROOT / "tmp/tools/terraform")
cache = ROOT / "tmp/terraform-provider-cache"
cache.mkdir(exist_ok=True, parents=True)
env = {
    k: v
    for k, v in os.environ.items()
    if not k.startswith("AWS_")
    and k not in {"TF_CLI_ARGS", "TF_CLI_ARGS_init", "TF_CLI_ARGS_test"}
}
env.update(
    AWS_EC2_METADATA_DISABLED="true",
    TF_PLUGIN_CACHE_DIR=str(cache),
    TF_IN_AUTOMATION="true",
)
subprocess.run(
    [binary, "fmt", "-check", "-recursive", "infrastructure/terraform"],
    cwd=ROOT,
    env=env,
    check=True,
)
for stage in ["bootstrap", "persistent", "demo", "edge", "simple"]:
    prefix = [binary, "-chdir=" + str(ROOT / "infrastructure/terraform" / stage)]
    for args in [
        ["init", "-backend=false", "-input=false", "-no-color"],
        ["validate", "-no-color"],
        ["test", "-no-color"],
    ]:
        subprocess.run(prefix + args, cwd=ROOT, env=env, check=True)
print(
    "All five Terraform roots validated and mocked plans passed. No live AWS plan/apply was run."
)
