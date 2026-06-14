---
name: ship-it
description: John's standing ship authorization. Use when John says "ship it", "ship this", "execute and ship", or "ship it to main" about work planned or discussed in the current session - that is the full no-reconfirmation authorization. ALSO use when John says a generic go-word ("execute it", "do it", "do it now", "let's go", "go ahead", "run it") about a code-change plan discussed in session whose natural endpoint is shipping - but then follow the Triggers section: confirm scope before pushing to main. It means - execute the agreed plan in a worktree, test and validate everything locally, and if confident there is no regression risk, push to main. NOT for go-words about non-shipping work (sending messages, running scripts, drafting), and NOT for product release flows that have their own skills/authorization - subs.rip CLI (subsrip-release), clove releases (/release), recipes.im OTA releases (separate authorization each), drafty plugin releases (version-bump flow).
---

# Ship it

"Ship it" is a single end-to-end authorization: execute the plan already discussed, validate it locally, and push to main if confident. Do not re-ask permission per step. The plan discussed in the conversation is the scope — "ship it" does not authorize adjacent work (refactors, READMEs, wiring) beyond it. One standing exception: the content-surface refresh in step 4 (changelog + KB) is part of every ship, not adjacent work.

## Triggers — two tiers

**Hard trigger** — "ship it", "ship this", "ship to main", "execute and ship": full authorization, no reconfirmation. Run the whole workflow including the push.

**Soft trigger** — generic go-words ("execute it", "do it", "do it now", "let's go", "go ahead", "run it") about a code-change plan discussed in session whose natural endpoint is shipping:

1. First check what's actually being approved. If the go-word refers to non-shipping work (send a message, run a script, draft something, a single command), this skill does not apply — just do that thing.
2. If it is a ship-shaped plan: state the interpretation in ONE short message — scope of the change + "this ends with a push to main (deploys to prod); say stop if that's not what you meant" — then start the reversible work immediately (worktree, implement, validate). Don't block waiting; the implementation runway is the objection window.
3. **The push to main needs confirmation on this tier.** If John is responsive (live session, or AskUserQuestion is viable), confirm before pushing. If unattended and no reply by push time: stop at the validated state, push the feature branch only (NOT main), and ask — a soft trigger never merges to main unconfirmed.

This keeps "ship it" fast (zero friction) while go-words cost at most one confirmation at the only irreversible step.

## What it authorizes

- Creating a worktree and implementing the agreed plan in it
- Running whatever local validation is needed (builds, tests, simulators, dev servers)
- Pushing to main **if** the confidence gate passes — on auto-deploy repos this deploys to prod; that is included in the authorization
- Non-destructive smoke testing in prod after the deploy lands (and reverting main if it fails)

## What it does NOT authorize

