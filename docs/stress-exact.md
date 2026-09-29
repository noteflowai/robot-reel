# Exact test for paired Stress Lab outcomes

From a source checkout, run:

```bash
python3 -m robot_reel.cli stress docs/stress --paired-exact
```

The command verifies the complete recorded collection and adds
`paired_exact_test` to the usual JSON result. It uses the same outcome groups
as `--paired`: `lost_success` is \(b\), `gained_success` is \(c\), and
\(n=b+c\) is the number of discordant seeds. Both-success and neither-success
seeds do not contribute to this test.

For each changed condition, the exact two-sided binomial sign test (exact
McNemar) reports \(p=\min(1, 2\sum_{k=0}^{\min(b,c)}\binom{n}{k}/2^n)\).
The JSON retains the integer numerator and denominator. It also reports
Holm-adjusted p values across the listed condition comparisons.

| Condition ID | Lost \(b\) | Gained \(c\) | Exact \(p\) | Holm-adjusted \(p\) | Smallest attainable \(p\) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `dim` (25% light) | 1 | 0 | 2/2 = 1.0 | 1.0 | 1.0 |
| `camera` (+12 cm) | 1 | 3 | 10/16 = 0.625 | 1.0 | 0.125 |

With only one and four discordant seeds respectively, even the most extreme
split cannot produce \(p<0.05\). These results concern one locked task and
its recorded pairs. They are not a power analysis, multi-level outcome model,
sequential-stopping correction, proof of general robustness or causal claim.

Run `--paired-exact` separately from `--paired` so the latter's exported JSON
remains directly comparable for `--paired-report` verification. The existing
[experiment methods](stress.md) and the offline pack describe the original
recording and remain byte identical to the published release.
