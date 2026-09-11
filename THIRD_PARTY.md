# Third-party components

Robot Reel is an independent project. It is not an official product of AWS,
Strands, Google DeepMind, Hugging Face, or Unitree.

| Component | Source | License / role |
| --- | --- | --- |
| Strands Robots | https://github.com/strands-labs/robots | Apache-2.0; robot factory and simulation integration |
| MuJoCo | https://github.com/google-deepmind/mujoco | Apache-2.0; simulator and renderer |
| SO-ARM100 model | https://github.com/google-deepmind/mujoco_menagerie/tree/main/trs_so_arm100 | Apache-2.0 model assets |
| Unitree G1 model | https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1 | Unitree BSD-style license; see the model directory's LICENSE |
| Microduck model | https://github.com/pollen-robotics/microduck_rl | Upstream README identifies 3D models as Creative Commons BY-SA-NC; it does not specify a version |
| Microduck walking policy | https://huggingface.co/pollen-robotics/microduck-policies | Official `alpha_walking.onnx`, pinned revision and SHA-256 in the capture; retain upstream terms |
| Microduck observation/action convention | https://github.com/pollen-robotics/microduck_rl/blob/main/scripts/infer_policy.py | Apache-2.0; credited in our adapter |

Models are fetched separately through `robot_descriptions`; meshes are not
vendored here. The video depicts these models. Keep this attribution with a
distributed demo bundle. Exact model license texts are included under
`licenses/` when packaging the release.

Microduck is fetched separately from a pinned official archive rather than
through `robot_descriptions`. Its model meshes and policy are not vendored in
this repository. Microduck video, preview GIF and poster depict those models:
keep the noncommercial/share-alike asset terms and the notice in
`docs/microduck/media/MICRODUCK-MEDIA-NOTICE.txt` with that footage. The
Apache-2.0 license on Robot Reel's recorder does not override upstream asset
terms. Pollen Robotics / Hugging Face has not endorsed Robot Reel.

The automotive geometry is authored procedurally in `robot_reel/packs.py`.
No Alpamayo weights, AlpaSim components or CARLA assets are distributed or run.

Pillow draws typography and overlays. FFmpeg, supplied through imageio-ffmpeg,
encodes video; its binary distribution has its own license conditions.
No third-party music, stock footage, or generated robot footage is used.
