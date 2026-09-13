"""Read back a public Space's uploaded objects and served pages against its CI bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_huggingface import LABS, MANIFEST, verify

# The static host inserts this single platform-owned variable immediately after
# <head>. Match its complete non-executable value, not arbitrary script contents.
CREATOR_VARIABLE = re.compile(
    rb'(?<=<head>)<script>window\.huggingface=\{variables:'
    rb'\{"SPACE_CREATOR_USER_ID":"[0-9a-f]{24}"\}\};</script>'
)


def served_bytes(name, body):
    return CREATOR_VARIABLE.sub(b"", body, count=1) if name.endswith(".html") else body


def verify_objects(directory, record, entries):
    """Check Git blob IDs and LFS SHA-256 IDs; leave unrelated remote files alone."""
    directory = Path(directory)
    files = {}
    for entry in entries:
        if not hasattr(entry, "blob_id"):  # Hub tree listings also contain directories.
            continue
        if entry.path in files:
            raise ValueError(f"Duplicate Hub object: {entry.path}")
        files[entry.path] = entry
    expected = set(record["files"]) | {MANIFEST}
    missing = expected - set(files)
    if missing:
        raise ValueError("Missing uploaded files: " + ", ".join(sorted(missing)))
    for name in sorted(expected):
        data, item = (directory/name).read_bytes(), files[name]
        if item.size != len(data):
            raise ValueError(f"Uploaded size differs: {name}")
        if item.lfs:
            actual = item.lfs.sha256
            wanted = hashlib.sha256(data).hexdigest()
        else:
            actual = item.blob_id
            wanted = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data,
                                  usedforsecurity=False).hexdigest()
        if actual != wanted:
            raise ValueError(f"Uploaded content differs: {name}")
    return {"verified_files": len(expected), "unmanaged_files": sorted(set(files)-expected)}


def verify_live(directory, host, *, timeout=120):
    """Wait for the public CDN to serve the exact manifest, viewers and thumbnail."""
    url = urlsplit(host)
    if (url.scheme != "https" or not (url.hostname or "").endswith(".hf.space")
            or url.username or url.password or url.port or url.query or url.fragment
            or url.path not in ("", "/")):
        raise ValueError("Expected the public HTTPS app host returned by the Hub")
    if not 0 < timeout <= 300:
        raise ValueError("Live verification timeout must be between 0 and 300 seconds")
    directory = Path(directory)
    names = [MANIFEST, "index.html", *(f"{lab}/index.html" for lab in LABS), "thumbnail.png"]
    pending = {name: (directory/name).read_bytes() for name in names}
    deadline = time.monotonic() + timeout
    reasons = {}
    while pending:
        for name in list(pending):
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                break
            request = Request(host.rstrip("/")+"/"+name, headers={"Cache-Control": "no-cache"})
            try:
                with urlopen(request, timeout=min(10, remaining)) as response:
                    # Bound a malformed or unexpected response to the expected file size.
                    body = response.read(len(pending[name])+257)
                if served_bytes(name, body) == pending[name]:
                    del pending[name]
                    reasons.pop(name, None)
                else:
                    reasons[name] = "served bytes differ from the tested artifact"
            except HTTPError as exc:
                if exc.code not in (404, 408, 429, 500, 502, 503, 504):
                    raise ValueError(f"Public Space returned HTTP {exc.code}: {name}") from exc
                reasons[name] = f"HTTP {exc.code}"
            except (URLError, TimeoutError) as exc:
                reasons[name] = type(exc).__name__
        if not pending:
            return names
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            details = "; ".join(f"{name}: {reasons.get(name, 'deadline reached')}" for name in pending)
            raise ValueError("Public Space did not serve the tested artifact before the deadline: " + details)
        time.sleep(min(5, remaining))


def verify_publication(directory, repo_id, *, revision=None, timeout=120):
    directory = Path(directory)
    record = verify(directory)
    if record["source_dirty"]:
        raise ValueError("A dirty preview cannot identify a published source commit")
    from huggingface_hub import HfApi

    # This is a public visitor check. Never send the publisher's credential.
    api = HfApi(token=False)
    info = api.space_info(repo_id)
    if info.private or info.sdk != "static":
        raise ValueError("Expected a public static Space")
    revision = revision or info.sha
    if info.sha != revision:
        raise ValueError("Space head differs from the uploaded commit")
    result = verify_objects(directory, record, api.list_repo_tree(
        repo_id, repo_type="space", revision=revision, recursive=True))
    result["live_files"] = verify_live(directory, info.host, timeout=timeout)
    current = api.space_info(repo_id)
    if current.sha != revision:
        raise ValueError("Space changed during readback; verify its current artifact separately")
    if not current.runtime or current.runtime.stage != "RUNNING":
        raise ValueError("Space is not running after public readback")
    return {**result, "repo_id": repo_id, "source_commit": record["source_commit"],
            "hub_commit": revision, "public_app_url": info.host, "anonymous_readback": True,
            "html_normalization": "Only the Hub's injected SPACE_CREATOR_USER_ID assignment"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--repo-id", default="glayguo/robot-reel")
    parser.add_argument("--revision", help="Expected Hub commit returned by the upload")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    print(json.dumps(verify_publication(args.bundle, args.repo_id, revision=args.revision,
                                      timeout=args.timeout), indent=2))
