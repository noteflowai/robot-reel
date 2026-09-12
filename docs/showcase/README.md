# Rebuild the GitHub showcase

The cover uses the VLA, director and Newton demos already published in this
checkout. It does not call a model, render new Blender frames or run physics.

```bash
# From the repository root, with the normal Robot Reel runtime installed:
python scripts/build_readme_showcase.py
python scripts/build_remix_site.py
```

The first command writes the seven-second animated cover, its static fallback,
three scene thumbnails and a source mapping. The second builds the interactive
[Physics → Cinema comparison](../remix.md) and its preview.

The animated cover shows independent recordings at 10 preview frames per
second. Each completed panel holds its final sample. The manifest identifies
every source sample and the input/output hashes. The Newton panel crops the
recorded browser canvas from the existing preview; it uses measured poses.

Both READMEs use GitHub-compatible HTML and Markdown. `<picture>` selects a
static image when the viewer requests reduced motion. Scene cards and links
remain usable without animation. No custom JavaScript or CSS runs in GitHub.

`social.png` is the 1280×640 social preview used by the landing page's Open
Graph tags and uploaded once in the repository settings. It is built from the
Butterfly Lab poster alone:

```bash
python3 scripts/build_social_preview.py
```

Use `--fonts DIRECTORY` with the cover builder if DejaVu fonts are elsewhere.
The comparison preview uses the standard Linux DejaVu Sans installation.
Preserve [the media notice](NOTICE.txt) and the upstream VLA attribution when
sharing these images.
