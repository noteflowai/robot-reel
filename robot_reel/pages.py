"""Keep each published page's inline script identical to the template it came from.

The exported replays are single self-contained HTML files, so every published page
under `docs/` carries a verbatim copy of its template's inline script. A change to
a template therefore only reaches the published site when the pages are rebuilt,
and a rebuild needs the original capture bundles with their videos. This module
compares the two directly, and can copy a template's script into the pages that
were built from it, refreshing any manifest that records the page's hash.

    python -m robot_reel.pages           # report drift
    python -m robot_reel.pages --write   # copy templates into the published pages

Only the script is synchronized. Anything else -- new markup, new recorded data,
new media -- still requires the documented rebuild for that page.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Every docs/**/index.html must appear here; check() fails on an unlisted page so
# a new published page cannot quietly escape the comparison.
PAGES = {
    "docs/index.html": "scripts/landing.html",
    "docs/studio/index.html": "robot_reel/replay.html",
    "docs/microduck/index.html": "robot_reel/replay.html",
    "docs/braking/index.html": "robot_reel/replay.html",
    "docs/compare/microduck/index.html": "robot_reel/comparison.html",
    "docs/compare/braking/index.html": "robot_reel/comparison.html",
    "docs/vla/index.html": "robot_reel/vla.html",
    "docs/director/index.html": "robot_reel/director.html",
    "docs/newton/index.html": "robot_reel/newton.html",
    "docs/chaos/index.html": "robot_reel/chaos.html",
    "docs/stress/index.html": "robot_reel/stress.html",
    "docs/blender/index.html": "scripts/blender_demo.html",
    "docs/remix/index.html": "scripts/remix_demo.html",
}
OPEN, CLOSE = "<script>\n", "</script>"


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
    """Return the published pages whose inline script differs from its template."""
    return [page for page, template in published(root)
            if inline_script(page)[0] != inline_script(template)[0]]


HASH_KEYS = ("sha256", "files", "inputs")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_hashes(root, changed):
    """Re-record the hashes of changed files, following the manifest chain.

    Published bundles hash each other: a comparison manifest records its page, and
    the remix manifest records that comparison manifest. Rewriting one file
    therefore invalidates the manifests above it, so this repeats until nothing is
    left to update. An entry is only rewritten when its recorded hash is the
    changed file's previous hash, which is what keeps the source-capture manifests
    inside a comparison bundle -- they record a different `index.html` -- untouched.
    """
    manifests = sorted((root/"docs").rglob("*manifest*.json"))
    pending, updated = dict(changed), []
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
                    # Bundle manifests name siblings; the remix manifest names its
                    # inputs from the docs root.
                    for target in ((path.parent/name).resolve(), (root/"docs"/name).resolve()):
                        if pending.get(target) == recorded:
                            entry[name] = digest(target)
                            touched = True
                            break
            if touched:
                found[path.resolve()] = digest(path)
                # Both writers use indent=2; only their trailing newline differs.
                path.write_text(json.dumps(document, indent=2) + ("\n" if text.endswith("\n") else ""))
                updated.append(path)
        pending = found
    return updated


def sync(root=ROOT):
    """Copy each template's inline script into its published pages."""
    written, changed = [], {}
    for page in check(root):
        template = root/PAGES[page.relative_to(root).as_posix()]
        script = inline_script(template)[0]
        text = page.read_text()
        _, start, end = inline_script(page)
        changed[page.resolve()] = digest(page)
        page.write_text(text[:start] + script + text[end:])
        written.append(page)
    return written + refresh_hashes(root, changed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true",
                        help="Copy the templates into the published pages")
    args = parser.parse_args(argv)
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
