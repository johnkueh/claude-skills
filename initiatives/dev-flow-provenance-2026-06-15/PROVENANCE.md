# dev-flow — provenance snapshot (2026-06-15)

What today's `dev-flow` skill + the PR-then-merge `ship-it` rewrite were derived
from, and where each source is backed up. Snapshot taken because some of the
source material lived **only in the unversioned `~/.claude/skills/` directory**
and would otherwise have no backup.

## Today's outputs (claude-skills, on the GitHub remote)
- `536638d` — PR #4: add `dev-flow` skill + runner + schema/template; evolve `ship-it` to PR-then-merge.
- `3338640` — PR #5: name agent-browser + argent as the pre-PR real-surface check.
- Reference manifest for drafty.im: johnkueh/drafty PR #30 (open).

## Sources — already backed up in git (no copy needed, recorded for the trail)
- **ship-it, pre-today (claude-skills)** — `git show 6baca61:skills/ship-it/SKILL.md`
  (commit `6baca61`, "restore the full method, generalize only the project bindings", 2026-06-13;
  prior `0abc6f9`). The actual base this rewrite evolved. A copy is included here as
  `ship-it.pre-today.claude-skills-6baca61.md` for a self-contained bundle.
- **drafty.im gate scripts** (the deterministic layer dev-flow's contract points at) —
  tracked in johnkueh/drafty, read at HEAD `ba38cf6` (scripts last touched 2026-06-13):
  `web/scripts/{ship-check.sh, prod-smoke.sh, worktree-prep.sh, worktrees-gc.sh}`.
- **dev-up skill** (env/worktree/metro-takeover/expo-qa) — `skills/dev-up/` in this repo.

## Sources that were UNVERSIONED — snapshotted here (the real backup gap)
The whole `~/.claude/skills/` dir (27 personal skills) is not a git repo and is
backed up nowhere. These three fed today's work directly:
- `ship-it.local-claude-dir-copy.md` — `~/.claude/skills/ship-it/SKILL.md`, a **distinct older
  copy** (67 lines diverged from `6baca61`). This is the harness-loaded one; it predates the
  claude-skills generalization. Preserved here so the older phrasing/lessons aren't lost.
- `goto-project.local-copy.md` — `~/.claude/skills/goto-project/SKILL.md` (local-only; dev-flow
  delegates routing to it).
- `proof-canvas.local-copy.md` — `~/.claude/skills/proof-canvas/SKILL.md` (local-only; the
  visual-proof step references it).

## Open backup gap (flagged, not yet acted on)
`~/.claude/skills/` (27 local-only skills incl. argent-*, johns-*, clove-*, glp3-daily,
drafty-outreach, skill-creator) has **no version control or remote backup**. Today's
snapshot covers only the 3 dev-flow-relevant ones. A full backup of that dir (its own
private git repo, or sync into this repo) is the durable fix — see the report.
