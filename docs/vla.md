# SmolVLA: inspect a real language-conditioned policy rollout

[Open the two-camera replay](https://noteflowai.github.io/robot-reel/vla/).
The task is **“pick up the black bowl between the plate and the ramekin and
place it on the plate.”** SmolVLA actually ran on CPU and applied controls to
LIBERO's simulated arm. The published seed-0 run completed the task according
to LIBERO's predicate after 76 actions: 3.8 simulated seconds, eight inference
calls, 77 recorded observations including the final state.

This is one rollout, not a success-rate benchmark or a physical robot test.
Collection took about 255 seconds after model/environment loading on the
tested host, with other rendering work in progress. Playback omits inference
waiting time. The demo does not claim real-time CPU inference.

## Reproduce in an isolated environment

The normal recording packs pin MuJoCo 3.13.0. LeRobot 0.6.1 uses MuJoCo 3.8.1;
install this recorder in a **separate Python 3.12 environment**. Do not install
the base Robot Reel package into that environment.

```bash
python3.12 -m venv .venv-vla
.venv-vla/bin/python -m pip install -r requirements/vla.txt
MUJOCO_GL=egl .venv-vla/bin/python scripts/record_smolvla.py \
  --output artifacts/vla --cache artifacts/vla-cache \
  --task-id 0 --seed 0 --action-steps 10 --max-steps 280
```

The tested Linux CPU renderer used Mesa EGL. On a system with an unusable
NVIDIA EGL driver and Mesa installed, select the available Mesa vendor file:

```bash
MUJOCO_GL=egl \
__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json \
OMP_NUM_THREADS=2 .venv-vla/bin/python scripts/record_smolvla.py \
  --output artifacts/vla --cache artifacts/vla-cache
```

This uses software OpenGL; CUDA is not required. The first run downloads
checkpoint and simulation assets from Hugging Face, requiring network access
and several GB of disk/RAM. Subsequent runs reuse the selected cache.
The collector creates LIBERO configuration before import, avoiding its
interactive setup prompt. It writes to user-selected paths and does not
require root. An existing nonempty recording directory is refused.

Use the normal Robot Reel environment to build and check the replay:

```bash
.venv/bin/python scripts/build_vla_site.py \
  --recording artifacts/vla --output artifacts/vla-site
.venv/bin/python -m robot_reel.cli vla artifacts/vla-site --check-media
# Pure trace/file verification also works without installed dependencies:
python3 -S -m robot_reel.cli vla artifacts/vla-site
```

The builder produces the offline HTML replay, both MP4s, measured trace,
attribution, checksum manifest, preview assets and a portable `episode.zip`.
Use `--font PATH` if DejaVu Sans is unavailable. The ZIP keeps the complete
viewer bundle together; extract it and open `index.html`.

## Pinned sources and adapter behavior

| Source | Revision |
| --- | --- |
| [HuggingFaceVLA/smolvla_libero](https://huggingface.co/HuggingFaceVLA/smolvla_libero) | `6721902bc4d61e50a3bfdb11dfb4cb626f05d102` |
| [HuggingFaceTB/SmolVLM2-500M-Instruct](https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Instruct) | `7b375e1b73b11138ff12fe22c8f2822d8fe03467` |
| [lerobot/libero-assets](https://huggingface.co/datasets/lerobot/libero-assets) | `0b3ea86be5fe169d0fd036ae63d1070ec09e90f6` |

Runtime: LeRobot 0.6.1, hf-libero 0.1.4, robosuite 1.4.0, MuJoCo 3.8.1,
PyTorch 2.11.0+cpu, Transformers 5.5.4, NumPy 2.2.6. The full checkpoint is
loaded with `strict=True` and its SHA-256 is recorded. Its embedded VLM
weights are used; a second copy of the VLM weights is not downloaded.

The published run explicitly overrides `n_action_steps` from the checkpoint's
1 to **10** to keep CPU inference practical. Each chunk is inferred from its
first observation; this is not a fresh model invocation at every action.
The policy retains ten denoising steps. The collector uses the upstream
observation, normalization and action processors.

LIBERO spatial task 0 uses initial state 0, seed 0, a hard reset and ten
settling steps before recording. Its measured simulator time therefore starts
at 0.5 s; episode time starts at zero. The adapter relies on hf-libero 0.1.4's
private asset-cache field to select the **pinned** snapshot, and on the
underlying simulator object for its actual clock. These contracts are tied
to the tested versions. Reset seeds alone do not guarantee bit-identical
outputs across hardware or dependency changes.

## What each frame means

- The scene and wrist images and eight measured state values are the
  observation **before** the associated action. Both image axes are flipped
  to match LeRobot's LIBERO preprocessing. Videos are 256×256 compressed
  recordings of those views, before model resizing.
- `proposed_action` stores seven policy controls after upstream
  postprocessing. `action` stores the actual values clipped to `[-1, 1]`
  and sent to the environment. These are normalized relative end-effector
  controls plus a gripper control, not joint angles or physical distances.
- Measured state is XYZ in meters, axis-angle rotation in radians and two
  gripper joint positions in meters. Seven arm joint positions are also
  retained independently.
- `inference_frame` identifies the observation used for the current chunk.
  Inference-call wall timings include that first environment step.
- `next_success` and `reward` describe the result **after** the action.
  Recording stops on success, termination or the configured step limit.
- The final observation has no action, inference reference or reward.
  Therefore this run has 76 controls and 77 video frames: 3.85 seconds of
  playback at 20 fps, covering 3.8 seconds of environment actions.

Validation checks timestamps, finite values, clipping, inference references,
terminal semantics, outcome consistency, both video lengths and embedded
viewer data. It does not rerun the learned model or independently prove that
the model produced a supplied trace. Routine CI validates the recorded
artifact and UI without downloading model weights; generating a fresh
episode is the explicit command above.

Preserve [the VLA media notice](../licenses/VLA-MEDIA-NOTICE.txt) when sharing
the videos and previews. Model weights and simulation meshes are not included
in the repository or episode download.
