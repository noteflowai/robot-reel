"""Every relative link in the Markdown docs and the landing page must resolve.

The READMEs, `docs/*.md` and `notes/` link to files, pages and headings in this
checkout. A moved file or a renamed heading silently breaks those links on
GitHub, so this walks all of them with the standard library. External URLs are
not fetched; the browser tests cover the published pages' own links.
"""
import html
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "node_modules", "artifacts", ".venv", ".venv-vla", ".venv-vla-gpu", ".venv-rerun", "build", "dist"}
LINK = re.compile(r"\]\(([^)\s]+)\)|\b(?:href|src|srcset)=\"([^\"]+)\"")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*$", re.MULTILINE)
INLINE_TAG = re.compile(r"<[^>]+>")
NOT_SLUG = re.compile(r"[^\w\- ]", re.UNICODE)


def markdown_files():
    return sorted(p for p in ROOT.rglob("*.md") if not SKIP & set(p.relative_to(ROOT).parts))


def anchors(path):
    """GitHub-style heading slugs: lowercase, punctuation dropped, spaces to dashes."""
    text = path.read_text()
    found = set()
    for match in HEADING.finditer(text):
        title = html.unescape(INLINE_TAG.sub("", match.group(1))).strip().lower()
        found.add(NOT_SLUG.sub("", title).replace(" ", "-"))
    found.update(re.findall(r"\bid=\"([^\"]+)\"", text))
    return found


def links(path):
    for match in LINK.finditer(path.read_text()):
        url = next(group for group in match.groups() if group)
        if url.startswith(("http://", "https://", "mailto:")):
            continue
        yield url


class RelativeLinkTest(unittest.TestCase):
    def check(self, source, url, cache):
        target, _, fragment = url.partition("#")
        path = source if not target else (source.parent/target).resolve()
        self.assertTrue(path.exists(), f"{source.relative_to(ROOT)} links to missing {url}")
        if fragment and path.suffix == ".md":
            if path not in cache:
                cache[path] = anchors(path)
            self.assertIn(fragment, cache[path],
                          f"{source.relative_to(ROOT)} links to missing heading {url}")

    def test_markdown_links_resolve(self):
        cache = {}
        for path in markdown_files():
            for url in links(path):
                self.check(path, url, cache)

    def test_landing_page_links_resolve(self):
        page = ROOT/"docs/index.html"
        for url in links(page):
            target, _, _ = url.partition("#")
            if not target:
                continue
            path = page.parent/target
            self.assertTrue(path.exists() or (path/"index.html").exists(),
                            f"docs/index.html links to missing {url}")

    def test_scan_covers_the_readmes(self):
        names = {p.relative_to(ROOT).as_posix() for p in markdown_files()}
        self.assertLessEqual({"README.md", "README.zh-CN.md", "CONTRIBUTING.md"}, names)
