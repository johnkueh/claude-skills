---
name: dev-up
description: One-verb local dev-server + worktree QA lifecycle for any checkout (web or Expo), backed by a Cloudflare-Tunnel ngrok replacement that multiplexes many dev servers (via portless) through one wildcard subdomain. Includes `dev-up`/`dev-down`/`dev-status` (env seeding, install, portless naming, public URL), `setup.sh` (one-time machine onboarding), `add-project.sh` (per-project tunnel wiring), `metro-takeover.sh` for switching Expo Metro between git worktrees, `expo-qa.sh` (fingerprint gate that detects when a worktree needs its own dev build or the installed dev client is stale, plus `eas update --branch wt/<branch>` publish for parallel branch QA on any dev client), `worktrees-gc.sh` for pruning landed agent worktrees in any repo, and `doctor.sh` for health-checking the tunnel/portless chain. Formerly named cloudflare-tunnel-portless. Triggers on "dev-up", "spin up the dev server", "start the dev server", "test before shipping", "public URL for this worktree", "set up cloudflare tunnel", "onboard new mac to tunnel", "add project to tunnel", "ngrok replacement", "public URL for localhost", "portless", "cloudflared", "metro-takeover", "switch metro to worktree", "expo-qa", "fingerprint gate", "is the dev client valid for this branch", "publish this branch as an EAS update", "QA this worktree on my phone", "worktrees-gc", "clean up worktrees", "prune old worktrees", "tunnel doctor", or "debug caddy/portless/cloudflared".
---

# dev-up — local dev servers + worktree QA, one verb each

