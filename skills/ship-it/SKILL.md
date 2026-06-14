---
name: ship-it
description: A standing ship authorization. When you say "ship it" about a plan discussed in the session, the agent executes it in a git worktree, validates it locally, and pushes to main — but only if there's no regression risk, with no per-step re-asking. Covers two trigger tiers (a hard "ship it" that runs the whole flow including the push, and soft go-words that still confirm before the irreversible push), the local confidence gate, pushing straight to remote main from the worktree, prod smoke-testing, and cleanup. Triggers on "ship it", "ship this", "ship to main", "execute and ship", and on go-words ("do it", "let's go", "go ahead", "run it") about a code-change plan whose natural endpoint is shipping.
---

# Ship it

"Ship it" is a single end-to-end authorization: execute the plan already discussed, validate it locally, and push to main if confident. Don't re-ask permission per step. The plan discussed in the conversation is the scope — "ship it" doesn't authorize adjacent work (refactors, READMEs, wiring) beyond it. One standing exception: refreshing the user-facing content surfaces a ship touches (changelog, help docs) is part of the ship, not adjacent work.

## Triggers — two tiers

**Hard trigger** — "ship it", "ship this", "ship to main", "execute and ship": full authorization, no reconfirmation. Run the whole workflow including the push.

**Soft trigger** — generic go-words ("execute it", "do it", "do it now", "let's go", "go ahead", "run it") about a code-change plan whose natural endpoint is shipping:

1. First check what's actually being approved. If the go-word refers to non-shipping work (send a message, run a script, draft something, a single command), this skill doesn't apply — just do that thing.
2. If it's a ship-shaped plan: state the interpretation in ONE short message — the scope of the change + "this ends with a push to main (deploys to prod); say stop if that's not what you meant" — then start the reversible work immediately (worktree, implement, validate). Don't block waiting; the implementation runway is the objection window.
3. **The push to main needs confirmation on this tier.** If the user is responsive, confirm before pushing. If unattended with no reply by push time: stop at the validated state, push the feature branch only (NOT main), and ask — a soft trigger never merges to main unconfirmed.

This keeps "ship it" fast (zero friction) while go-words cost at most one confirmation at the only irreversible step.

## What it authorizes

- Creating a worktree and implementing the agreed plan in it
- Running whatever local validation is needed (builds, tests, dev servers)
- Pushing to main **if** the confidence gate passes — on auto-deploy repos this deploys to prod; that's included in the authorization
- Non-destructive smoke testing in prod after the deploy lands (and reverting main if it fails)

## What it does NOT authorize

- Release flows with their own sign-off — app-store submissions, OTA updates, package/CLI/plugin version bumps — even when the change just shipped to main
- Manual deploy commands on an auto-deploy repo — it ships via the push itself
- Destructive ops (force-pushing over others' work, dropping data, deleting branches that aren't yours)

## Workflow

1. **Read the repo's CLAUDE.md / contributing docs first.** They usually document the validation harness, env gotchas, and deploy behavior — and aren't always auto-loaded.

2. **Make a worktree off the latest main.** Run `git fetch origin` first so `origin/main` (or `origin/master`) is current, then branch the worktree from origin's default branch — NOT from the current checkout's possibly-parked HEAD:
   ```sh
   git fetch origin
   git worktree add -b <feature> ../<repo>-<feature> origin/main
   ```
   Bootstrap the worktree in place: if the repo has a worktree-prep script, run it; otherwise install with the package manager the repo's LOCKFILE names (`bun.lock` → bun, `pnpm-lock.yaml` → pnpm — the lockfile beats your global default; a wrong-tool install resolves drifted deps and manufactures phantom type errors). Worktrees don't inherit gitignored `.env*` files — seed them from the main checkout. Leave the main checkout and its WIP untouched; **never merge the branch into it at the end** — that stale checkout is where merge conflicts come from. The branch ships straight to remote main in step 7.

3. **Implement the plan.** Small incremental commits, follow the repo's existing patterns.

4. **Refresh the user-facing content surfaces the ship touches — in the same pass.** Do this BEFORE validation so the edits ride the same commit and the same gate run.
   - **Changelog** — for anything a user would notice (feature, behavior change, visible fix), add a curated entry. Internal-only ships (tests, refactors, infra) get none — don't pad it.
   - **Help / docs** — fix any doc the ship makes stale (instructions, flag names, flows); if it adds a user-facing capability, write the doc people will search for.
   - **Long-form articles** stay a deliberate, separate decision — never auto-written as part of a ship. If the ship is article-worthy, flag it instead of writing it.

