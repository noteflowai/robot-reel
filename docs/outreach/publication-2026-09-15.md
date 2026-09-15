# Publication receipt · 2026-09-15

Recorded for the maintainer. Carried out by an assistant on the maintainer's explicit
instruction. No acceptance, review or endorsement by any third party is claimed.

## What was published

Robot Reel appears in a finding-led thread from
[@glay_oneai](https://x.com/glay_oneai/status/2099745359224578381), one post among four, sharing
the observation that each project's own green number was hiding something.

The post says: the 30-trial SmolVLA experiment was re-run on the same GPU, physics states were
bitwise identical 30 of 30, and renders matched on 3194 of 3195 frames. The frame that differed
was never consumed by a policy call, so it could not propagate, and it is reported rather than
rounded into "29 of 30 trials matched".

No GitHub issue was opened anywhere on this project's behalf. The VLA reproducibility literature
is an obvious neighbour for this work, but a note to any of those authors should say something
they do not already know, and the honest version of that note is still being worked out. It will
be drafted here first and reviewed before anything is sent, in the same way as the OWASP and HVE
notes in the sibling projects.

## What backs the claim

| Claim | Where it is checked |
| --- | --- |
| Physics states bitwise identical, 30/30 | `robot-reel stress docs/stress --repeat <run>` reports `identical_states` for every trial |
| Renders identical on 3194 of 3195 recorded frames | The same report's `recorded_renders` counts |
| The differing frame was never consumed | `input_renders` is 360 of 360, and the policy is called once every ten steps |
| Aggregates are committed | [`docs/stress-reproducibility.json`](../stress-reproducibility.json) beside the sealed pack |
| Failure taxonomy | [`docs/stress/reliability.json`](../stress/reliability.json), recomputed on verification rather than hash-checked |

The repeat run itself is 36 MB and rebuildable from the recorded plan, so only the aggregates are
committed. It is one repeat of one plan on one machine and does not establish determinism on other
hardware, drivers or stack versions.

## Not done

- No reminder comment on the open [科技爱好者周刊 #11664](https://github.com/ruanyf/weekly/issues/11664)
  or [HelloGitHub #3694](https://github.com/521xueweihan/HelloGitHub/issues/3694) submissions. Both
  are in an editorial queue where chasing costs more than it gains.
- No PyPI publication. [`docs/distribution.md`](../distribution.md) states that PyPI publishing is
  deliberately not enabled for this release, which is a maintainer decision.