The day-to-day surface is the verbs: `dev-up`/`dev-down`/`dev-status` for any
checkout or worktree, `metro-takeover` + `expo-qa` for Expo QA, `worktrees-gc`
for cleanup. Underneath: a free Cloudflare Tunnel + a tiny host-preserving
proxy in front of [portless](https://github.com/vercel-labs/portless) replaces
ngrok — one persistent tunnel handles every web project under a single
wildcard subdomain (free, no timeouts, wildcard = zero per-worktree config),
Expo apps get individual ingress entries. (Formerly `cloudflare-tunnel-portless`.)

**The mechanical procedures live in scripts, not prose.** Don't reassemble
setup or wiring steps by hand — run the script; each one is idempotent and
prints what a human still has to do.

| Task | Command |
|---|---|
| Start/stop/inspect a dev server (any checkout/worktree) | `dev-up` / `dev-down` / `dev-status` |
| One-time machine onboarding | `setup.sh <domain> [--tag t] [--tunnel name]` |
| Wire a new project | `add-project.sh web [name]` or `add-project.sh expo <hostname> <port>` |
| Health-check the whole chain | `doctor.sh` |
| Swap Expo Metro to this worktree | `metro-takeover.sh` |
| Expo QA gate / EAS Update publish / client record | `expo-qa.sh gate|publish|record` |
| Prune landed agent worktrees | `worktrees-gc.sh [--dry-run]` |

## dev-up / dev-down / dev-status — START HERE for day-to-day use

Three commands (symlinked into `~/.local/bin` from `dev.sh` in this skill) own
the whole lifecycle:

```bash
dev-up        # from anywhere inside any checkout or worktree
dev-down      # stop what dev-up started here (or: dev-down <name>, --all, --force)
dev-status    # infra health + every route, local + public URLs
```

`dev-up` does, in order: detect the repo root, surface (`web/`, repo root, or
Expo `app/`) and whether this is a worktree → ensure the tunnel chain is alive
(kickstarts launchd agents) → **seed env into worktrees** (copies `.env*` from
the main checkout, or runs the project's `scripts/dev-env-seed.sh` if present)
→ `pnpm install` if `node_modules` is missing → start the server under
portless with the right name → wait for ready → probe the public URL → print
local + public URLs, log path, and the stop command.

Naming: main checkout → the portless name from the `dev` script (`portless
<name> …`), or the package.json name for `portless run`, or the repo dir
basename for plain dev scripts (which dev-up wraps in portless automatically).
Worktree → `<branch>-<name>`, **flat single label** so the wildcard TLS cert
covers it (nested `branch.project.<DOMAIN>` hosts have NO cert on free
Universal SSL — HTTPS handshake fails). Override with `DEVUP_NAME`; TLD comes
from the pubproxy LaunchAgent (`DEVUP_TLD` to override). Cross-origin artifact
hosts work the same way: `art-<name>` is still one label, and pubproxy routes
an unregistered `art-<name>` host to `<name>`'s server.

In an Expo `app/` dir, `dev-up` delegates to `metro-takeover.sh`. Convention:
`pnpm dev` in Expo apps is **simulator-local** (no tunnel env, survives tunnel
outages); `pnpm dev:phone` is the tunnel variant for physical-device testing
via `<project>-app.<DOMAIN>`.

Safety: `dev-down` only kills processes dev-up started (pidfile under
`~/.dev-up/<name>/`); for servers started by hand it refuses unless `--force`.
`dev-up` is idempotent — if the route is already live it just reprints the URLs.

## Architecture

```
phone / external network
  → *.<your-tunnel-domain>             (Cloudflare wildcard CNAME → tunnel UUID)
  → cloudflared tunnel run dev         (one persistent process)
      ├─ wildcard rule → pubproxy :1354 (host-preserving lookup against
      │                                  portless's routes.json)
      │                                → 127.0.0.1:<dev-port> directly
      └─ Expo entries  → Metro :8081   (one ingress rule per Expo app,
                                        before wildcard)

laptop (local)
  → http://<project>.localhost:1355   → portless :1355 → 127.0.0.1:<dev-port>
```

Why each layer exists:
- **portless** auto-allocates a port per `pnpm dev`, dispatches by Host header,
  and auto-handles worktrees — load-bearing for parallel coding agents.
- **pubproxy** (`pubproxy.js`, ~80 lines, in this skill) forwards public-tunnel
  traffic by reading portless's `routes.json` **without rewriting Host**. It
  replaced a Caddy host-rewriter that broke downstream URL builders (Clerk
  Dev's handshake most painfully — see Troubleshooting).
- **Cloudflare Tunnel** terminates TLS at the edge, no open inbound ports,
  faster than ngrok and free.

## Setup (one-time per machine)

Human prerequisites first (dashboard clicks; `setup.sh` checks and stops with
instructions if missing): own a domain, add it as a free Cloudflare zone,
switch nameservers at the registrar, and `cloudflared tunnel login` (browser
authorize). Then:

```bash
/abs/path/to/dev-up/setup.sh <domain>     # idempotent; --tag <t> for the plist label, --tunnel <name> if not "dev"
/abs/path/to/dev-up/doctor.sh             # verify; run it any time something feels off
```

`setup.sh` installs/locates the **brew** cloudflared (never the pnpm
node-wrapper — it dies under launchd), creates the tunnel, routes wildcard
DNS, writes `~/.cloudflared/config.yml` (never clobbers an existing one),
writes + loads both LaunchAgents (pubproxy on `:1354`, cloudflared), and runs
doctor. `doctor.sh` checks the whole chain — binary, agents, config sanity,
portless, pubproxy, DNS, end-to-end probe, Expo ingress status, and a
`*_PUBLIC_*` secret audit — printing a concrete fix command per failure.

### Lock down access (immediately after setup — both free)

The wildcard cert lands in Certificate Transparency logs within minutes, so
subdomain names are **public, not secret**: scanners can reach any dev server
that's running. Two dashboard settings remove ~95% of the risk:

1. **Cloudflare Access**: Zero Trust → Access → Applications → Add
   (Self-hosted), domain `*.<DOMAIN>`, Allow policy on your email(s).
   **Expo caveat:** the dev client can't render the Access login page — add a
   second Access application per `<project>-app.<DOMAIN>` with a **Bypass**
   policy (acceptable: the host is unguessable-in-practice and the bundle is
   mostly public client code).
2. **Bot Fight Mode**: Security → Bots → On.

Plus two habits: never put real secrets in `EXPO_PUBLIC_*`/`NEXT_PUBLIC_*`
vars (they compile into the downloadable bundle — doctor audits this), and
kill dev servers when done (`dev-down`) — a stopped server is a 404; the blast
radius is whatever's running right now. The cloudflared daemon itself is
outbound-only; webhook endpoints are signature-verified; tunnel credentials at
rest are useless without local shell access (recreate the tunnel if leaked).

## Per-project wiring

```bash
add-project.sh web [name]                  # web: prints the dev-script change; nothing to wire
add-project.sh expo <hostname> <port>      # expo: ingress entry + cloudflared reload + dev script to paste
```

**Web projects need zero tunnel config** — make the dev script `portless run
next dev` (or `portless <explicit-name> next dev` when package.json names
collide, e.g. a workspace literally named "web"; dots become hyphens; inspect
with `portless list`). Drop hardcoded port flags (portless injects `PORT`),
delete old ngrok scripts, and repoint webhook URLs (Clerk/Stripe/GitHub — both
`.env` and the provider dashboard) at `https://<project>.<DOMAIN>`.

**Expo apps don't fit the portless dispatch pattern** (Metro is one HTTP+WS
server on a known port), so each gets a specific ingress entry before the
wildcard — that's what `add-project.sh expo` edits. Naming: `<project>-app.<DOMAIN>`
when the repo also has a web side; bare `<project>.<DOMAIN>` for standalone
apps. Pin Metro's port in the dev script so the ingress holds; the script
prints the exact `EXPO_PACKAGER_PROXY_URL=… REACT_NATIVE_PACKAGER_HOSTNAME=…`
dev script to paste (both vars must match the public hostname — one controls
the manifest's bundle URL, the other the QR). To run two Expo worktrees live
simultaneously, pin a second port and add a second ingress entry; the default
serial workflow needs neither (see metro-takeover).

## Worktree cleanup (`worktrees-gc.sh`)

Prunes agent worktrees under `.claude/worktrees/` whose work has landed. A
worktree is removed only when **all three** hold: clean working tree, the work
landed, and nothing outside build dirs (`node_modules`, `.next`, `.expo`,
`ios/build`, `ios/Pods`, `android/build`, `android/.gradle`) was touched in
the last 6 hours — a co-running agent session is never yanked. "Landed" means
HEAD is an ancestor of `origin/<default-branch>` (detected: main, master,
whatever origin/HEAD says), **or** — for squash/rebase-merged PRs, where
ancestry never holds — `gh` finds a merged PR for the branch whose head SHA
equals the worktree's HEAD (a branch with commits added after the merge is
kept). It does NOT prescribe a merge style; the gh check degrades to KEEP
without gh/GitHub. Everything kept is listed with its reason; `--dry-run`
previews. Idempotent, never touches the main checkout. pnpm worktrees cost far
less disk than `du` suggests (hard-linked store) — run for hygiene, not panic.

## Switching Metro between worktrees (`metro-takeover.sh`)

Kills any running Metro, starts the current worktree's, waits for ready, emits
a clickable dev-client deeplink (OSC-8). The serial-QA pattern: agent in
worktree A takes over Metro, QAs on the sim; agent B takes over after — one
Metro, one pinned port, one dev client at a time.

Autodetects from the skill-conformant setup; override with env vars:

| Variable | Default source | Override |
|---|---|---|
| App dir | git root, prefer `<root>/app` if it has an expo dep | `MT_APP_DIR` |
| Port | `--port N` parsed from the `dev` script; fallback 8081 | `MT_PORT` |
| Tunnel URL | `EXPO_PACKAGER_PROXY_URL` from the dev script; fallback localhost | `MT_URL` |
| Scheme | `app.json` → `expo config --json` run with the dev script's env (so `isDev ? 'x-dev' : 'x'` resolves the dev variant) | `MT_SCHEME` |

pnpm monorepo case handled: resolves `<app>/node_modules/.bin/expo`, then
`<root>/…`, then `$PATH` (npx doesn't always walk up to the hoisted binary).

## Expo QA: fingerprint gate + EAS Update publish (`expo-qa.sh`)

Metro takeover is the **inner loop** (HMR, one worktree at a time). `expo-qa.sh`
is the **correctness gate and the parallel review path**:

```bash
expo-qa.sh gate                 # is the installed dev client valid for this branch?
expo-qa.sh publish [--dry-run]  # gate, then eas update --branch wt/<branch>
expo-qa.sh record               # after building+installing a dev client: pin its fingerprint
```

**`gate`** compares the worktree's `@expo/fingerprint` hash (iOS default,
`--platform android` to switch) against the default-branch checkout. Match
(exit 0) → branch is JS-only; QA on the installed dev client — Metro or
published update — is valid. Mismatch (exit 2) → the branch changes the native
layer; "verified on sim" through the shared client would be a false positive —
the branch needs its own `eas build --profile development` (differing sources
are printed). Run it before claiming any simulator verification. It's the only
protection on **pinned** `runtimeVersion` projects (a native-drifted update
loads, then crashes); on `policy: 'fingerprint'` projects it predicts whether
a published update will even be loadable.

**`record`** closes the gate's blind spot: the *installed client* can predate
the baseline — it lists new updates but greys out Open (fingerprint runtime)
or loads them against wrong natives (pinned). `record` pins the fingerprint of
the tree a dev client was just built from to `~/.expo-qa/<app>-<platform>.json`;
project `local-build.sh` wrappers call it automatically after successful dev
builds (template in the expo-local-build skill). With a record, `gate` adds a
third verdict — **CLIENT STALE, exit 3** — and `publish` refuses with "rebuild
the dev client first" (`--skip-gate` if you'll load on a fresher device).

**`publish`** runs the gate, then `eas update --branch wt/<branch>` from the
app dir with the dev script's env applied (so `APP_VARIANT`-style variants
resolve like the running client), and emits the dev-client deeplink. This is
the parallel-QA bus: N worktrees publish concurrently, zero Metro/port/sim
contention, loadable on any dev client — sim or physical phone, no Mac awake,
works on cellular. ~1–2 min latency, no HMR: review path, not dev loop. The
`wt/` prefix is enforced and the default branch refused, so a publish can
never reach a release channel (channels map to branches explicitly; nothing
maps to `wt/*`). Where a project's OTA releases need separate authorization
(e.g. recipes.im), that covers channel-mapped branches — still surface `wt/*`
publishes in your report.

| Variable | Default source | Override |
|---|---|---|
| App dir | git root, prefer `<root>/app` with an expo dep | `EQ_APP_DIR` |
| Baseline | the git worktree checked out on the default branch | `EQ_BASELINE_DIR` |
| Platform | `ios` | `EQ_PLATFORM` / `--platform` |
| Scheme | `app.json` → `expo config --json` with dev-script env | `EQ_SCHEME` |
| Message | last commit subject | `--message` |
| EAS environment | `development` (eas-cli requires one non-interactively) | `EQ_EAS_ENV` / `--environment` |

pnpm gotcha (verified on journeys.im): each tree is fingerprinted with **its
own** `node_modules/.bin/fingerprint` — a bin borrowed from another checkout
hashes an identical tree differently. Handled; version skew between trees
produces a warning (mismatch may be algorithm drift). Both trees need deps
installed.

## Troubleshooting

### `https://<project>.<DOMAIN>` returns portless's 404

Portless doesn't know that name. Check: dev server actually running? name
matches `portless list` (or `<branch>-<name>` for worktrees)? dev script uses
`portless run`/`portless <name>`? chain alive (`lsof -nP -iTCP:1354
-sTCP:LISTEN`, same for `:1355`, `tail ~/.cloudflared/cloudflared.log` shows
"Registered tunnel connection")?

### Redirects / Clerk Dev bouncing to `<project>.localhost`

This is what pubproxy fixes — the old Caddy host-rewriter broke Next.js
redirects, OG `metadataBase`, and Clerk Dev's `dev_browser` handshake
(fresh devices bounced to `<project>.localhost:1355` → connection refused).
If it resurfaces: is `:1354` held by `node` (not a leftover `caddy` — `brew
services list | grep caddy` should be none)? is the project in
`~/.portless/routes.json`? pubproxy returns its own explicit 404 when it has
no route — that's portless registration, not the bounce. Last resort for a
project that truly can't run Clerk Dev behind a tunnel: a Clerk Production
instance on a real subdomain (invasive; rarely worth it).

### cloudflared keeps reconnecting / one connection flaps

Normal — it holds 4 redundant edge connections; single flaps are harmless
while ≥3 are stable.

### Phone can't reach it but laptop can

Confirm cellular works (`https://1.1.1.1` from the phone). If the laptop works
and the phone doesn't, the laptop is resolving via something local (e.g.
`.localhost`); public DNS → Cloudflare IPs → tunnel works everywhere.

