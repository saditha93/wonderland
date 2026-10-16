"""Create a source-only handover archive without credentials/private data."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {
    "secrets",
    "tmp",
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "dist-admin",
    ".terraform",
    "__pycache__",
    ".pytest_cache",
}
SOURCE_SUFFIXES = {
    ".py",
    ".tsx",
    ".ts",
    ".css",
    ".html",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".tf",
    ".hcl",
    ".sh",
    ".toml",
    ".lock",
    ".mmd",
    ".example",
}


def allowed(path):
    path = Path(path)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and not any(part in FORBIDDEN for part in path.parts)
        and not str(path).startswith("docs/course-materials/")
        and not (path.name.startswith(".env") and path.name != ".env.example")
        and ".tfstate" not in path.name
        and not path.name.endswith((".tfvars", ".tfplan"))
        and (
            path.suffix in SOURCE_SUFFIXES
            or path.suffix == ".txt"
            and str(path).startswith("docs/evidence/")
            or path.name.startswith("Dockerfile")
            or path.name in {".gitignore", ".dockerignore"}
        )
    )


def source_files(root):
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if top.returncode == 0 and Path(top.stdout.strip()).resolve() == root.resolve():
            listed = subprocess.run(
                ["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"],
                cwd=root,
                capture_output=True,
            )
            if listed.returncode == 0:
                return sorted(set(p.decode() for p in listed.stdout.split(b"\0") if p))
    except FileNotFoundError:
        pass
    # Source ZIPs intentionally omit .git. Keep the commands usable after unzip;
    # prune private/generated directories before traversing large dependencies.
    result = []
    for directory, children, filenames in os.walk(root, followlinks=False):
        children[:] = [
            d
            for d in children
            if d not in FORBIDDEN
            and not (Path(directory) / d).is_symlink()
            and (Path(directory) / d).relative_to(root).as_posix()
            != "docs/course-materials"
        ]
        result.extend(
            (Path(directory) / name).relative_to(root).as_posix() for name in filenames
        )
    return sorted(result)


def validate_text(data, path):
    content = data.decode("utf-8")
    if re.search(r"^-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", content, re.M):
        raise RuntimeError(f"Private key material found; packaging refused: {path}")
    if re.search(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bsk_live_[A-Za-z0-9]{20,}", content):
        raise RuntimeError(f"Credential-like value found; packaging refused: {path}")


def create_package():
    files = source_files(ROOT)
    directory = ROOT / "tmp/handover"
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "wonderland-source.zip"
    temporary = archive.with_suffix(".zip.partial")
    manifest = {
        "scope": "Source and public documentation only; no credentials, databases, dependencies or private course PDFs",
        "files": [],
    }
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as bundle:
            for relative in files:
                path = ROOT / relative
                if not allowed(relative) or path.is_symlink() or not path.is_file():
                    continue
                data = path.read_bytes()
                validate_text(data, relative)
                bundle.write(path, "wonderland/" + relative)
                manifest["files"].append(
                    {"path": relative, "sha256": hashlib.sha256(data).hexdigest()}
                )
            bundle.writestr(
                "wonderland/HANDOVER-MANIFEST.json",
                json.dumps(manifest, indent=2) + "\n",
            )
        with ZipFile(temporary) as bundle:
            assert bundle.testzip() is None
            assert all(
                allowed(n.removeprefix("wonderland/")) for n in bundle.namelist()
            )
            assert "wonderland/start.sh" in bundle.namelist()
            assert "wonderland/docs/assignment/report.md" in bundle.namelist()
        temporary.replace(archive)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n")
        print(
            f"Handover ready: {archive.relative_to(ROOT)} ({len(manifest['files'])} source/document files)"
        )
        print(
            "Includes the report, short demo guide, code and optional infrastructure. Private data excluded."
        )
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    create_package()
