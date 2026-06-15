---
name: dev-ship
description: A standing ship authorization. Use when you say "ship it", "ship this", "execute and ship", or "ship it to main" about work planned or discussed in the current session — that is the full no-reconfirmation authorization. ALSO use on a generic go-word ("execute it", "do it", "do it now", "let's go", "go ahead", "run it") about a code-change plan discussed in session whose natural endpoint is shipping — but then follow the Triggers section: confirm scope before merging. It means — execute the agreed plan in a worktree, test and validate everything locally, and if confident there is no regression risk, open a PR and merge it (the merge is the deploy trigger). NOT for go-words about non-shipping work (sending messages, running scripts, drafting), and NOT for product release flows that have their own process and authorization (app-store submissions, OTA releases, package/CLI/plugin version bumps — each a separate authorization).
---

# Ship it

"Ship it" is a single end-to-end authorization: execute the plan already discussed, validate it locally, and — if confident — open a PR and merge it (the merge is what deploys). Do not re-ask permission per step. The plan discussed in the conversation is the scope — "ship it" does not authorize adjacent work (refactors, READMEs, wiring) beyond it. One standing exception: the content-surface refresh in step 4 (changelog + docs) is part of every ship, not adjacent work.

**Where the project-specific bits live — the dev-flow contract.** This skill is the universal *method* (the reasoning). The deterministic *mechanics* — which gate script to run, which smoke/prep/gc to invoke — live in each repo's `.workflow.json` manifest and are invoked through generic `dev-flow` verbs (`dev-flow gate`, `dev-flow smoke`, `dev-flow prep`, `dev-flow gc`). The env gotchas, deploy behaviour, and content-surface locations still live in each repo's `CLAUDE.md`. Step 1 is read it first; everywhere this skill names a `dev-flow` verb, the repo's manifest names the actual script behind it.

**`drafty.im` is the named reference implementation.** Throughout, the concrete drafty script is given alongside the generic verb so the binding is legible: `dev-flow gate` → `bash web/scripts/ship-check.sh`, `dev-flow smoke` → `bash web/scripts/prod-smoke.sh`, `dev-flow prep` → `bash web/scripts/worktree-prep.sh`, `dev-flow gc` → `bash web/scripts/worktrees-gc.sh`. A repo without a `.workflow.json` either gets one (`dev-flow init` / `dev-flow doctor --fix`) or falls back to the script names its `CLAUDE.md` records.

**dev-flow is the front-of-house orchestrator; this skill is its ship authorization.** The `dev-flow` master skill is the reasoning layer that routes a prompt (via `dev-goto`), classifies it bug/feature/other, and drives the full investigate→reproduce→fix→prove lifecycle. When that flow reaches the ship boundary, it *calls this skill* for the ship semantics below — the worktree discipline, the confidence gate, the PR-then-merge decision, the teardown. dev-flow owns the "what to build and how to prove it"; dev-ship owns "is it safe to merge, and how do we merge it without stranding work."

## Triggers — two tiers

**Hard trigger** — "ship it", "ship this", "ship to main", "execute and ship": full authorization, no reconfirmation. Run the whole workflow including opening AND merging the PR.

**Soft trigger** — generic go-words ("execute it", "do it", "do it now", "let's go", "go ahead", "run it") about a code-change plan discussed in session whose natural endpoint is shipping:

1. First check what's actually being approved. If the go-word refers to non-shipping work (send a message, run a script, draft something, a single command), this skill does not apply — just do that thing.
2. If it is a ship-shaped plan: state the interpretation in ONE short message — scope of the change + "this ends with a merged PR (deploys to prod); say stop if that's not what you meant" — then start the reversible work immediately (worktree, implement, validate). Don't block waiting; the implementation runway is the objection window.
3. **The merge needs confirmation on this tier.** If the user is responsive (live session, or a clarifying question is viable), confirm before merging the PR. If unattended and no reply by merge time: stop at the validated state, open the PR (which pushes the feature branch only — NOT a merge to main), and ask — a soft trigger never merges unconfirmed.

