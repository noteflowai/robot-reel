# Check a model explanation against a recorded robot episode

[Open the model review](https://noteflowai.github.io/robot-reel/model-review/).
Compare the original main and wrist recordings with Qwen3.8-27B-FP8's responses
to five sampled frames from each camera, first without and then with the recorded
outcome. Download the complete review to open it offline.

This is a selected three-episode demonstration from the existing seed-09 SmolVLA
stress experiment: reference, dim and camera conditions. It contains one fresh
generation per mode per episode. It is not a new policy rollout, a model ranking,
a population accuracy estimate, or evidence of a physical failure mechanism.

## Check structured claims without a model

```sh
robot-reel review-claims trace.json claims.json --output review.json
```

The claims file has exactly these fields:

```json
{
  "outcome": "step_limit",
  "action_count": 160,
  "cited_frames": [0, 160],
  "explanation": "A visual interpretation to be reviewed separately."
}
```

This JSON is an authored format example. Original model responses are in the
review's `recorded/` directory. Extract their `text` field as JSON to pass it to
the checker; do not edit the answer to make it match.

The CLI reports each fact as `matched`, `contradicted`, or `unassessed`, binds the
inputs by SHA-256, and refuses to overwrite an existing report. Exit 0 requires
both facts to match and at least one existing cited frame; exit 1 means a mismatch
or an unassessed claim; exit 2 means invalid input or an output error.
`unknown` and `null` preserve uncertainty. The explanation is always `not_assessed`.
A real frame number does not prove that the image supports a claim. The trace is
supplied evidence, not independently authenticated physical truth.

## What the model received

The protocol was committed before generation. `examples/model-review/sources.json`
fixes the source commit, clip/trace hashes, sampled frame indexes and exact contact
sheet hashes. The sheets are decoded from the published lossy MP4 derivatives;
they are not the original policy-input RGB buffers. The two prompt modes differ
only by adding the machine-readable recorded facts. Repeating a supplied fact is
record reading, not independent visual discovery.

Model: `Qwen/Qwen3.8-27B-FP8`, revision
`017b9c7af6b5689d5dd426a76e0bc077eb5ca20a`. Runtime identities accompany the outputs.
Seed 17, temperature 0.6, top-p 0.9, top-k 20, thinking disabled, 512-token budget.
All completed outputs, including invalid JSON or wrong claims, are retained.

Transformers 5.17.0 interprets the checkpoint's nonexistent dense-model
`mlp.gate` exclusions as regex prefixes, incorrectly excluding `gate_proj` and
losing its FP8 scales. The recorder's explicit `--fix-dense-fp8-skip` removes those
router exclusions in memory, keeps the source weights unchanged, and rejects
any missing, unexpected or mismatched checkpoint keys. Failed initialization
notes are retained separately from completed model outputs.

After downloading the pinned checkpoint into `MODEL_DIR`, use the recorded
runtime versions and a suitable GPU (the recorded run uses an L40S):

```sh
python examples/model-review/record.py --vision --fix-dense-fp8-skip \
  --model "$MODEL_DIR" --model-id Qwen/Qwen3.8-27B-FP8 \
  --revision 017b9c7af6b5689d5dd426a76e0bc077eb5ca20a \
  --protocol examples/model-review/protocol.json --output runs/new-model-review
```

Fresh generation may differ across hardware or library versions. For ordinary
review, use the published outputs and `review-claims`; no GPU is needed.
The build script requires every protocol output, checks source hashes, recomputes
facts, verifies the offline archive and publishes into a new directory atomically.
Keep `NOTICE.txt` with all media; Robot Reel's code license does not relicense the
upstream robot assets.

## 中文

先看原始双相机回放，再读模型解释。三个已发布的 seed-09 仿真片段，各有“只看抽帧”
和“抽帧加结果记录”两种输入，共六次真实生成。命令 `review-claims` 仅核对结果标签、
动作数量和引用帧是否存在；解释与因果判断始终不参与自动判定。未知项不会被当作通过。
所有原始输出、采样图、提示词、模型版本、加载修正和复现命令均随离线包提供。