### `tunnel route dns` fails with "record exists"

`-f` solves CNAME-vs-CNAME. A leftover wildcard **A** record (Cloudflare
sometimes auto-creates one on zone import) must be deleted in the dashboard.

### WebSocket HMR isn't working

Tunnel + pubproxy pass WebSockets natively. If HMR fails, the page is probably
constructing the WS URL from the wrong host — same root cause as the redirect
issue.

## File map

```
~/.cloudflared/
├── cert.pem                      # auth from `cloudflared tunnel login`
├── <UUID>.json                   # per-tunnel credentials
├── config.yml                    # ingress rules (setup.sh writes, add-project.sh edits)
└── cloudflared.log               # daemon log

~/Library/LaunchAgents/com.<short-tag>.pubproxy.plist     # pubproxy daemon (setup.sh)
~/Library/LaunchAgents/com.cloudflare.cloudflared.plist   # cloudflared daemon (setup.sh)
<this-skill>/setup.sh                                     # one-time machine onboarding
<this-skill>/add-project.sh                               # per-project tunnel wiring
<this-skill>/pubproxy.js                                  # the host-preserving proxy
<this-skill>/dev.sh                                       # dev-up/dev-down/dev-status (symlinked in ~/.local/bin)
<this-skill>/metro-takeover.sh                            # Expo Metro worktree switcher
<this-skill>/expo-qa.sh                                   # Expo fingerprint gate + EAS Update wt/ publish + client record
<this-skill>/worktrees-gc.sh                              # prune landed agent worktrees (any repo)
<this-skill>/doctor.sh                                    # health check

~/.dev-up/<name>/                                         # per-server pidfile + log (dev-up state)
~/.expo-qa/<app>-<platform>.json                          # recorded dev-client fingerprint (expo-qa record)
```
