#!/usr/bin/env bash
# Run with the same Docker access used to build the supplied image.
set -euo pipefail
image="${1:?usage: check_container.sh IMAGE}"
container_output="$(mktemp -d)"
trap 'rm -rf -- "$container_output"' EXIT

# Check the shipped entry command and the default user's writable output.
docker run --rm "$image"
docker run --rm "$image" python -c \
  'import os, pathlib; assert os.getuid() != 0; pathlib.Path("/app/artifacts/check").write_text("ok")'
# A deliberately different UID catches images that only work as UID 1000.
chmod 0777 "$container_output"
docker run --rm --user 12345:12345 \
  --mount "type=bind,src=$container_output,dst=/app/artifacts" \
  "$image" robot-reel direct docs/compare/braking \
  --plan examples/contact-storyboard.json --output artifacts/director
# The export directory intentionally retains the creating user's permissions.
docker run --rm --user 12345:12345 \
  --mount "type=bind,src=$container_output,dst=/data,readonly" \
  "$image" python -c \
  'import pathlib; files = [p for p in pathlib.Path("/data/director").rglob("*") if p.is_file()]; assert files; assert all(p.stat().st_uid == 12345 and p.stat().st_gid == 12345 for p in files)'
# The creating UID removes its output, including directories that another
# unprivileged host user could not unlink recursively.
docker run --rm --user 12345:12345 \
  --mount "type=bind,src=$container_output,dst=/data" \
  "$image" python -c 'import shutil; shutil.rmtree("/data/director")'
