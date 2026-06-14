---
name: ship-it
description: A standing ship authorization. Use when you say "ship it", "ship this", "execute and ship", or "ship it to main" about work planned or discussed in the current session — that is the full no-reconfirmation authorization. ALSO use on a generic go-word ("execute it", "do it", "do it now", "let's go", "go ahead", "run it") about a code-change plan discussed in session whose natural endpoint is shipping — but then follow the Triggers section: confirm scope before pushing to main. It means — execute the agreed plan in a worktree, test and validate everything locally, and if confident there is no regression risk, push to main. NOT for go-words about non-shipping work (sending messages, running scripts, drafting), and NOT for product release flows that have their own process and authorization (app-store submissions, OTA releases, package/CLI/plugin version bumps — each a separate authorization).
---

# Ship it

"Ship it" is a single end-to-end authorization: execute the plan already discussed, validate it locally, and push to main if confident. Do not re-ask permission per step. The plan discussed in the conversation is the scope — "ship it" does not authorize adjacent work (refactors, READMEs, wiring) beyond it. One standing exception: the content-surface refresh in step 4 (changelog + docs) is part of every ship, not adjacent work.

**Where the project-specific bits live.** This skill is the universal method. The *bindings* — which gate script to run, where the changelog/KB live, the deploy behaviour, env gotchas — live in each repo's `CLAUDE.md`, not here. Step 1 is read it first; everywhere this skill says "the repo's X script", that repo's `CLAUDE.md` names the actual file.

## Triggers — two tiers

**Hard trigger** — "ship it", "ship this", "ship to main", "execute and ship": full authorization, no reconfirmation. Run the whole workflow including the push.

**Soft trigger** — generic go-words ("execute it", "do it", "do it now", "let's go", "go ahead", "run it") about a code-change plan discussed in session whose natural endpoint is shipping:

1. First check what's actually being approved. If the go-word refers to non-shipping work (send a message, run a script, draft something, a single command), this skill does not apply — just do that thing.
2. If it is a ship-shaped plan: state the interpretation in ONE short message — scope of the change + "this ends with a push to main (deploys to prod); say stop if that's not what you meant" — then start the reversible work immediately (worktree, implement, validate). Don't block waiting; the implementation runway is the objection window.
3. **The push to main needs confirmation on this tier.** If the user is responsive (live session, or a clarifying question is viable), confirm before pushing. If unattended and no reply by push time: stop at the validated state, push the feature branch only (NOT main), and ask — a soft trigger never merges to main unconfirmed.

This keeps "ship it" fast (zero friction) while go-words cost at most one confirmation at the only irreversible step.

## What it authorizes

- Creating a worktree and implementing the agreed plan in it
- Running whatever local validation is needed (builds, tests, simulators, dev servers)
- Pushing to main **if** the confidence gate passes — on auto-deploy repos this deploys to prod; that is included in the authorization
- Non-destructive smoke testing in prod after the deploy lands (and reverting main if it fails)

## What it does NOT authorize

