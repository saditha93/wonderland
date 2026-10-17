"""Check local Markdown file links without network access or private-file reads."""

from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]


def missing_links():
    documents = [ROOT / "README.md"]
    for folder in (
        "docs",
        "infrastructure",
        "scripts",
        "services",
        "analytics",
        ".github",
    ):
        documents.extend((ROOT / folder).rglob("*.md"))
    for document in documents:
        if "course-materials" in document.parts:
            continue
        content = re.sub(r"```.*?```", "", document.read_text(), flags=re.S)
        for target in re.findall(r"\]\(([^)]+)\)", content):
            target = target.split("#", 1)[0]
            if not target or re.match(r"\w+:", target) or target.startswith("/"):
                continue
            if not (document.parent / unquote(target)).exists():
                yield f"{document.relative_to(ROOT)} → {target}"


if __name__ == "__main__":
    errors = list(missing_links())
    if errors:
        raise SystemExit("Missing document links:\n" + "\n".join(errors))
    print("Documentation links passed.")
