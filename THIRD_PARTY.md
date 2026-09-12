# Third-party components

Robot Reel is an independent project. It is not an official product of AWS,
Strands, Google DeepMind, Hugging Face, or Unitree.

| Component | Source | License / role |
| --- | --- | --- |
| Strands Robots | https://github.com/strands-labs/robots | Apache-2.0; robot factory and simulation integration |
| MuJoCo | https://github.com/google-deepmind/mujoco | Apache-2.0; simulator and renderer |
| Newton | https://github.com/newton-physics/newton | Apache-2.0; optional CPU rigid-body simulation |
| NVIDIA Warp | https://github.com/NVIDIA/warp | Apache-2.0; Newton's simulation runtime |
| OpenUSD | https://github.com/PixarAnimationStudios/OpenUSD | Modified Apache-2.0; optional scene export and transform verification |
| SO-ARM100 model | https://github.com/google-deepmind/mujoco_menagerie/tree/main/trs_so_arm100 | Apache-2.0 model assets |
| Unitree G1 model | https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1 | Unitree BSD-style license; see the model directory's LICENSE |
| Microduck model | https://github.com/pollen-robotics/microduck_rl | Upstream README identifies 3D models as Creative Commons BY-SA-NC; it does not specify a version |
| Microduck walking policy | https://huggingface.co/pollen-robotics/microduck-policies | Official `alpha_walking.onnx`, pinned revision and SHA-256 in the capture; retain upstream terms |
| Microduck observation/action convention | https://github.com/pollen-robotics/microduck_rl/blob/main/scripts/infer_policy.py | Apache-2.0; credited in our adapter |
| SmolVLA LIBERO policy | https://huggingface.co/HuggingFaceVLA/smolvla_libero | Apache-2.0; separately downloaded, pinned checkpoint |
| SmolVLM2 backbone | https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Instruct | Apache-2.0; tokenizer/config, with weights inside the full policy checkpoint |
| LeRobot | https://github.com/huggingface/lerobot | Apache-2.0; VLA inference and observation/action processors |
| LIBERO | https://github.com/Lifelong-Robot-Learning/LIBERO | MIT; manipulation tasks and task predicates |
| LIBERO asset snapshot | https://huggingface.co/datasets/lerobot/libero-assets | Pinned, downloaded separately; retain upstream asset terms and attribution |
| MCP Python SDK | https://github.com/modelcontextprotocol/python-sdk | MIT; optional local director tool server |
| Blender | https://www.blender.org | GPL; external application used to create and render editable scenes |

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
The Newton demo uses procedural box geometry authored in `robot_reel/newton.py`.
Its browser preview draws measured poses without third-party mesh assets.
The Butterfly Lab records twelve isolated Newton worlds with procedural boxes.
Its time sculpture draws measured tip paths, and its OpenUSD file preserves
local body poses under explicitly offset presentation groups. Its source
mapping and media notice are in `docs/chaos/`; no third-party visual assets or
image generation models are used.
The director uses the same procedural geometry and recorded braking samples.
The README showcase uses excerpts of the published VLA, director and Newton
replays. Its source frame mapping and media notice are in `docs/showcase/`.
The Physics → Cinema comparison uses the original procedural braking footage
and its Blender replay; it does not introduce additional model assets.

The VLA videos and previews depict LIBERO/robosuite assets. Keep
[`licenses/VLA-MEDIA-NOTICE.txt`](licenses/VLA-MEDIA-NOTICE.txt) with this footage.
The downloaded LIBERO asset dataset does not declare a dataset license in its
card metadata; the recorder's Apache-2.0 license does not override asset terms.
No policy weights or LIBERO meshes are vendored here. Exact revisions,
checkpoint hash and runtime versions are in the episode's `trace.json`.

Pillow draws typography and overlays. FFmpeg, supplied through imageio-ffmpeg,
encodes video; its binary distribution has its own license conditions.
No third-party music, stock footage, or generated robot footage is used.