- OTA releases, EAS builds, app-store submissions, plugin/CLI version bumps — these are separate authorizations even if the change just shipped to main
- `vercel deploy` / `vercel --prod` — never; auto-deploy repos ship via the push itself
- Destructive ops (force-push over others' work, dropping data, deleting branches not yours)

## Workflow

1. **Read the repo's CLAUDE.md first.** Sessions start in ~/Projects and cd in, so it is not auto-loaded. It usually documents validation harnesses, env gotchas, and deploy behavior.

2. **Make a worktree off latest main.** "Ship it" is the explicit ask — run `git fetch origin` first so `origin/main` (or `origin/master`) is current, then create the worktree (EnterWorktree; the default `worktree.baseRef: fresh` branches from origin's default branch, NOT from the checkout's possibly-parked HEAD — keep it that way) and execute the plan there, leaving the main checkout and its WIP untouched. The worktree is self-contained: bootstrap it IN the worktree — **if the repo has a worktree-prep script, run that** (drafty.im: `bash web/scripts/worktree-prep.sh` — correct package manager, env seeding minus admin tokens, generated TS env); otherwise install with the package manager the repo's LOCKFILE names (bun.lock → bun, pnpm-lock.yaml → pnpm — the lockfile beats the global pnpm default; a wrong-tool install resolves drifted deps and manufactures phantom type errors). All validation runs there too. **Never merge the branch into the local main checkout at exit** — that checkout is stale and usually parked on John's WIP branch, and the exit-time local merge is where every agent merge-conflict incident has come from (2026-06-11/12); the branch ships straight to remote main in step 7 instead. Mobile caveats: Metro against a worktree goes through `metro-takeover.sh` (dev-up skill); EAS builds only ever run from the main checkout and are separate authorizations anyway.

3. **Implement the plan.** Small incremental commits, follow existing repo patterns.

4. **Refresh the content surfaces — changelog + KB autonomously, articles intentionally.** Do this BEFORE validation so the content edits ride the same commit and the same gate run (no second push, no second gate). If the repo has user-facing content surfaces, check each against the ship:
   - **Changelog — autonomous, every user-visible ship.** If the change is something a user would notice (feature, behavior change, visible fix), add a curated entry now. drafty.im: use the repo's `changelog` skill → `web/src/content/changelog.ts` (read by `/changelog` and `drafty changelog`). Internal-only ships (tests, gates, refactors, infra) get no entry — don't pad it.
   - **KB / help center — autonomous, every ship.** Check whether the ship makes any existing article stale (instructions, screenshots-in-words, flag names, flows) and fix it; if the ship adds a user-facing capability people will ask "how do I…" about, write the new question-titled article in the established style. drafty.im: `web/src/content/kb/` + typed registry `web/src/content/kb.ts`.
   - **Articles — intentional, never autonomous.** Long-form editorial (drafty.im: `web/src/content/articles/`) is a deliberate product/voice decision — do NOT auto-write or auto-edit one as part of a ship. If the ship is article-worthy (new wedge, new workflow story), say so in the report or park it on the action canvas with a one-line angle.
   This content refresh is IN scope of the ship authorization — it is not "adjacent work". Content registries are typed, so the gate's typecheck covers them.

5. **Validate locally — the confidence gate.** Run it all from inside the worktree (bootstrapped per step 2 — repo prep script or lockfile-named package manager). Need a running dev server? Use `dev-up` (dev-up skill), not bare `pnpm dev` — in a worktree it seeds `.env*` from the main checkout (gitignored, so worktrees don't have them otherwise), installs if needed, and serves under a `<branch>-<name>` portless route with a public URL; `dev-down` when finished. All that apply:
   - Typecheck + lint + unit tests
   - Production build passes (`pnpm build` or repo equivalent) — but never run `next build` while a dev server is running in the same checkout (corrupts `.next`)
   - **Mechanical regression gates** — run the repo's scripted invariant suites; they catch the regressions a manual pass is structurally blind to (a leak-freeness break still *looks* like a working gate). drafty.im: `bash web/scripts/ship-check.sh` (~6-8 min, REQUIRED before every push to main — typecheck + live perms/ops/front-door suites + production build + HTTP smoke of every public op + schema-drift preflight; needs the checkout's dev server down: `dev-down` → gate → `dev-up`). Other repos: whatever CLAUDE.md names.
   - **Grow the gate as you ship.** If the ship adds a flow with mechanical invariants (who-can-see-what, key/token validation, leak-free no-ops, single-use/expiry), add tests for them to the gate IN THE SAME SHIP — that's what makes the next autonomous ship safe, and manual verification today protects nothing tomorrow.
   - **Visual/UI work: render it and look.** Screenshot the running app/page at a real viewport. Compile-passes ≠ looks-right. Keep the screenshots — they become the proof image in the report (step 11).
   - **Exercise the actual happy path in its real runtime — not a convenient proxy for it.** The minimum bar before push is the feature's main flow, run for real on the surface a user actually hits. If correctness depends on the client environment — PWA standalone, iOS Safari/WebKit, a specific browser, service workers, visibility/lifecycle events (visibilitychange/pageshow/focus), offline — verify it *there*. `ship-check` and "render and look" are structurally blind to runtime behavior: a server/build/contract gate can be fully green while the real trigger never fires on the real device. A synthetic event dispatch in headless desktop proves the logic, not the trigger. We don't need exhaustive edge cases — we need the real happy path actually exercised once, on the real surface, *before* the push (not after someone asks).
   - Mobile **or PWA surface — even in a web app**: run it on the simulator/emulator via Argent and exercise the changed flow on the actual surface (a web feature whose target is the iPhone PWA / mobile Safari gets driven in iOS Safari via Argent, not just headless desktop Chrome)
   - Anything the repo CLAUDE.md names as the test harness (e.g. drafty's e2e setup script)

6. **Ship decision.**
   - **Confident, no regression risk** → push to main.
   - **Not confident, or anything is flaky/unverifiable** → push the branch, do NOT merge to main (on auto-deploy repos the merge is what makes it deployable), and report exactly what passed, what's uncertain, and why. Don't hedge-ship.

7. **Push to main — directly from the worktree, after syncing it.** Do NOT merge into the local checkout first (it's stale and often parked on John's WIP branch — merging or `git merge --ff-only` from there ships into THAT branch, not main, or conflicts against drift). The whole exit happens in the worktree:
   ```sh
   git fetch origin
   git merge origin/main --no-edit    # absorb main's drift INTO the branch — resolve conflicts here, where the feature context lives
   # if the merge brought in changes, re-run the relevant validation before pushing
   git push origin HEAD:main          # ship straight to remote main
   git branch -f main origin/main     # sync local main afterwards (ONLY if main isn't checked out anywhere)
   ```
   If the push is rejected non-fast-forward (another agent landed on main in between): fetch, merge `origin/main` again, re-validate what changed, retry the push. Never force-push main, and never touch John's parked WIP.

8. **Verify the deploy, then smoke test prod when the change warrants it.**
   - Report the pushed commit. Confirm the new deploy is actually serving (deploy status or commit hash on the live site) before testing — otherwise the smoke test exercises the old build. A bounded wait for the deploy is fine here; no endless polling loops.
   - **If the repo has a scripted prod smoke, run it first** — it covers the prod-only failure classes (env vars, platform config, forgot-the-schema-push) in seconds. drafty.im: `bash web/scripts/prod-smoke.sh` (read-only, ~20s). Then add manual checks only for what the script doesn't cover.
   - **Smoke test in prod for high-usage / high-risk changes**: anything touching auth/login, payments/subscriptions, publish/push/save paths, core APIs, the home page or primary entry surface, or data-shape changes (migrations, schema, serialization). Exercise the changed flow plus the one or two highest-traffic adjacent flows on the live site/app.
   - Low-risk changes (copy tweaks, isolated pages, styling on minor surfaces) → a single load-and-look of the affected URL is enough; don't manufacture a test pass.
   - **Prod smoke tests are non-destructive**: read-only checks and test accounts only; never mutate real user data; any test artifact created must be narrowly identifiable (e.g. TEST- prefix) and cleaned up immediately after.
   - If the smoke test fails: revert main (revert commit, not force-push), confirm the revert deployed, then report the failure.

9. **Clean up the worktree.** First confirm the work actually landed: `git fetch origin && git merge-base --is-ancestor HEAD origin/main` must succeed — only then stop anything dev-up started (`dev-down`), ExitWorktree with remove (or `git worktree remove` + `git worktree prune`), and delete the feature branch since its commits are on main. If the repo has a worktree GC script, run it too (drafty.im: `bash web/scripts/worktrees-gc.sh` — prunes landed+clean+idle worktrees, never live sessions), so strays from past sessions don't accumulate. Don't leave ship-it worktrees lying around — they cause the drift problems the hygiene rules exist for. Leave the main checkout exactly as found (same parked branch, WIP untouched — no merge into it, ever).

10. **Save memory.** Persist to project memory anything non-obvious learned during the ship: gotchas hit (build quirks, env traps, flaky steps), decisions made along the way, and a SHIPPED entry for significant features (what + date + open threads). Skip what the repo/git history already records. Update existing memory files rather than duplicating.

11. **Report.** State what shipped (commit, branch→main, deploy state), what was validated and how (including prod smoke test results), and anything still pending (env vars, migrations, OTA, builds). "Ready to test" only when the whole path is actually live — if something is still pending, name the blocker explicitly. **Visual work: the report MUST include a proof canvas** — use the `proof-canvas` skill (~/.claude/skills/proof-canvas) to push the verification screenshots to a private drafty canvas with story captions, put the bare URL in the report, and also send the raw PNGs via SendUserFile (inline on mobile). Verifying for yourself without showing John is an incomplete report.
