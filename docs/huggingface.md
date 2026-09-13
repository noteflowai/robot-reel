# Hugging Face: an interactive entry point for Robot Reel

The native Space is **`glayguo/robot-reel`**. It hosts the complete Cloth,
Stress and Butterfly browser experiments and their original evidence.
The remaining project demos are linked from the Space.

The Space uses Hugging Face's **static HTML SDK**. Its visitors replay saved
data; it does not run a model, simulator or GPU service. The Space card names
the actual SmolVLA model and LIBERO asset snapshot used to record the policy
experiment. All upstream media notices travel with the recordings.

## Rebuild locally

From a clean checkout:

```bash
python3 scripts/build_huggingface.py --output artifacts/huggingface-space
node scripts/check_huggingface.cjs artifacts/huggingface-space
python3 -m http.server 8080 --directory artifacts/huggingface-space
```

For an uncommitted local preview, add `--allow-dirty` to the build command.
Preview bundles cannot be published. Choose an empty destination each time.

The builder copies only Git-tracked files from the three lab directories and
explicitly listed public assets. It adapts navigation, refreshes affected
manifests and copied archives, and revalidates the source data before publishing
the output directory. `space-manifest.json` records the source commit, original
input hashes and every output file's hash. Unrelated workspace files, caches,
credentials and model weights are not part of the upload.

The browser check uses a cross-origin iframe with clipboard access denied,
at desktop and mobile widths. It checks native media, source sample links,
figure/JSON download and sample restoration without external runtime requests.
The share controls show a complete link that can be copied or opened separately,
so sharing does not depend on an embedding platform's address bar.

## Publish

Install the isolated publishing dependency and authenticate using the Hub CLI:

```bash
python3 -m pip install -r huggingface/requirements-publish.txt
hf auth login
python3 scripts/publish_huggingface.py \
  --bundle artifacts/huggingface-space --repo-id glayguo/robot-reel
```

Use an account permitted to create and update this Space. Keep access tokens in
the Hub's credential store or an environment secret, never in source files.
The publisher verifies the complete bundle and validates the Space card with
the Hub before creating or modifying a Space. It rejects dirty previews and protects
an existing unrelated Space. Updates use the Hub's parent-commit guard and
remove only obsolete files managed by the previous Robot Reel manifest.

## Automatic updates

The main `Check` workflow builds and tests a Space artifact. After that complete
workflow succeeds, `Hugging Face Space` uploads **those tested bytes**, using the
repository's `HF_TOKEN` Actions secret. Pull requests can build and test but
cannot publish. Obsolete main commits are skipped.

To retry a deployment, run `Hugging Face Space` manually with the successful
`Check` run ID for current main. The artifact must still be available; artifacts
are retained for seven days. Otherwise, rerun `Check` for current main first.

## Promotion and attribution

Use the Space as the direct experience link and GitHub for source, reproduction,
issues and the complete showcase. `huggingface/thumbnail.png` combines original
experiment posters; its source hashes are in `huggingface/thumbnail.json`.
The Space's model and dataset metadata identify recording sources and help
people find the demo in the relevant Hub ecosystem.

Keep the experiment scope visible: 30 policy trials are one controlled task,
not an official LIBERO result; cloth properties are not calibrated real fabric;
the Butterfly sculpture's depth is time. A useful launch asks for missing
telemetry or reproduction feedback rather than implying a new foundation model.

Official references checked on 2026-09-13:

- [Static HTML Spaces](https://huggingface.co/docs/hub/en/spaces-sdks-static)
- [Space configuration and discovery metadata](https://huggingface.co/docs/hub/en/spaces-config-reference)
- [Hub Python API](https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api)
