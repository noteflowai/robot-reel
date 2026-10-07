# The same protocol, run against Claude on Amazon Bedrock

Two generations made with `../bedrock_claims.py` on 2026-10-07. Both use the frozen protocol in `../protocol.json`
and the committed contact sheet `../episode-b.png`. That sheet shows seed 09 under 25 % light; its recorded
outcome is `step_limit` after 160 actions.

Scope: this is one model and one episode, with one generation per prompt mode. It is a worked example of the
workflow: the model makes structured claims, and the recorded trace checks them. It is not a model ranking, an
accuracy estimate or a physical explanation.

| | Model | Region / API | Tokens in / out | Claims | `review-claims` |
|---|---|---|---|---|---|
| images only | `jp.anthropic.claude-opus-5-5` (Japan cross-Region inference profile) | ap-northeast-1, Converse | 1669 / 309 | `unknown`, `null`, frames 0–160 | outcome and action count **unassessed**; frames matched; `facts_match: false` |
| with record | same | same | 1748 / 194 | `step_limit`, `160`, frames 0–160 | all three **matched**; `facts_match: true` |

From images only, the model wrote that the bowl looks like it is placed on the plate, while the record says the
episode ran out of actions. It correctly kept the outcome `unknown` rather than claiming success. The checker
therefore reports those facts as unassessed, not as matched. Reading a supplied record back is record reading, not
visual discovery (see [the tutorial](../../../docs/model-review.md)). Explanations are kept verbatim and are never
assessed.

## Files

- `<case>.receipt.json`: the model id, Region and request id; the exact system and user text; the SHA-256 of the
  sheet; the inference settings actually sent and the protocol deviations; the raw answer text; token usage;
  latency.
- `<case>.claims.json`: the JSON object parsed from that raw text, unedited. `tests/test_bedrock_claims.py`
  re-parses each receipt and requires the result to equal this file.
- `<case>.review.json`: `robot-reel review-claims` output against
  `docs/stress/runs/seed-09-dim/attempt-001/trace.json`. The test re-runs the check and requires identical results.

Protocol deviation, recorded in each receipt: the Converse API has no seed, top-p, top-k or thinking switch
fields, and this model rejects `temperature`. Only the 512-token limit was sent. The Qwen generations next to this
directory used the full sampling settings, so the two sets are not a controlled comparison.

## Reproduce (billable, one call each)

```sh
pip install boto3
python examples/model-review/bedrock_claims.py episode-b-images-only \
  --model jp.anthropic.claude-opus-5-5 --region ap-northeast-1 --output runs/bedrock-review
robot-reel review-claims docs/stress/runs/seed-09-dim/attempt-001/trace.json \
  runs/bedrock-review/episode-b-images-only.claims.json
```

The script refuses to overwrite a recorded answer. An answer that is not one JSON object stays in the receipt, and
no claims file is written. Any Converse model that accepts images can be used. Add `--send-sampling` for models that
accept `temperature`.