5. **Validate locally — the confidence gate.** Run it all from inside the worktree. All that apply:
   - Typecheck + lint + tests
   - The production build passes — but don't run a production build while a dev server is running in the same checkout if your bundler shares the build directory (it can corrupt the cache)
   - **Mechanical regression gates** — run the repo's scripted invariant suites; they catch the regressions a manual pass is structurally blind to (a broken invariant can still *look* like a passing gate)
   - **Grow the gate as you ship.** If the ship adds a flow with mechanical invariants (who-can-see-what, token validation, single-use / expiry), add tests for them in the same ship — that's what makes the next autonomous ship safe; manual verification today protects nothing tomorrow.
   - **Visual / UI work: render it and look.** Screenshot the running page at a real viewport. Compile-passes ≠ looks-right.
   - **Exercise the real happy path in its real runtime — not a convenient proxy.** The minimum bar before push is the feature's main flow, run for real on the surface a user actually hits. If correctness depends on the client environment (PWA standalone, iOS Safari / WebKit, a specific browser, service workers, visibility / lifecycle events, offline), verify it *there* — a green server/build gate is blind to a trigger that never fires on the real device.

6. **Ship decision.**
   - **Confident, no regression risk** → push to main.
   - **Not confident, or anything flaky / unverifiable** → push the branch, do NOT merge to main (on auto-deploy repos the merge is what makes it deployable), and report exactly what passed, what's uncertain, and why. Don't hedge-ship.

7. **Push to main — directly from the worktree, after syncing it.** Don't merge into the local checkout first (it's stale and often parked on other WIP — merging from there ships into THAT branch, or conflicts against drift). The whole exit happens in the worktree:
   ```sh
   git fetch origin
   git merge origin/main --no-edit    # absorb main's drift INTO the branch — resolve conflicts here, where the feature context lives
   # if the merge brought in changes, re-run the relevant validation before pushing
   git push origin HEAD:main          # ship straight to remote main
   ```
   If the push is rejected non-fast-forward (someone landed on main in between): fetch, merge `origin/main` again, re-validate what changed, retry the push. Never force-push main, and never touch parked WIP.

8. **Verify the deploy, then smoke test prod when the change warrants it.**
   - Confirm the new deploy is actually serving (deploy status, or the commit hash on the live site) before testing — otherwise the smoke test exercises the old build. A bounded wait for the deploy is fine; no endless polling loops.
   - **If the repo has a scripted prod smoke, run it first** — it covers the prod-only failure classes (env vars, platform config, a forgotten schema push) in seconds. Then add manual checks only for what the script doesn't cover.
   - **Smoke test for high-usage / high-risk changes**: anything touching auth/login, payments / subscriptions, publish / save paths, core APIs, the home page or primary entry surface, or data-shape changes (migrations, schema, serialization). Exercise the changed flow plus the one or two highest-traffic adjacent flows.
   - Low-risk changes (copy tweaks, isolated pages, minor styling) → a single load-and-look of the affected URL is enough; don't manufacture a test pass.
   - **Prod smoke tests are non-destructive**: read-only checks and test accounts only; never mutate real user data; any test artifact created must be narrowly identifiable (e.g. a `TEST-` prefix) and cleaned up immediately.
   - If the smoke test fails: revert main (a revert commit, not a force-push), confirm the revert deployed, then report the failure.

9. **Clean up the worktree.** First confirm the work actually landed — `git fetch origin && git merge-base --is-ancestor HEAD origin/main` must succeed — then stop any dev server you started, remove the worktree (`git worktree remove` + `git worktree prune`), and delete the feature branch since its commits are on main. Leave the main checkout exactly as found (same parked branch, WIP untouched — no merge into it, ever).

10. **Report.** State what shipped (commit, branch → main, deploy state), what was validated and how (including prod smoke-test results), and anything still pending (env vars, migrations, releases, builds). "Ready to test" only when the whole path is actually live — if something is still pending, name the blocker explicitly. For visual work, include the screenshots you took as proof.

The point isn't speed for its own sake. It's that shipping stops being a chore you work up the patience for and becomes a decision you make the moment you're confident.
