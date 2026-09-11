# Two runs, one clock

Install `pip install -e '.[microduck]'`, then record two ten-second trials:

```bash
robot-reel --pack microduck --speed 0.3 --output artifacts/duck-slow
robot-reel --pack microduck --speed 0.5 --output artifacts/duck-fast
robot-reel compare --left artifacts/duck-slow/microduck-trace.json \
  --right artifacts/duck-fast/microduck-trace.json \
  --left-label '0.3 m/s command' --right-label '0.5 m/s command' \
  --output artifacts/duck-comparison
python -m robot_reel.verify artifacts/duck-comparison
```

Open `artifacts/duck-comparison/index.html`, including directly from disk. Download
`comparison.mp4` for a 1280×720 side-by-side film. Share the entire folder for the
interactive version. Keep the Microduck media notice with redistributed footage.
The comparison film has no soundtrack; the individual capture films include one.

For automotive physics, record the braking pack and compare its two controllers:

```bash
robot-reel --pack braking --output artifacts/braking
robot-reel compare --left artifacts/braking/braking_early-trace.json \
  --right artifacts/braking/braking_late-trace.json \
  --left-label 'Early braking / 14 m' --right-label 'Late braking / 2 m' \
  --output artifacts/braking-comparison
python -m robot_reel.verify artifacts/braking-comparison
```

The left video clock drives playback and telemetry; the right video is corrected
when drift exceeds one frame. Browser decoder timing can vary during playback.
Pausing and manual stepping align both videos to the same recorded frame. The timeline shows frame index / recording FPS; underlying MuJoCo
capture timestamps must agree between the two traces within one microsecond.

Inputs must have matching lengths, frame rates, channels, homes, timesteps, engine
versions and model identity. Braking permits only the trigger gap to change in the
vehicle configuration. No resampling or automatic winner score is applied.
Original selected traces, raw videos and source manifests accompany each output.
Checksums detect changes against the bundled manifest; they are not signatures or
independent proof of capture provenance.

Microduck uses the official ONNX policy with XML PD actuators, not BAM or hardware.
Measured forward speed is trunk-frame translational velocity averaged over captured
frames with a nonzero forward command. Final world x and lateral offset are positions
relative to the model's initial x=y=0. Neither commanded speed nor world x alone is
an assessment of walking quality. The braking model is a 1D surrogate with scripted
controllers, not autonomous driving or a safety validation.
