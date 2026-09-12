# Robot Reel runtime image (MuJoCo, MCP director, MCAP inspection).
#
# Build:
#   docker build -t robot-reel .
# Check the included VLA recording (stdlib only, no GPU):
#   docker run --rm robot-reel
# Export a checked storyboard from the included braking comparison:
#   docker run --rm -v "$PWD/artifacts:/app/artifacts" robot-reel \
#     robot-reel direct docs/compare/braking \
#       --plan examples/contact-storyboard.json --output artifacts/director
# Record a MuJoCo pack with software rendering (slow):
#   docker run --rm -e MUJOCO_GL=osmesa -v "$PWD/artifacts:/app/artifacts" \
#     robot-reel robot-reel --pack braking --output artifacts/braking
#
# The Newton, Blender and GPU workflows are not covered by this image; see docs/.
FROM python:3.12-slim

# git: pip metadata and dependency sources; libgl1/libegl1/libosmesa6/libglib2.0-0: headless MuJoCo rendering.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libgl1 libegl1 libosmesa6 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e '.[director,inspect]'

ENV MUJOCO_GL=egl
CMD ["robot-reel", "vla", "docs/vla"]
