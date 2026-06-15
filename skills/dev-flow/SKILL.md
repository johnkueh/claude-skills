---
name: dev-flow
description: John's master development workflow — the reasoning layer that takes a request from "go work on X" to landed-and-verified. Use when John says "go work on <project>", names a project plus a task, "fix this bug", "implement this feature", or fires a ship go-word ("ship it", "do it", "let's go") about a code-change plan. It routes (delegates to goto-project), classifies the work as bug/feature/other, drives the right path, decides when confident enough to PR and when to merge, and picks web-vs-OTA-vs-native-rebuild on landing. It REASONS; it never spells mechanical steps — those are deterministic verbs in the per-repo `.workflow.json` contract, called via the `dev-flow` runner (doctor/prep/gate/smoke/gc/pr) and `dev-up`/`dev-down`. Defers to ship-it for the standing ship authorization itself, to goto-project for routing, and to drafty-proof-canvas for visual proof. Do NOT duplicate those skills.
---

# dev-flow

The thin reasoning skill on top of a per-repo CONTRACT of deterministic scripts. Your job here is judgment: route, classify, pick the repro, read the evidence, decide when the work is confident enough to PR, decide when to merge. Everything mechanical — bootstrapping a worktree, the confidence gate, the prod smoke, the GC, opening and merging the PR — is a `dev-flow` verb or an existing repo script. If a step is deterministic, it is NOT prose here; you call the verb.

## The contract you stand on

Each repo carries a `<repo-root>/.workflow.json` manifest that points the generic verbs at that repo's real scripts. You never hardcode a script name or a mechanical step — you ask the runner:

