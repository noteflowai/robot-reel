# Contributing

Keep the distinction between physics rollouts, kinematic animation, and agent
decisions explicit in code, telemetry, and video labels.

Run `python3 -m unittest discover -s tests -v` directly from the checkout; these
tests require only the standard library. CI also runs them with `python -S`.
For capture/rendering development, follow the README virtual-environment setup
and install the declared dependencies with `python -m pip install -e .`.
Do not install only `imageio-ffmpeg`: MuJoCo and the remaining runtime dependencies
are required for recording too.
For capture changes, run the credential-free demo and verify its output.
Do not require a paid model or real hardware for ordinary tests.

Blender changes should also pass the saved-project check in [docs/blender.md](docs/blender.md).

Please include a short reproducible command and the observed result with fixes.
Do not commit credentials, account-specific logs, downloaded robot meshes, or
large videos. Release assets are the place for shareable video bundles.
