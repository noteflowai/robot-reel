# Robot Reel runtime image (MuJoCo, MCP director, MCAP inspection).
#
# Build:
#   docker build -t robot-reel .
# Check the included VLA recording (stdlib only, no GPU):
#   docker run --rm robot-reel
# Export a checked storyboard from the included braking comparison:
#   mkdir -p artifacts
#   docker run --rm --user "$(id -u):$(id -g)" \
#     -v "$PWD/artifacts:/app/artifacts" robot-reel \
#     robot-reel direct docs/compare/braking \
#       --plan examples/contact-storyboard.json --output artifacts/director
# Record a MuJoCo pack with software rendering (slow):
#   docker run --rm --user "$(id -u):$(id -g)" -e MUJOCO_GL=osmesa \
#     -v "$PWD/artifacts:/app/artifacts" \
#     robot-reel robot-reel --pack braking --output artifacts/braking
#
# The Newton, Blender and GPU workflows are not covered by this image; see docs/.
FROM python:3.12-slim

# git: pip metadata and dependency sources; libgl1/libegl1/libosmesa6/libglib2.0-0: headless MuJoCo rendering.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libgl1 libegl1 libosmesa6 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY robot_reel ./robot_reel
# Only the two documented sample inputs belong in the runtime image.
COPY docs/vla ./docs/vla
COPY docs/compare/braking ./docs/compare/braking
COPY examples/contact-storyboard.json ./examples/contact-storyboard.json
RUN pip install --no-cache-dir '.[director,inspect]' \
    && groupadd --gid 1000 robotreel \
    && useradd --uid 1000 --gid robotreel --create-home robotreel \
    && mkdir -p /app/artifacts \
    && chown robotreel:robotreel /app/artifacts

ENV MUJOCO_GL=egl \
    PYTHONDONTWRITEBYTECODE=1 \
    XDG_CACHE_HOME=/tmp/robot-reel-cache \
    MPLCONFIGDIR=/tmp/robot-reel-matplotlib
USER robotreel:robotreel
CMD ["robot-reel", "vla", "docs/vla"]
