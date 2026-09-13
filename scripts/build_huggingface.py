"""Build a bounded, verified static Space from the three recorded labs."""
from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.pages import digest, refresh_hashes
from robot_reel.stress_site import verify_site as verify_stress
from scripts.build_cloth_showcase import verify_showcase as verify_cloth
from scripts.build_chaos_showcase import verify_showcase as verify_chaos

LABS = ("cloth", "stress", "chaos")
SOURCE = "https://github.com/noteflowai/robot-reel"
SITE = "https://noteflowai.github.io/robot-reel/"
SCHEMA = "robot-reel-space-1"
MANIFEST = "space-manifest.json"


def _safe_file(root, relative):
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
        raise ValueError(f"Symlink is not a publishable file: {relative}")
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Missing or unsafe publishable file: {relative}")
    return path


class Navigation(HTMLParser):
    """Adapt only anchor start tags; leave embedded records and scripts intact."""
    def __init__(self, text, lab, site):
        super().__init__(convert_charrefs=False)
        self.text, self.lab, self.site = text, lab, site
        self.offsets, self.changes = [0], []
        for line in text.splitlines(keepends=True):
            self.offsets.append(self.offsets[-1] + len(line))

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if not href or href.startswith("#"):
            return
        url = urlsplit(href)
        canonical = href.startswith(SITE)
        relative = canonical or not url.scheme and not url.netloc
        if relative:
            path = (url.path[len("/robot-reel/"):] if canonical
                    else posixpath.normpath(posixpath.join(self.lab, url.path)))
            target = self.site/path
            if target.exists() and target.resolve().is_relative_to(self.site):
                path = posixpath.relpath(path or ".", self.lab)
                if target.is_dir():
                    path = path.rstrip("/") + "/"
                attributes["href"] = urlunsplit(("", "", path, url.query, url.fragment))
            else:
                if path.startswith("../") or path.startswith("/"):
                    raise ValueError("Navigation escapes the known website")
                attributes["href"] = urlunsplit(("https", "noteflowai.github.io",
                                                  "/robot-reel/"+path, url.query, url.fragment))
        if attributes["href"].startswith(("https://", "http://")):
            attributes["target"] = "_blank"
            attributes["rel"] = "noopener noreferrer"
        replacement = "<a" + "".join(
            " "+key if value is None else f' {key}="{html.escape(value, quote=True)}"'
            for key, value in attributes.items()) + ">"
        raw = self.get_starttag_text()
        if replacement != raw:
            line, column = self.getpos()
            start = self.offsets[line-1] + column
            self.changes.append((start, start+len(raw), replacement))

    def rewrite(self):
        self.feed(self.text)
        result = self.text
        for start, end, value in reversed(self.changes):
            result = result[:start] + value + result[end:]
        return result


def verify(directory):
    directory = Path(directory).resolve()
    record = json.loads((directory/MANIFEST).read_text())
    if (record.get("schema") != SCHEMA or record.get("source_repository") != SOURCE
            or not re.fullmatch(r"[0-9a-f]{40}", record.get("source_commit", ""))
            or type(record.get("source_dirty")) is not bool):
        raise ValueError("Invalid Space source identity")
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if any(p.is_symlink() for p in directory.rglob("*")):
        raise ValueError("Space contains a symlink")
    expected = record.get("files", {})
    if actual != set(expected) | {MANIFEST}:
        raise ValueError("Space file inventory differs from its manifest")
    for name, metadata in expected.items():
        path = _safe_file(directory, name)
        if path.stat().st_size != metadata["bytes"] or digest(path) != metadata["sha256"]:
            raise ValueError(f"Changed Space file: {name}")
    cloth, stress = verify_cloth(directory/"cloth"), verify_stress(directory/"stress")
    verify_chaos(directory/"chaos")  # Includes the fixed twelve-world source contract.
    if cloth["vertex_samples"] != 42471 or stress["completed_trials"] != 30:
        raise ValueError("Space evidence counts differ from the advertised experiments")
    return record


def build(destination, *, root=ROOT, allow_dirty=False):
    root, destination = Path(root).resolve(), Path(destination).absolute()
    if any(p.is_symlink() for p in (destination, *destination.parents)):
        raise ValueError("Choose a destination without symlinks")
    if destination == root or root.is_relative_to(destination) or any(
        destination.is_relative_to(root/name) for name in ("docs", "robot_reel", "huggingface", "scripts", "tests")
    ):
        raise ValueError("Destination overlaps source files")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("Choose an empty Space destination")
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True))
    if dirty and not allow_dirty:
        raise ValueError("Commit source changes before publishing; use --allow-dirty for a local preview")
    tracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z", *(f"docs/{lab}" for lab in LABS)]
    ).decode().split("\0")
    inputs = {name: name.removeprefix("docs/") for name in tracked if name}
    inputs.update({
        "huggingface/index.html": "index.html", "huggingface/README.md": "README.md",
        "huggingface/space.gitattributes": ".gitattributes", "huggingface/thumbnail.png": "thumbnail.png",
        "LICENSE": "LICENSE", "docs/showcase/butterfly-preview.mp4": "assets/butterfly-preview.mp4",
    })
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".robot-reel-space-", dir=destination.parent) as temporary:
        stage = Path(temporary)/"docs"
        source_files = {}
        for original, target in inputs.items():
            source = _safe_file(root, original)
            if target == "index.html" and not source.read_bytes().isascii():
                raise ValueError("Use HTML entities for Space landing symbols to preserve static-host delivery")
            path = stage/target
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, path)
            source_files[original] = digest(source)
        changed = {}
        for lab in LABS:
            page = stage/lab/"index.html"
            changed[page] = digest(page)
            page.write_text(Navigation(page.read_text(), lab, stage).rewrite())
        refresh_hashes(Path(temporary), changed)
        files = {p.relative_to(stage).as_posix(): {"bytes": p.stat().st_size, "sha256": digest(p)}
                 for p in sorted(stage.rglob("*")) if p.is_file()}
        record = {"schema": SCHEMA, "source_repository": SOURCE, "source_commit": revision,
                  "source_dirty": dirty, "source_files": source_files, "files": files}
        (stage/MANIFEST).write_text(json.dumps(record, indent=2)+"\n")
        verify(stage)
        if destination.exists():
            destination.rmdir()
        stage.rename(destination)
    return {"source_commit": revision, "source_dirty": dirty, "files": len(files),
            "bytes": sum(p["bytes"] for p in files.values()), "destination": str(destination)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"artifacts/huggingface-space")
    parser.add_argument("--allow-dirty", action="store_true", help="Build a local preview that cannot be published")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = verify(args.output) if args.verify else build(args.output, allow_dirty=args.allow_dirty)
    print(json.dumps(result, indent=2))
