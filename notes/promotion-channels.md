# Robot Reel publication record and next channels

Checked September 13, 2026. A submitted issue is a request for editorial review,
not a listing or endorsement. Do not reopen or duplicate a submission to bump it.

## Published and submitted

| Channel | Status | Public record | Submitted content |
| --- | --- | --- | --- |
| Newton — Show and tell | Published community showcase | [Discussion #4237](https://github.com/newton-physics/newton/discussions/4237) | [Newton recording / USD / Blender](outreach/newton-showcase.md) |
| 科技爱好者周刊 | Submitted; awaiting editorial selection | [Issue #11664](https://github.com/ruanyf/weekly/issues/11664) | [Chinese interactive-lab introduction](outreach/weekly-submission.md) |
| HelloGitHub | Submitted; awaiting review | [Issue #3694](https://github.com/521xueweihan/HelloGitHub/issues/3694) | [Beginner-oriented project form](outreach/hellogithub-submission.md) |
| Awesome Physical AI, maintained by natnew | Suggested; awaiting curation | [Issue #26](https://github.com/natnew/awesome-physical-ai/issues/26) | [Evaluation Methodology resource](outreach/physical-ai-resource.md) |
| Hugging Face | Space, pinned Community introduction and collection already public | [Space](https://huggingface.co/spaces/glayguo/robot-reel) | [Existing publication record](huggingface-launch.md) |

The four new submissions identify the maintainer relationship. Images and
method links use the verified source commit
`858886243c100f866be773d2c32eb13c2e2da917`. All ten distinct links in their bodies
returned HTTP 200 before submission; GitHub readback matched the prepared text.
The standard-library cloth and Butterfly verifiers also passed. These checks
validate the supplied recordings; no new simulation was needed for publication.

## Next channels, in priority order

| Channel | Suitable contribution | Current next step |
| --- | --- | --- |
| Blender Artists, Resources → Released Add-ons and Extensions | A free script/workflow showing recorded deformation → USD → Blender, with the downloadable source and frame-rate details | [Draft ready](outreach/blender-workflow.md); needs the owner's forum login. Tag `free`; identify this as a Python workflow, not an installed Blender extension. |
| DEV Community | A substantive tutorial on preserving source samples, clocks and transforms across an export | Needs an author account. Include the working example in the article and disclose AI assistance; a link-only announcement does not meet the content policy. |
| Show HN | A directly usable experiment with the creator available to discuss it | Human-written submission and comments required. Use the fact brief below; do not paste an AI-written launch comment. |
| Reddit robotics / Blender communities | A concrete recording or import example matched to the community | Rules could not be verified: Reddit returned 403. Read current sidebar and pinned threads while signed in before choosing a post type. |
| Awesome Robotics Libraries | A portable inspection tool alongside existing robotics visualization software | Revisit after more usage evidence. The directory scores activity, documentation, popularity, maturity and uniqueness; this two-day-old project lacks the popularity/maturity points, and overlap with Foxglove needs a clear explanation. |
| Hugging Face Blog Articles | A longer engineering article linked to the existing Space | Current account has no PRO subscription or qualifying organization. The current publishing rules require one of those; no subscription was purchased. |

For Chinese tutorials, the existing [customer brief](customer-brief.zh-CN.md)
and the weekly submission provide factual material for 知乎 / 掘金. Their account
access and current posting rules have not been checked, so neither is recorded
as submitted.

## Show HN fact brief — not a post draft

- Usable entry: the direct Cloth Lab or the three-lab Space, without sign-up.
- Creator should explain their own motivation and implementation choices.
- Three labs: 30 SmolVLA closed-loop simulated trials; 42,471 recorded cloth
  vertex samples; 12 CPU Newton worlds and 14,424 body poses.
- All SmolVLA outcomes remain available; one task and a 160-action cap.
- Cloth replay contains original vertices and derived measurements. No
  collision, self-contact or calibrated material claims.
- Adjacent pendulum release angles differ by 0.05°. The reported 6.260145 m
  peak is world 04 versus world 01, whose initial angles differ by **0.15°**.
- Viewing a recording needs no live GPU service. The cloth recording and
  SmolVLA inference used L40S; the pendulums used CPU.
- Do not solicit votes, delete and repost, or present a minor version bump
  as a new Show HN project.

## Rules checked

- [Newton contribution guide](https://github.com/newton-physics/newton/blob/main/CONTRIBUTING.md):
  discussions for community topics; issues for bugs/features leading to changes.
  The live API confirmed a **Show and tell** category.
- [Weekly README](https://github.com/ruanyf/weekly): explicitly invites software,
  article and resource submissions through issues. The recruitment thread is
  a separate channel.
- [HelloGitHub submission form](https://github.com/521xueweihan/HelloGitHub/blob/master/.github/ISSUE_TEMPLATE/submit-cn.yaml)
  and [review criteria](https://github.com/521xueweihan/HelloGitHub/issues/271):
  self-submissions allowed; 32–256-character description; documentation and
  licensing expected. Public site search and GitHub issue search showed no
  earlier Robot Reel entry.
- [Awesome Physical AI guide](https://github.com/natnew/awesome-physical-ai/blob/main/CONTRIBUTING.md)
  and [curation standards](https://github.com/natnew/awesome-physical-ai/blob/main/website/docs/curation-standards.mdx):
  documentation and activity required; 100 stars preferred, not mandatory.
  Submission discloses the project's age and one-star count. Its form refers
  to a label that did not exist; the issue was submitted without that label.
- [Blender Artists guidelines](https://blenderartists.org/guidelines)
  and [category description](https://blenderartists.org/t/294166):
  use the appropriate category, avoid cross-posting and tag released scripts
  `free` or `commercial`.
- [DEV terms, content policy](https://dev.to/terms)
  and [code of conduct](https://dev.to/code-of-conduct):
  substantial on-topic content rather than promotion/backlinks; disclose
  AI assistance.
- [Show HN guidelines](https://news.ycombinator.com/showhn.html)
  and [HN general guidelines](https://news.ycombinator.com/newsguidelines.html):
  usable work, creator participation, no vote solicitation; generated or
  AI-edited text is prohibited in comments.
- [Awesome Robotics Libraries criteria](https://github.com/jslee02/awesome-robotics-libraries/blob/main/CONTRIBUTING.md):
  new resources use the suggestion issue workflow; direct addition PRs are
  automatically closed.
- [Hugging Face Blog Articles](https://huggingface.co/docs/hub/en/blog-articles):
  personal publishing requires confirmed email and PRO or qualifying Team /
  Enterprise membership.

## Follow-up

Respond to technical questions on the existing threads. Record accepted
listings only after the curator's decision; a closed issue alone does not
establish acceptance. Check GitHub traffic/referrers and actual community
feedback before deciding which tutorial to write next. No traffic or star
increase has been measured or promised by this publication record.
