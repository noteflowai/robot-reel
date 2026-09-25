"""Keep each published page's inline script identical to the template it came from.

The exported replays are single self-contained HTML files, so every published page
under `docs/` carries a verbatim copy of its template's inline script. A change to
a template therefore only reaches the published site when the pages are rebuilt,
and a rebuild needs the original capture bundles with their videos. This module
compares the two directly, and can copy a template's script into the pages that
were built from it, refreshing local offline archives and dependent manifests.

    python -m robot_reel.pages           # report drift
    python -m robot_reel.pages --write   # copy templates into the published pages

The landing page is copied in full. Microduck's single-payload template also
updates markup and styles while preserving its embedded recording verbatim.
Other recorded replays synchronize only scripts; markup still needs a rebuild.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]

# Every docs/**/index.html must appear here; check() fails on an unlisted page so
# a new published page cannot quietly escape the comparison.
PAGES = {
    "docs/index.html": "scripts/landing.html",
    "docs/studio/index.html": "robot_reel/replay.html",
    "docs/microduck/index.html": "robot_reel/replay.html",
    "docs/microduck-lab/index.html": "scripts/microduck_lab.html",
    "docs/braking/index.html": "robot_reel/replay.html",
    "docs/compare/microduck/index.html": "robot_reel/comparison.html",
    "docs/compare/braking/index.html": "robot_reel/comparison.html",
    "docs/vla/index.html": "robot_reel/vla.html",
    "docs/director/index.html": "robot_reel/director.html",
    "docs/newton/index.html": "robot_reel/newton.html",
    "docs/chaos/index.html": "robot_reel/chaos.html",
    "docs/cloth/index.html": "robot_reel/cloth.html",
    "docs/solver-lab/index.html": "robot_reel/solver_lab.html",
    "docs/scene-lab/index.html": "robot_reel/scene_lab.html",
    "docs/libero-plus/index.html": "robot_reel/libero_plus.html",
    "docs/stress/index.html": "robot_reel/stress.html",
    "docs/lerobot/index.html": "robot_reel/lerobot.html",
    "docs/blender/index.html": "scripts/blender_demo.html",
    "docs/remix/index.html": "scripts/remix_demo.html",
    "docs/model-review/index.html": "scripts/model_review.html",
}
OPEN, CLOSE = "<script>\n", "</script>"
STATIC_PAGES = {"docs/index.html", "docs/scene-lab/index.html", "docs/libero-plus/index.html"}
PAYLOAD_PAGES = {
    "docs/solver-lab/index.html": ('<script id="lab-data" type="application/json">', "__LAB_DATA__"),
    "docs/microduck-lab/index.html": ('<script id="lab-data" type="application/json">', "__LAB_DATA__"),
    "docs/model-review/index.html": ('<script id="lab-data" type="application/json">', "__LAB_DATA__"),
}


def recorded_template(page, template, marker, placeholder):
    """Apply a single-payload template without serializing or changing its data."""
    text, source = page.read_text(), template.read_text()
    if text.count(marker) != 1 or source.count(placeholder) != 1:
        raise ValueError(f"{page}: ambiguous recorded payload; rebuild the bundle")
    start = text.index(marker) + len(marker)
    end = text.find(CLOSE, start)
    if end < 0:
        raise ValueError(f"{page}: unterminated recorded payload")
    return source.replace(placeholder, text[start:end])


def inline_script(path):
    """Return (script, start, end) for the one script element without attributes.

    The JSON payload blocks carry attributes, so they are never returned here.
    """
    text = path.read_text()
    if text.count(OPEN) != 1:
        raise ValueError(f"{path}: expected exactly one inline <script> block")
    start = text.index(OPEN) + len(OPEN)
    end = text.index(CLOSE, start)
    return text[start:end], start, end


def published(root=ROOT):
    """Yield (page, template) paths, failing on a page that is not listed."""
    found = sorted(p.relative_to(root).as_posix() for p in (root/"docs").rglob("index.html"))
    unlisted = [name for name in found if name not in PAGES]
    if unlisted:
        raise ValueError(f"Published pages missing from PAGES: {', '.join(unlisted)}")
    for name in found:
        yield root/name, root/PAGES[name]


def check(root=ROOT):
    """Check full supported templates and other recorded replays' inline scripts."""
    drifted = []
    for page, template in published(root):
        if page.relative_to(root).as_posix() in STATIC_PAGES:
            same = page.read_bytes() == template.read_bytes()
        elif page.relative_to(root).as_posix() in PAYLOAD_PAGES:
            same = page.read_text() == recorded_template(
                page, template, *PAYLOAD_PAGES[page.relative_to(root).as_posix()])
        else:
            same = inline_script(page)[0] == inline_script(template)[0]
        if not same:
            drifted.append(page)
    return drifted


