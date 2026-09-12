# Physics → Cinema

[Open the interactive comparison](https://noteflowai.github.io/robot-reel/remix/).
Drag the divider, switch to either complete view, jump to the first recorded
contact, or step through both videos on the shared source timeline.

The original view is the published early/late MuJoCo braking comparison.
The second view is its published Blender replay. Both contain the same 180
source samples at 30 fps. The views use different camera projections and scene
styling; the divider does not imply spatial registration of the images.

The builder verifies the original comparison, the Blender source bundle and
its native check report. It then compares every exported frame and outcome
with the original traces before publishing the page. The film does not run
new physics. All 360 vehicle samples were checked in the saved Blender project.

```bash
# Rebuild the page and preview from the media already in this checkout.
# Uses the normal Robot Reel runtime; DejaVu Sans is used for preview captions.
python scripts/build_remix_site.py

# Verify source agreement and the published page using only the standard library.
python3 -S scripts/build_remix_site.py --verify
```

The page references the existing `docs/compare/braking/` and `docs/blender/`
media instead of duplicating the videos. Keep those directories with
`docs/remix/` to use it locally. Download the native project from the page or
continue to the [MCP director](director.md) to create a new storyboard.

The README preview samples both 30 fps videos at 10 Hz and moves the divider.
Its source timestamps remain visible. The full browser replay retains every
source sample. Checksums and source paths are listed in `remix/manifest.json`.