- `dev-flow info` — print the resolved manifest (package manager, deploy type, hooks)
- `dev-flow doctor [--fix]` — validate the manifest + that each hook exists; `--fix` scaffolds one by inference
- `dev-flow prep` — repo-specific worktree bootstrap (extras beyond what `dev-up` already seeds)
- `dev-flow gate` — the full local confidence gate (REQUIRED hook; nonzero = do not ship)
- `dev-flow smoke [args...]` — read-only post-deploy prod smoke (optional)
- `dev-flow teardown [--keep-branch]` — retire THE CURRENT worktree once its PR landed, then delete its branch (local + remote). Squash-safe (recognises a MERGED PR via gh, not just ancestry). This is the per-worktree teardown — use it, not `gc`.
- `dev-flow gc` — REPO-WIDE sweep of landed+idle worktrees (falls back to dev-up's generic GC). It can prune another session's worktree — reserve it for explicit cleanup, never routine teardown.
- `dev-flow deploy-type` — prints `auto-vercel | ota | native-rebuild | none` so you know how landing reaches users
- `dev-flow pr open --title T [--body-file F] [--canvas URL] [--proof img...]` — push branch, open PR with canvas + proof baked into the body
- `dev-flow pr merge [--squash] [--keep-branch]` — merge now (this is the deploy trigger); deletes the remote branch by default

Run `dev-flow doctor` early when a repo is new to you — a missing or stale manifest is the one thing that turns this flow back into guesswork.

## Lifecycle

```
prompt
  -> goto-project        (route name -> repo -> cd -> read CLAUDE.md -> fetch+pull main)
  -> CLASSIFY            {bug | feature | other}
  -> the path for that class
  -> land decision       (PR -> merge, gated on confidence)
  -> teardown            (exit worktree once landed + smoke-tested)
```

### Route

Delegate to **goto-project** — do not reimplement routing. It resolves the name, cds in, loads the repo CLAUDE.md (env gotchas, harness, deploy behavior), and reports the parked branch + WIP. Take what it tells you as ground: John often parks the main checkout on a WIP branch, which is exactly why work happens in a worktree, never in that checkout.

### Classify

Read the request and decide one of three. The classification picks the path; getting it wrong wastes the turn.

- **bug** — something built behaves wrong. The path is evidence-first: prove the cause, prove the fix.
- **feature** — new capability or visible change. The path is plan-first: agree the shape before building.
- **other** — not a code change to a built surface (a question, a script run, a message, research, a release that owns its own authorization). Skip this flow; proceed normally. Don't manufacture a worktree for a one-liner.

When ambiguous, lead with your read and one line of why, then proceed — don't stall on taxonomy.

## The bug path

1. **Investigate the root cause before touching code.** The cause lives in the code, the analytics, or the logs — not in a guess. Pull the real evidence: the failing line, the actual event data, the production log body (use the `--no-follow --expand` Vercel backfill, not the streaming default). Rank candidate causes by likelihood; don't promote the first one to "the cause" off a single sample.
2. **Stand up an isolated worktree.** `dev-flow prep` for repo-specific bootstrap; `dev-up` when you need a running server (it seeds env from the main checkout, installs, serves a public URL). The gate provisions its own throwaway backend internally — you don't wire one up.
3. **Reproduce CONCLUSIVELY.** A bug you can't reproduce is a hypothesis. Write the repro test, or drive the real surface (simulator via Argent for mobile, the actual browser/PWA for web) until you see the reported failure with your own eyes, on the surface that matters — the user's real data shape, not a clean synthetic.
4. **Fix, then re-run the repro.** The same test/flow that was red must go green. Treat a second report of the same symptom as a class bug: fix the category and add the cheapest tripwire, don't patch the instance.
5. **Confidence gate.** `dev-flow gate`. Green = the change broke nothing the suite exercises. Capture the baseline first so "no regressions" means something. Cover the edge cases the bug exposed.
6. **Land** — see the decision gates below.

## The feature path

1. **Shape before code.**
   - Small / one-shot / non-visual → state the plan in chat in a few lines, then build.
   - Complex or taste-contested (visual, copy, layout, architecture) → put it on a **drafty canvas** first and get the call before building. Never burn deploys iterating a subjective visual the user hasn't seen.
2. **On the ship go-word** ("ship it", or a go-word about a plan whose endpoint is shipping) — the setup/teardown is identical to the bug path: worktree, implement, gate, proof, PR, merge-if-confident, teardown. The ship *authorization semantics* (hard vs soft trigger, what's in scope, when the push needs reconfirmation) belong to **ship-it** — defer to it; don't restate them here.
3. **Refresh user-facing content as part of the ship**, not as adjacent work — changelog + KB per the repo's `content` manifest hints. This is ship-it's step; follow it there.
4. **Implement → gate → land.** Feature-complete + gate-green + confident = land. Half a feature doesn't ship.

## The other path

Not a bug or feature against a built surface → this flow doesn't apply. Do the thing directly. Release flows that own their authorization (OTA, EAS, plugin/CLI version bumps, clove `/release`) are explicitly out of scope — route to their skills.

## Decision gates

**When confident enough to PR.** All of: the repro is green (bug) or the flow works on its real surface (feature); `dev-flow gate` exits zero against a captured baseline; visual work has been looked at, not just compiled; the happy path has been exercised once for real on the surface a user hits.

**Drive the change on its real surface before opening the PR — `dev-flow gate` green is necessary but NOT sufficient.** The gate is a server/build/contract check; it is structurally blind to runtime and interaction (a leak-freeness break still *looks* like a working gate; a green ship-check ≠ a verified feature). So before `dev-flow pr open`, actually exercise the changed flow:
- **Web / PWA** → **agent-browser** (or the `run` skill) against the running dev server — click the real button, submit the real form, watch the real console/network. For a PWA or mobile-Safari target, drive it there, not just headless desktop Chrome.
- **Mobile (RN/Expo)** → **argent** on the iOS simulator / Android emulator — tap through the changed screen via the discovery→tap loop, never from a guess.
This is the one check that catches "compiles and the suite's green, but the trigger never fires on the real device." Capture the screenshots here — they're the proof.

Then push proof and open the PR: visual work ends with a **drafty-proof-canvas** (required by John's standing rules and ship-it) — push the screenshots, put the bare URL in the report, send the PNGs via SendUserFile. `dev-flow pr open` bakes the canvas link and proof refs into the PR body.

**When to merge.** Confident, no regression risk, edge cases covered → `dev-flow pr merge` (this is the deploy trigger). Anything flaky, unverifiable, or half-done → leave the PR open, report exactly what passed and what's uncertain, don't hedge-merge. A non-fast-forward rejection means main moved under you: re-sync the branch onto `origin/main`, re-run the gate on what changed, retry.

**How landing reaches users — branch on `dev-flow deploy-type`:**
- `auto-vercel` (web, e.g. drafty.im) — merge IS the deploy. After it lands, confirm the new build is serving, then `dev-flow smoke` for prod-only failure classes (env vars, routing, un-pushed schema). If smoke fails, revert main (revert commit, never force-push), confirm the revert deployed, report.
- `ota` (mobile JS-only change) — merging to main does NOT ship to devices. The OTA release is a **separate authorization** each time; name it as a pending step, don't fire it under this flow.
- `native-rebuild` (mobile change touching native code/deps) — no OTA can carry it. **Hand back to the user**: state plainly that a native rebuild + reinstall is required, with the exact build command as the chat line that authorizes it (John doesn't run terminal commands manually). Don't pretend the change is live.
- `none` — nothing auto-deploys; report the merged commit and stop.

## v1 constraints (explicit, John)

- **Single-threaded.** No parallel subagents in the runtime flow. One piece of work at a time; v2 territory otherwise.
- **Push from the worktree to GitHub — NEVER merge the branch into the local main checkout.** That checkout is stale and usually parked on John's WIP; the exit-time local merge is where every agent merge-conflict incident came from. Land via the PR (`dev-flow pr open` → `pr merge`), straight to remote main.
- **Exit the worktree once landed + smoke-tested.** `dev-down` whatever dev-up started, then `dev-flow teardown` — it confirms the change actually landed (MERGED PR via gh, or HEAD an ancestor of `origin/main` — so a `--squash` merge, which rewrites the SHA, is still recognised), removes THIS worktree, and deletes its branch local + remote. Don't reach for `dev-flow gc` here: it's a repo-wide sweep that can prune another session's worktree. Leave the main checkout exactly as found.

## RN/Expo reality — honest

Per-worktree isolation of Metro and the dev client is **solved**: `metro-takeover.sh` swaps Metro to a worktree and `expo-qa.sh` gates the fingerprint and publishes `eas update --branch wt/<branch>` for on-device branch QA (both in the **dev-up** skill). What is NOT parallelizable in v1: **a single iOS simulator is a hardware singleton.** Two flows cannot drive the same simulator at once. Serialize on it — one simulator-bound flow at a time — until v2 introduces multi-device orchestration. This is the concrete reason mobile work stays single-threaded even where the JS tooling could fan out.

## What this skill defers, never duplicates

- **goto-project** — routing (name → repo → cd → CLAUDE.md → fetch+pull). Call it; don't re-derive paths.
- **ship-it** — the standing ship authorization, its trigger tiers, scope rules, and the content-refresh step. The land decision here uses ship-it's semantics; it does not restate them.
- **drafty-proof-canvas** — pushing visual proof to a drafty canvas. The PR/report references it.
- **dev-up** — worktree env seeding, public dev URLs, metro-takeover, expo-qa, the generic worktree GC fallback.

drafty.im is the reference implementation of the contract: bun-locked, `auto-vercel`, gate `web/scripts/ship-check.sh`, smoke `web/scripts/prod-smoke.sh`, prep `web/scripts/worktree-prep.sh`, GC `web/scripts/worktrees-gc.sh`, content in `web/src/content/{changelog.ts,kb/}`.