This keeps "ship it" fast (zero friction) while go-words cost at most one confirmation at the only irreversible step (the merge).

## What it authorizes

- Creating a worktree and implementing the agreed plan in it
- Running whatever local validation is needed (builds, tests, simulators, dev servers)
- Opening a PR from the feature branch and **merging it if the confidence gate passes** — on auto-deploy repos the merge is what deploys to prod; that is included in the authorization
- Non-destructive smoke testing in prod after the deploy lands (and reverting main if it fails)

## What it does NOT authorize

- OTA releases, native app builds, app-store submissions, package/CLI/plugin version bumps — these are separate authorizations even if the change just shipped to main
- Manual deploy commands (e.g. a `deploy --prod`) on an auto-deploy repo — it ships via the merge itself
- Destructive ops (force-push over others' work, dropping data, deleting branches not yours)

## Workflow

1. **Read the repo's CLAUDE.md first.** Sessions often start a directory up and `cd` in, so it is not always auto-loaded. It documents the env gotchas, deploy behaviour, and content-surface locations. The validation/prep/smoke/gc scripts are now invoked through `dev-flow` verbs that read the repo's `.workflow.json`; if no manifest exists yet, run `dev-flow doctor --fix` (or `dev-flow init`) to scaffold one by inference, then sanity-check it against `CLAUDE.md`'s named scripts. Scaffold it in the main checkout (or commit it on the feature branch so it lands with the PR) — a `.workflow.json` created transiently inside a throwaway worktree is lost when that worktree is `gc`'d.

2. **Make a worktree off latest main.** Work goes in a worktree branched from fresh `origin/main` (or `origin/master`), never from the parked checkout's possibly-stale HEAD — that's the whole reason for the worktree. Use **EnterWorktree** (or `dev-flow prep`) to create and enter it. Then bootstrap IN the worktree — **`dev-flow prep`** for repo-specific extras (drafty: `bash web/scripts/worktree-prep.sh`), and **`dev-up`** when you need a running server; both pick the package manager from the lockfile and seed gitignored `.env*` from the main checkout minus admin tokens (worktrees don't inherit env files). `dev-flow prep` is a clean no-op when the manifest has no `prep` hook. The *why* matters: the lockfile beats your global default — a wrong-tool install resolves drifted deps and manufactures phantom type errors. All validation runs in the worktree too. **Never merge the branch into the local main checkout at exit** — that checkout is stale and often parked on other WIP, and the exit-time local merge is where every merge-conflict incident comes from. The branch ships via a PR merged server-side (step 7), never via a local merge into your checkout. (Mobile: switching a Metro bundler between worktrees has its own tool — see the `dev-up` skill; native builds only ever run from the main checkout and are separate authorizations anyway.)

3. **Implement the plan.** Small incremental commits, follow existing repo patterns.

4. **Refresh the content surfaces — changelog + docs autonomously, articles intentionally.** Do this BEFORE validation so the content edits ride the same commit and the same gate run (no second push, no second gate). If the repo has user-facing content surfaces (the manifest's `content` block, or the locations CLAUDE.md names), check each against the ship:
   - **Changelog — autonomous, every user-visible ship.** If the change is something a user would notice (feature, behaviour change, visible fix), add a curated entry now (the repo names its changelog source). Internal-only ships (tests, gates, refactors, infra) get no entry — don't pad it.
   - **KB / help center — autonomous, every ship.** Check whether the ship makes any existing article stale (instructions, flag names, flows) and fix it; if the ship adds a user-facing capability people will ask "how do I…" about, write the new question-titled article in the established style.
   - **Articles — intentional, never autonomous.** Long-form editorial is a deliberate product/voice decision — do NOT auto-write or auto-edit one as part of a ship. If the ship is article-worthy (new wedge, new workflow story), say so in the report or park it, don't write it.
   This content refresh is IN scope of the ship authorization — it is not "adjacent work". Typed content registries get covered by the gate's typecheck.

5. **Validate locally — the confidence gate (`dev-flow gate`).** Run it all from inside the worktree (bootstrapped per step 2). `dev-flow gate` (drafty: `bash web/scripts/ship-check.sh`) is REQUIRED and a nonzero exit means DO NOT ship. Need a running dev server? In a worktree, seed `.env*` from the main checkout (gitignored, so worktrees don't have them otherwise) and serve it — see the `dev-up` skill for a one-verb version with a public URL; `dev-down` when finished. All that apply:
   - Typecheck + lint + unit tests
   - Production build passes — but never run a production build while a dev server is running in the same checkout if your bundler shares the build dir (it corrupts the cache, e.g. Turbopack's `.next`). (drafty's gate stops a dev server on the main checkout itself and restores it on exit.)
   - **Mechanical regression gates** — `dev-flow gate` runs the repo's scripted invariant suites; they catch the regressions a manual pass is structurally blind to (a leak-freeness break still *looks* like a working gate). The drafty reference gate (`ship-check.sh`) runs typecheck + mints a throwaway Instant app and pushes working-tree schema/perms to it + the live in-process invariant suites + a production build with an HTTP smoke of every public op + a schema-drift preflight vs prod (and a conditional headless-Chrome render gate when the diff touches the render pipeline) — all repo-internal to the gate. Run `dev-flow gate` before every merge.
   - **Grow the gate as you ship.** If the ship adds a flow with mechanical invariants (who-can-see-what, key/token validation, leak-free no-ops, single-use/expiry), add tests for them to the gate IN THE SAME SHIP — that's what makes the next autonomous ship safe, and manual verification today protects nothing tomorrow.
   - **Visual/UI work: render it and look.** Screenshot the running app/page at a real viewport. Compile-passes ≠ looks-right. Keep the screenshots — they become the proof in the report and the PR body (steps 7, 11).
   - **Exercise the actual happy path in its real runtime — not a convenient proxy for it.** The minimum bar before merge is the feature's main flow, run for real on the surface a user actually hits, driven by the real tool: **agent-browser** (or the `run` skill) for web/PWA against the running dev server, **argent** for the iOS simulator / Android emulator. If correctness depends on the client environment — PWA standalone, iOS Safari/WebKit, a specific browser, service workers, visibility/lifecycle events (visibilitychange/pageshow/focus), offline — verify it *there*. A scripted gate and "render and look" are structurally blind to runtime behaviour: a server/build/contract gate can be fully green while the real trigger never fires on the real device. A synthetic event dispatch in headless desktop proves the logic, not the trigger. You don't need exhaustive edge cases — you need the real happy path actually exercised once, on the real surface, *before* the merge.
   - **Mobile or PWA surface — even in a web app**: run it on the simulator/emulator via **argent** and exercise the changed flow on the actual surface (a web feature whose target is the iPhone PWA / mobile Safari gets driven in iOS Safari via argent, not just headless desktop Chrome).
   - Anything the repo's CLAUDE.md names as the test harness.

6. **Ship decision.**
   - **Confident, no regression risk** → open the PR and merge it.
   - **Not confident, or anything is flaky/unverifiable** → open the PR (which pushes the branch) but do NOT merge it, and report exactly what passed, what's uncertain, and why. Don't hedge-ship. On a soft trigger (see Triggers), the merge waits for confirmation regardless.

7. **Open a PR, then merge it — server-side, never into the local checkout.** This replaces the old direct-push-to-main step (John approved PR-then-merge). The branch ships through a PR that GitHub merges server-side, so the local stale checkout is never touched.
   - Before opening, absorb main's drift INTO the branch so any conflicts resolve where the feature context lives, not at the merge — `dev-flow pr open` does this re-sync as part of pushing. If the absorb pulled changes, re-run `dev-flow gate` on what changed before merging.
   - `dev-flow pr open --title "<title>" [--body-file <f>] [--canvas <drafty-url>] [--proof <screenshot> ...]` pushes the current branch and opens the PR; the body embeds the drafty proof-canvas link + proof images + a generated summary, and it prints the PR url.
   - `dev-flow pr merge` merges the PR server-side — THIS is the deploy trigger.
   - The PR body carries the proof: the drafty canvas link (step 10) and the screenshots from step 5, plus a short summary of what changed and how it was validated.
   - **The branch is NEVER merged into the local main checkout** — `gh` merges it server-side on the remote. The local checkout stays exactly as found. This is the property that preserves the no-local-merge discipline of step 2 while still landing the work.
   - A non-fast-forward / "not mergeable" rejection means main moved under you: re-sync the branch onto `origin/main`, re-run `dev-flow gate`, and retry `dev-flow pr merge`. Never force-push main, and never touch parked WIP.

8. **Verify the deploy, then smoke test prod when the change warrants it (`dev-flow smoke`).**
   - Report the merged PR + the commit on main. Confirm the new deploy is actually serving (deploy status or commit hash on the live site) before testing — otherwise the smoke test exercises the old build. A bounded wait for the deploy is fine; no endless polling loops.
   - **Run `dev-flow smoke` first** (drafty: `bash web/scripts/prod-smoke.sh`, forward args like `--email` when the ship touched mail/invite paths) — it covers the prod-only failure classes (env vars, platform config, a forgotten schema push) in seconds, read-only. If the manifest has no `smoke` hook, `dev-flow smoke` notes the skip; add manual checks for what it doesn't cover.
   - **Smoke test in prod for high-usage / high-risk changes**: anything touching auth/login, payments/subscriptions, publish/save paths, core APIs, the home page or primary entry surface, or data-shape changes (migrations, schema, serialization). Exercise the changed flow plus the one or two highest-traffic adjacent flows on the live site/app.
   - Low-risk changes (copy tweaks, isolated pages, styling on minor surfaces) → a single load-and-look of the affected URL is enough; don't manufacture a test pass.
   - **Prod smoke tests are non-destructive**: read-only checks and test accounts only; never mutate real user data; any test artifact created must be narrowly identifiable (e.g. a `TEST-` prefix) and cleaned up immediately after.
   - If the smoke test fails: revert main (a revert commit / a revert PR, not a force-push), confirm the revert deployed, then report the failure.

9. **Clean up the worktree (`dev-flow gc`).** First confirm the work actually landed — it must be an ancestor of `origin/main` — then `dev-down` whatever the dev server started, `ExitWorktree` (remove), and `dev-flow gc` (drafty: `bash web/scripts/worktrees-gc.sh`; falls back to dev-up's generic `worktrees-gc.sh` when the manifest has no `gc` hook) to sweep any landed + clean + idle worktrees from past sessions, never live ones — gc already encodes the landed-ancestor check as its prune predicate. Don't leave dev-ship worktrees lying around — they cause the drift problems the hygiene rules exist for. Leave the main checkout exactly as found (same parked branch, WIP untouched — no merge into it, ever).

10. **Save what you learned.** Persist anything non-obvious from the ship for next time: gotchas hit (build quirks, env traps, flaky steps), decisions made along the way, and a SHIPPED note for significant features (what + date + open threads). Skip what the repo/git history already records. Update existing notes rather than duplicating.

11. **Report.** State what shipped (PR url + merge commit, branch → main, deploy state), what was validated and how (including `dev-flow smoke` results), and anything still pending (env vars, migrations, releases, builds). "Ready to test" only when the whole path is actually live — if something is still pending, name the blocker explicitly. **Visual work: include the screenshots you took as proof** (and the drafty proof-canvas link) — verifying it for yourself without showing the user is an incomplete report.

The point isn't speed for its own sake. It's that shipping stops being a chore you work up the patience for and becomes a decision you make the moment you're confident.