HASH_KEYS = ("sha256", "files", "inputs")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_archives(root, changed):
    """Replace archived copies of changed files, preserving unrelated sources.

    A member must match both the sibling path and its previous hash. In particular,
    a source-capture manifest with the same filename is not a copy of the site's
    manifest. Never add members or extract paths supplied by an archive.
    """
    updated = {}
    for path in sorted((root/"docs").rglob("*.zip")):
        with zipfile.ZipFile(path) as source:
            replacements = {}
            for info in source.infolist():
                target = (path.parent/info.filename).resolve()
                if (not info.is_dir() and target.is_relative_to(path.parent.resolve())
                        and target in changed):
                    with source.open(info) as stream:
                        previous = hashlib.file_digest(stream, "sha256").hexdigest()
                    if previous == changed[target]:
                        replacements[info.filename] = target
            if not replacements:
                continue
            if len(source.namelist()) != len(set(source.namelist())):
                raise ValueError(f"{path}: duplicate offline archive members; rebuild the bundle")
            previous = digest(path)
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".zip", delete=False) as stream:
                temporary = Path(stream.name)
            try:
                with zipfile.ZipFile(temporary, "w") as destination:
                    destination.comment = source.comment
                    for info in source.infolist():
                        target = replacements.get(info.filename)
                        with (target.open("rb") if target else source.open(info)) as incoming:
                            with destination.open(copy.copy(info), "w") as outgoing:
                                shutil.copyfileobj(incoming, outgoing)
                temporary.chmod(path.stat().st_mode)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            updated[path.resolve()] = previous
    return updated


def refresh_hashes(root, changed):
    """Refresh manifests and offline copies, following their dependency chain.

    Published bundles hash each other: a comparison manifest records its page, and
    the remix manifest records that comparison manifest. Rewriting one file
    therefore invalidates the manifests above it, so this repeats until nothing is
    left to update. An entry is only rewritten when its recorded hash is the
    changed file's previous hash, which is what keeps the source-capture manifests
    inside a comparison bundle -- they record a different `index.html` -- untouched.
    """
    root = root.resolve()
    manifests = sorted((root/"docs").rglob("*manifest*.json"))
    pending, updated = dict(changed), []
    while pending:
        archive_inputs = dict(pending)
        # Finish the manifest chain before repacking, so the page and its final
        # manifest are copied together instead of recompressing the media twice.
        while pending:
            found = {}
            for path in manifests:
                text = path.read_text()
                document = json.loads(text)
                touched = False
                for key in HASH_KEYS:
                    entry = document.get(key)
                    if not isinstance(entry, dict):
                        continue
                    for name, recorded in entry.items():
                        recorded_hash = recorded.get("sha256") if isinstance(recorded, dict) else recorded
                        # Bundle manifests name siblings; input manifests may
                        # name paths from the docs root or the repository root.
                        for target in ((path.parent/name).resolve(), (root/"docs"/name).resolve(),
                                       (root/name).resolve()):
                            if target in pending and pending[target] == recorded_hash:
                                entry[name] = (
                                    {**recorded, "sha256": digest(target), "bytes": target.stat().st_size}
                                    if isinstance(recorded, dict) else digest(target)
                                )
                                touched = True
                                break
                if touched:
                    found[path] = digest(path)
                    archive_inputs.setdefault(path, found[path])
                    # Both writers use indent=2; only their trailing newline differs.
                    path.write_text(json.dumps(document, indent=2) + ("\n" if text.endswith("\n") else ""))
                    updated.append(path)
            pending = found
        pending = refresh_archives(root, archive_inputs)
        updated.extend(pending)
    return list(dict.fromkeys(updated))


def sync(root=ROOT):
    """Copy the landing page or replay scripts, then refresh archives and hashes."""
    root = root.resolve()
    written, changed = [], {}
    for page in check(root):
        template = root/PAGES[page.relative_to(root).as_posix()]
        changed[page.resolve()] = digest(page)
        if page.relative_to(root).as_posix() in STATIC_PAGES:
            page.write_bytes(template.read_bytes())
        elif page.relative_to(root).as_posix() in PAYLOAD_PAGES:
            page.write_text(recorded_template(
                page, template, *PAYLOAD_PAGES[page.relative_to(root).as_posix()]))
        else:
            script = inline_script(template)[0]
            text = page.read_text()
            _, start, end = inline_script(page)
            page.write_text(text[:start] + script + text[end:])
        written.append(page)
    return written + refresh_hashes(root, changed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true",
                        help="Copy the templates into the published pages")
    args = parser.parse_args(argv)
    args.root = args.root.resolve()
    if args.write:
        written = sync(args.root)
        for path in written:
            print(f"Updated {path.relative_to(args.root)}")
        print(f"{len(written)} files updated.")
        return
    drifted = check(args.root)
    if drifted:
        for page in drifted:
            print(f"{page.relative_to(args.root)} differs from {PAGES[page.relative_to(args.root).as_posix()]}")
        parser.exit(1, f"{len(drifted)} published pages are behind their templates. "
                       "Rebuild them, or run: python -m robot_reel.pages --write\n")
    print(f"{len(PAGES)} published pages match their templates.")


if __name__ == "__main__":
    main()
