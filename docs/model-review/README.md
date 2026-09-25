# Model explanations beside recorded robot evidence

The frozen protocol and image inputs were committed before generation. This
selected development example uses three already published SmolVLA episodes;
it does not run a new policy. Six model outputs compare images-only review with
review supplied the recorded facts. The model's explanation is never treated as
a verified physical cause.

See [the tutorial and scope](../../docs/model-review.md), `protocol.json` for exact
prompts and settings, `sources.json` for original media and contact-sheet hashes,
and `recorded/` for every completed generation and the runtime identity.

The recording script rejects incomplete checkpoint loading. It documents an
explicit, in-memory Transformers 5.17.0 dense FP8 exclusion correction; model
weight bytes remain unchanged. See `runtime-failures.json` for initialization
attempts that produced no completed model answer.

```sh
python scripts/build_model_review.py --output runs/model-review-site
python scripts/build_model_review.py --output runs/model-review-site --verify
```

Open `index.html` in the resulting directory, or extract its `review.zip` to share
the same page, source clips, traces, sampled images, raw responses and fact checks.
Media attribution is in `NOTICE.txt`.
