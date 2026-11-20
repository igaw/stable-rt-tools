---
name: srt-release
description: Make or check a release of an out-of-tree patch series (e.g. PREEMPT_RT v6.12-rt) with srt from stable-rt-tools - quilt or git workflow, from srt prep to the announcement. Use when asked to do a new rt/stable-rt release, continue one, check where a release stands, or review the trees of a release.
---

# Releasing a series with srt

srt makes the releases of a patch series on top of upstream releases, e.g.
v6.12.118-rt24 on v6.12.118. The maintainer owns the release: you run the
local steps and the checks, they decide on everything which leaves the
machine. docs/quilt-workflow.rst, docs/git-workflow.rst and docs/agents.rst
describe the steps in detail.

## Rules

- Never upload, push or send mail on your own. `srt upload`, `srt push`
  and sending the announcement publish the release and can't be undone.
  Show the dry runs and wait for the maintainer's explicit OK for this
  release. An OK for one release is not one for the next.
- Don't test the kernel. Testing happens after `srt quilt release` (git
  workflow: after the tags) with the maintainer's own setup (e.g.
  srt-build and LAVA); stop there and let them test.
- The linux-6.18.y-rt branches (Sebastian Andrzej Siewior) are the
  reference for how a release looks: merge messages, the queue commit as
  announcement, the tarball, tag order -patches, -rebase, release.
- Several series can share a work area; each has its own prepared release.
  Work on the series the maintainer named.
- Keep the wording of the previous announcement (`git log -1 --format=%B
  <old tag>-patches`), don't propose new wording. A release which is only
  an upstream update lists `- none` as changes, as srt generates it: use
  the generated announcement unchanged then.

## With the srt MCP server

If the `srt` MCP tools are there (`srt mcp`), use them: `list_series`,
`status`, `check`, `queue_diff`, `queue_draft`, then the steps `prep`,
`refresh`, `queue`, `rebase`, `merge`, `release`, `create`, `sign`,
`announce`, and `undo`. Every step returns srt's output, the next step and
the status. `upload` and `push` are dry runs; the real ones need
`dry_run: false`, the maintainer's OK and a server started with
`--allow-publish`. If the server refuses, the maintainer runs them.

## With the srt command

Run srt from the worktree of the series (e.g. `rt/v6.12-rt`). srt asks
before every step which changes something; without a terminal a question
counts as no and the step stops.

- `-y`/`--yes` answers yes. Use it only for a step the maintainer asked
  for; never with `srt upload` or `srt push` without their OK.
- `srt quilt queue` opens an editor: `--draft` prints the generated
  announcement, `-F FILE` commits the completed one, `--no-edit` the
  generated one.
- `srt upload --dry-run` and `srt push --dry-run` change nothing.
- Set `GIT_EDITOR=true` so a git command never waits for an editor.
- Every command ends with `next: ...`; `srt status --json` and
  `srt check --json` give the state as JSON.

## Where does the release stand?

1. Fetch first, e.g. `git -C ../linux fetch stable` and
   `git -C ../linux fetch stable-rt`: another maintainer of the group may
   have released in the meantime.
2. `srt status` lists the steps done and the next one. A warning means the
   prepared release doesn't fit the fetched branches (published already,
   newer release on the series, newer upstream release): tell the
   maintainer, then `srt prep --clear` and `srt prep`.
3. `srt check` checks the trees of the steps done so far. A `fail` stops
   the release; report `warn` lines to the maintainer.

## Quilt workflow

```
srt prep                      # OLD_TAG -> NEW_TAG, updates the upstream worktree
  [maintainer adds or drops patches in ../<series>-patches/patches]
srt quilt refresh             # patches already upstream: ask before -y
srt check                     # queue: review what changed, show the git diff
srt quilt queue --draft       # announcement for the maintainer to complete
srt -y quilt queue -F FILE
srt -y quilt rebase
srt quilt merge               # conflict: stop, show it, the maintainer resolves
srt -y quilt release          # tree must equal -rebase, else a fixup commit
srt check
  [STOP: the maintainer tests the release]
srt create
srt sign                      # needs the maintainer's GPG key (agent unlocked)
srt check                     # files and signatures
srt upload --dry-run
srt push --dry-run
  [STOP: show both, wait for the OK]
srt -y upload
srt -y push
srt announce > ../announce    # the maintainer sends it
```

Release candidates don't exist in the quilt workflow.

Something wrong before the push: `srt -y quilt undo` deletes the local
tags, resets the series and keeps the refreshed patches; fix the queue and
redo from `srt quilt refresh`. After the push nothing is undone: a fixup
commit in the next release.

## Git workflow

Release candidate, in `<series>-next`: merge the upstream release,
`srt commit`, `srt tag -r N`, the maintainer tests, `srt announce` (sends
the review mails: ask first), `srt push`.

Release: in the series `git merge --ff-only <series>-next` and `srt tag`;
in `-rebase` `git rebase` onto the upstream release, `srt commit` and
`srt tag`; then in the series `srt create`, `srt sign`, `srt check`, and
upload, push and announce as above.

## Reporting

Tell the maintainer per step what happened in a line or two, quote
warnings and failures as srt printed them, and end with the next step.
