# Contributing

Keep the distinction between physics rollouts, kinematic animation, and agent
decisions explicit in code, telemetry, and video labels.

Start with the README setup. Run `python -m unittest discover -s tests -v`.
For capture changes, run the credential-free demo and verify its output.
Do not require a paid model or real hardware for ordinary tests.

Please include a short reproducible command and the observed result with fixes.
Do not commit credentials, account-specific logs, downloaded robot meshes, or
large videos. Release assets are the place for shareable video bundles.
