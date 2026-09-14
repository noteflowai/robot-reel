"""Upload missing draft assets, checking every byte hash before publication.

This helper never overwrites assets or publishes a release. It can resume an
interrupted upload when given the original tested artifact directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import quote


def inventory(folder):
    folder = Path(folder)
    paths = list(folder.iterdir())
    if not 1 <= len(paths) <= 64:
        raise ValueError("Expected a bounded release asset directory")
    files = {}
    for path in paths:
        if (path.is_symlink() or not path.is_file()
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", path.name)):
            raise ValueError("Release assets must be regular, safely named files")
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        files[path.name] = {"size": path.stat().st_size, "digest": "sha256:" + checksum}
    sums = {}
    for line in (folder/"SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9_.-]*)", line)
        if not match or match[2] in sums:
            raise ValueError("Malformed or duplicate checksum entry")
        sums[match[2]] = "sha256:" + match[1]
    if sums != {name: item["digest"] for name, item in files.items() if name != "SHA256SUMS"}:
        raise ValueError("Checksums do not match the complete local inventory")
    return files


class GitHub:
    def __init__(self, repo, tag, source):
        self.repo, self.tag = repo, tag
        sha = self.json("api", f"repos/{repo}/commits/{quote(tag, safe='')}")["sha"]
        if sha != source:
            raise ValueError("Release tag does not match the tested source commit")
        release = self.json("release", "view", tag, "--repo", repo,
                            "--json", "databaseId,isDraft,tagName")
        if not release["isDraft"] or release["tagName"] != tag:
            raise ValueError("Only an existing draft can receive assets; preserve public releases")
        self.release_id = release["databaseId"]

    @staticmethod
    def json(*args):
        return json.loads(subprocess.check_output(["gh", *args], text=True, timeout=60))

    def state(self):
        return self.json("api", f"repos/{self.repo}/releases/{self.release_id}")

    def upload(self, path):
        try:
            result = subprocess.run(
                ["gh", "release", "upload", self.tag, str(path), "--repo", self.repo],
                capture_output=True, text=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            return False
        # Re-read the server even after a lost response: the upload may have succeeded.
        return result.returncode == 0


def checked_remote(api, expected):
    release = api.state()
    if not release["draft"] or release["tag_name"] != api.tag:
        raise ValueError("Draft state changed; stop without altering it")
    found = set()
    for item in release["assets"]:
        name = item["name"]
        if name in found or name not in expected:
            raise ValueError("Unexpected or duplicate remote release asset")
        wanted = expected[name]
        if (item["state"] != "uploaded" or item["size"] != wanted["size"]
                or item.get("digest") != wanted["digest"]):
            raise ValueError(f"Existing remote asset differs; preserve it: {name}")
        found.add(name)
    return found


def upload(folder, api, *, sleep=time.sleep):
    folder = Path(folder)
    expected = inventory(folder)
    # Validate every existing asset before making any upload.
    found = checked_remote(api, expected)
    added = []
    for name in sorted(expected.keys() - found):
        for attempt in range(3):
            # A changed local input must not be uploaded under an earlier checksum.
            if inventory(folder) != expected:
                raise ValueError("Local release files changed during upload")
            found = checked_remote(api, expected)
            if name in found:
                break
            api.upload(folder/name)
            found = checked_remote(api, expected)
            if name in found:
                added.append(name)
                break
            if attempt < 2:
                sleep(2 ** attempt)
        else:
            raise RuntimeError(f"Upload incomplete after three attempts; draft preserved: {name}")
    found = checked_remote(api, expected)
    if found != expected.keys():
        raise ValueError("Draft does not contain every tested asset")
    return {"verified": True, "draft": True, "files": len(found), "uploaded": added,
            "unchanged": sorted(found - set(added))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--assets", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        parser.error("Expected owner/repository")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", args.tag):
        parser.error("Expected a version release tag")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        parser.error("Expected the full tested source commit")
    inventory(args.assets)
    print(json.dumps(upload(args.assets, GitHub(args.repo, args.tag, args.source_commit)), indent=2))