- OTA releases, native app builds, app-store submissions, package/CLI/plugin version bumps — these are separate authorizations even if the change just shipped to main
- Manual deploy commands (e.g. a `deploy --prod`) on an auto-deploy repo — it ships via the push itself
- Destructive ops (force-push over others' work, dropping data, deleting branches not yours)

## Workflow

1. **Read the repo's CLAUDE.md first.** Sessions often start a directory up and `cd` in, so it is not always auto-loaded. It documents the validation harness, env gotchas, deploy behaviour, and the names of the gate/smoke/prep scripts this skill refers to generically.

2. **Make a worktree off latest main.** "Ship it" is the explicit ask — run `git fetch origin` first so `origin/main` (or `origin/master`) is current, then create the worktree branched from origin's default branch, NOT from the current checkout's possibly-parked HEAD:
   ```sh
   git fetch origin
   git worktree add -b <feature> ../<repo>-<feature> origin/main
   ```
   The worktree is self-contained: bootstrap it IN the worktree — **if the repo has a worktree-prep script, run that** (correct package manager, env seeding minus admin tokens, generated env); otherwise install with the package manager the repo's LOCKFILE names (`bun.lock` → bun, `pnpm-lock.yaml` → pnpm — the lockfile beats your global default; a wrong-tool install resolves drifted deps and manufactures phantom type errors). Worktrees don't inherit gitignored `.env*` — seed them from the main checkout. All validation runs in the worktree too. **Never merge the branch into the local main checkout at exit** — that checkout is stale and often parked on other WIP, and the exit-time local merge is where every merge-conflict incident comes from; the branch ships straight to remote main in step 7. (Mobile: switching a Metro bundler between worktrees has its own tool — see the `dev-up` skill; native builds only ever run from the main checkout and are separate authorizations anyway.)

3. **Implement the plan.** Small incremental commits, follow existing repo patterns.

4. **Refresh the content surfaces — changelog + docs autonomously, articles intentionally.** Do this BEFORE validation so the content edits ride the same commit and the same gate run (no second push, no second gate). If the repo has user-facing content surfaces, check each against the ship:
   - **Changelog — autonomous, every user-visible ship.** If the change is something a user would notice (feature, behaviour change, visible fix), add a curated entry now (the repo names its changelog source). Internal-only ships (tests, gates, refactors, infra) get no entry — don't pad it.
   - **KB / help center — autonomous, every ship.** Check whether the ship makes any existing article stale (instructions, flag names, flows) and fix it; if the ship adds a user-facing capability people will ask "how do I…" about, write the new question-titled article in the established style.
   - **Articles — intentional, never autonomous.** Long-form editorial is a deliberate product/voice decision — do NOT auto-write or auto-edit one as part of a ship. If the ship is article-worthy (new wedge, new workflow story), say so in the report or park it, don't write it.
   This content refresh is IN scope of the ship authorization — it is not "adjacent work". Typed content registries get covered by the gate's typecheck.

5. **Validate locally — the confidence gate.** Run it all from inside the worktree (bootstrapped per step 2). Need a running dev server? In a worktree, seed `.env*` from the main checkout (gitignored, so worktrees don't have them otherwise) and serve it — see the `dev-up` skill for a one-verb version with a public URL; `dev-down` when finished. All that apply:
   - Typecheck + lint + unit tests
   - Production build passes — but never run a production build while a dev server is running in the same checkout if your bundler shares the build dir (it corrupts the cache, e.g. Turbopack's `.next`)
   - **Mechanical regression gates** — run the repo's scripted invariant suites; they catch the regressions a manual pass is structurally blind to (a leak-freeness break still *looks* like a working gate). The repo names its gate script in CLAUDE.md (e.g. a `ship-check.sh` that runs typecheck + live invariant suites + production build + an HTTP smoke of every public endpoint + a schema-drift preflight). Run it before every push to main.
   - **Grow the gate as you ship.** If the ship adds a flow with mechanical invariants (who-can-see-what, key/token validation, leak-free no-ops, single-use/expiry), add tests for them to the gate IN THE SAME SHIP — that's what makes the next autonomous ship safe, and manual verification today protects nothing tomorrow.
   - **Visual/UI work: render it and look.** Screenshot the running app/page at a real viewport. Compile-passes ≠ looks-right. Keep the screenshots — they become the proof in the report (step 11).
   - **Exercise the actual happy path in its real runtime — not a convenient proxy for it.** The minimum bar before push is the feature's main flow, run for real on the surface a user actually hits. If correctness depends on the client environment — PWA standalone, iOS Safari/WebKit, a specific browser, service workers, visibility/lifecycle events (visibilitychange/pageshow/focus), offline — verify it *there*. A scripted gate and "render and look" are structurally blind to runtime behaviour: a server/build/contract gate can be fully green while the real trigger never fires on the real device. A synthetic event dispatch in headless desktop proves the logic, not the trigger. You don't need exhaustive edge cases — you need the real happy path actually exercised once, on the real surface, *before* the push.
   - **Mobile or PWA surface — even in a web app**: run it on the simulator/emulator and exercise the changed flow on the actual surface (a web feature whose target is the iPhone PWA / mobile Safari gets driven in iOS Safari, not just headless desktop Chrome).
   - Anything the repo's CLAUDE.md names as the test harness.

6. **Ship decision.**
   - **Confident, no regression risk** → push to main.
   - **Not confident, or anything is flaky/unverifiable** → push the branch, do NOT merge to main (on auto-deploy repos the merge is what makes it deployable), and report exactly what passed, what's uncertain, and why. Don't hedge-ship.

7. **Push to main — directly from the worktree, after syncing it.** Do NOT merge into the local checkout first (it's stale and often parked on other WIP — merging or `git merge --ff-only` from there ships into THAT branch, not main, or conflicts against drift). The whole exit happens in the worktree:
   ```sh
   git fetch origin
   git merge origin/main --no-edit    # absorb main's drift INTO the branch — resolve conflicts here, where the feature context lives
   # if the merge brought in changes, re-run the relevant validation before pushing
   git push origin HEAD:main          # ship straight to remote main
   git branch -f main origin/main     # sync local main afterwards (ONLY if main isn't checked out anywhere)
   ```
   If the push is rejected non-fast-forward (someone else landed on main in between): fetch, merge `origin/main` again, re-validate what changed, retry the push. Never force-push main, and never touch parked WIP.

8. **Verify the deploy, then smoke test prod when the change warrants it.**
   - Report the pushed commit. Confirm the new deploy is actually serving (deploy status or commit hash on the live site) before testing — otherwise the smoke test exercises the old build. A bounded wait for the deploy is fine; no endless polling loops.
   - **If the repo has a scripted prod smoke, run it first** — it covers the prod-only failure classes (env vars, platform config, a forgotten schema push) in seconds. Then add manual checks only for what the script doesn't cover.
   - **Smoke test in prod for high-usage / high-risk changes**: anything touching auth/login, payments/subscriptions, publish/save paths, core APIs, the home page or primary entry surface, or data-shape changes (migrations, schema, serialization). Exercise the changed flow plus the one or two highest-traffic adjacent flows on the live site/app.
   - Low-risk changes (copy tweaks, isolated pages, styling on minor surfaces) → a single load-and-look of the affected URL is enough; don't manufacture a test pass.
   - **Prod smoke tests are non-destructive**: read-only checks and test accounts only; never mutate real user data; any test artifact created must be narrowly identifiable (e.g. a `TEST-` prefix) and cleaned up immediately after.
   - If the smoke test fails: revert main (a revert commit, not a force-push), confirm the revert deployed, then report the failure.

9. **Clean up the worktree.** First confirm the work actually landed: `git fetch origin && git merge-base --is-ancestor HEAD origin/main` must succeed — only then stop anything the dev server started, remove the worktree (`git worktree remove` + `git worktree prune`), and delete the feature branch since its commits are on main. If the repo has a worktree GC script, run it too (prunes landed + clean + idle worktrees, never live sessions), so strays from past sessions don't accumulate. Don't leave ship-it worktrees lying around — they cause the drift problems the hygiene rules exist for. Leave the main checkout exactly as found (same parked branch, WIP untouched — no merge into it, ever).

10. **Save what you learned.** Persist anything non-obvious from the ship for next time: gotchas hit (build quirks, env traps, flaky steps), decisions made along the way, and a SHIPPED note for significant features (what + date + open threads). Skip what the repo/git history already records. Update existing notes rather than duplicating.

11. **Report.** State what shipped (commit, branch → main, deploy state), what was validated and how (including prod smoke-test results), and anything still pending (env vars, migrations, releases, builds). "Ready to test" only when the whole path is actually live — if something is still pending, name the blocker explicitly. **Visual work: include the screenshots you took as proof** — verifying it for yourself without showing the user is an incomplete report.

The point isn't speed for its own sake. It's that shipping stops being a chore you work up the patience for and becomes a decision you make the moment you're confident.
