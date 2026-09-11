# Third-party components

Robot Reel is an independent project. It is not an official product of AWS,
Strands, Google DeepMind, Hugging Face, or Unitree.

| Component | Source | License / role |
| --- | --- | --- |
| Strands Robots | https://github.com/strands-labs/robots | Apache-2.0; robot factory and simulation integration |
| MuJoCo | https://github.com/google-deepmind/mujoco | Apache-2.0; simulator and renderer |
| SO-ARM100 model | https://github.com/google-deepmind/mujoco_menagerie/tree/main/trs_so_arm100 | Apache-2.0 model assets |
| Unitree G1 model | https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1 | Unitree BSD-style license; see the model directory's LICENSE |

Models are fetched separately through `robot_descriptions`; meshes are not
vendored here. The video depicts these models. Keep this attribution with a
distributed demo bundle. Exact model license texts are included under
`licenses/` when packaging the release.

Pillow draws typography and overlays. FFmpeg, supplied through imageio-ffmpeg,
encodes video; its binary distribution has its own license conditions.
No third-party music, stock footage, or generated robot footage is used.
