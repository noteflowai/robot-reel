## Summary

<!-- What changed and why. Include a short reproducible command and the observed result for fixes. -->

## Verification

Which of these did you run from the checkout root?

- [ ] `python3 -S -m unittest discover -s tests` (stdlib-only tests, as CI runs them)
- [ ] `npm run check:js` (type-check the inline viewer scripts; required for template script changes)
- [ ] `npm test` (browser replay tests)
- [ ] `python3 -m robot_reel.pages` (published pages match their templates)
- [ ] Other (capture demo, `--verify --check-usd`, Blender saved-project check, ...): 

Observed result:

```
```

## Checklist

- [ ] Physics rollouts, kinematic animation, and agent decisions stay explicitly labelled in code, telemetry, and video labels.
- [ ] No credentials, account-specific logs, downloaded robot meshes, or large videos are committed.
- [ ] If a replay template's inline script changed, the published pages under `docs/` were rebuilt (`python3 -m robot_reel.pages --write`) and the refreshed hashes are included.
- [ ] Ordinary tests do not require a paid model or real hardware.
- [ ] Docs (`README.md`, `docs/`, `CHANGELOG.md`) are updated where behaviour changed.
