"""Parallel uploads must preserve Docker's ordered layers and fail closed."""

import gzip
import hashlib
import io
import json
import tarfile
import threading
from types import SimpleNamespace
import pytest
from scripts.advanced.registry_upload import publish


def archive(tmp_path):
    image = "example/repo:demo"
    entries = {
        "config.json": json.dumps({"architecture": "amd64", "os": "linux"}).encode(),
        "first.tar": b"first layer",
        "second.tar": b"second layer",
    }
    entries["manifest.json"] = json.dumps(
        [
            {
                "Config": "config.json",
                "RepoTags": [image],
                "Layers": ["first.tar", "second.tar"],
            }
        ]
    ).encode()
    path = tmp_path / "image.tar"
    with tarfile.open(path, "w") as t:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return path, image


def test_reversed_upload_completion_keeps_manifest_layer_order(tmp_path):
    path, image = archive(tmp_path)
    second = threading.Event()
    captured = []
    digests = [
        "sha256:" + hashlib.sha256(gzip.compress(x, mtime=0)).hexdigest()
        for x in [b"first layer", b"second layer"]
    ]

    def available(**kw):
        digest = kw["layerDigests"][0]
        if digest == digests[0]:
            assert second.wait(3)
        if digest == digests[1]:
            second.set()
        return {"layers": [{"layerAvailability": "AVAILABLE"}]}

    def put(**kw):
        captured.append(json.loads(kw["imageManifest"]))
        return {"image": {"imageId": {"imageDigest": "published"}}}

    publish(
        SimpleNamespace(batch_check_layer_availability=available, put_image=put),
        path,
        "repo",
        "demo",
        image,
        "amd64",
    )
    assert [x["digest"] for x in captured[0]["layers"]] == digests


def test_layer_failure_never_publishes_manifest(tmp_path):
    path, image = archive(tmp_path)
    calls = []

    def available(**kw):
        calls.append(kw)
        if len(calls) > 1:
            raise RuntimeError("ECR unavailable")
        return {"layers": [{"layerAvailability": "AVAILABLE"}]}

    client = SimpleNamespace(
        batch_check_layer_availability=available,
        put_image=lambda **kw: pytest.fail("Incomplete image published"),
    )
    with pytest.raises(RuntimeError, match="ECR unavailable"):
        publish(client, path, "repo", "demo", image, "amd64")
