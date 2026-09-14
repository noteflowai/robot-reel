# Review a recorded frame with an agent

Export a Microduck frame, have an agent load a focused review skill through
Skills Anywhere, then check the facts against this checkout before writing a
review. The same frame can be reopened in the browser for a visual inspection.

[Microduck Motion Lab](https://noteflowai.github.io/robot-reel/microduck-lab/) ·
[Sample frame JSON](../examples/microduck-frame.json) ·
[Skill and MCP walkthrough](https://github.com/noteflowai/dsh-skills-anywhere/blob/main/docs/PHYSICAL_AI.md)

## Start with one known frame

In the lab, choose a run, frame and joint, then select **Frame JSON**. The bundled
example is frame 120 of the 0.5 m/s command run, with `left_knee` selected.
From this source checkout, verify it with Python's standard library:

```bash
python3 scripts/build_microduck_lab.py --verify --frame-json examples/microduck-frame.json
```

The command first checks the complete lab, including original traces, videos,
source identities, derived poses and ZIP members. It then compares every field
of the received frame. The successful `frame` result identifies `right`, `120`
and `left_knee`, with `recorded_facts_match: true`.

| Checked fact | Example value |
| --- | --- |
| Video time | 4.0 s |
| Simulation sample time | approximately 4.035 s |
| Preceding policy step | 201 |
| Measured angle | approximately 0.249538 rad |
| Target angle | approximately 0.313140 rad |
| Signed residual, measured minus target | approximately −0.063602 rad |

The JSON retains full precision, the original trace SHA-256 and model commit.
These rounded display values are not a replacement for it. Changing a recorded
angle, source hash or another field makes verification fail.

## Load the review instructions through MCP

Skills Anywhere supplies a usable, MIT-licensed
[`robot-reel-review` skill](https://github.com/noteflowai/dsh-skills-anywhere/blob/main/examples/robot-reel-review/SKILL.md).
Follow its [local setup](https://github.com/noteflowai/dsh-skills-anywhere/blob/main/docs/PHYSICAL_AI.md)
to register the Git source for a review workspace, then use `find_skills` and
`open_skill` (or `skill://robot-reel-review`) in your MCP client.

Give the agent the actual absolute paths to this trusted checkout and the
received JSON. The skill asks it to run the read-only verifier through its own
execution tool, explain any mismatch, and distinguish checked facts from
interpretation. MCP delivers the skill text; it does not execute Python.
The HF skill playground shows that same skill as its fourth guided example and
does not read local recordings or run commands.

For a visual follow-up, choose **Open frame JSON** in Microduck Motion Lab.
A matching file restores the run, frame and joint while preserving your orbit.
Both the browser import and source verifier work without a GPU or model account.
An LLM is optional for explaining the facts; the verifier itself is deterministic.

## Scope of the review

A 0.5 m/s label is a command, not achieved walking speed. A joint residual alone
does not establish failure, contact or balance. The schematic fixes the floating
root because the original recordings did not save root orientation. The policy
runs use MuJoCo with PD-actuator fallback, not BAM or physical hardware.
A source match does not authenticate the sender or certify an agent's reasoning.
See [methods and media rights](microduck-lab.md) when sharing derived imagery.
