---
name: dev-up
description: One-verb local dev-server + worktree QA lifecycle for any checkout (web or Expo), backed by a Cloudflare-Tunnel ngrok replacement that multiplexes many dev servers (via portless) through one wildcard subdomain. Includes `dev-up`/`dev-down`/`dev-status` (env seeding, install, portless naming, public URL), `metro-takeover.sh` for switching Expo Metro between git worktrees, `expo-qa.sh` (fingerprint gate that detects when a worktree needs its own dev build, plus `eas update --branch wt/<branch>` publish for parallel branch QA on any dev client), `worktrees-gc.sh` for pruning landed agent worktrees in any repo, and `doctor.sh` for health-checking the tunnel/portless chain. Formerly named cloudflare-tunnel-portless. Triggers on "dev-up", "spin up the dev server", "start the dev server", "test before shipping", "public URL for this worktree", "set up cloudflare tunnel", "ngrok replacement", "public URL for localhost", "portless", "cloudflared", "metro-takeover", "switch metro to worktree", "expo-qa", "fingerprint gate", "is the dev client valid for this branch", "publish this branch as an EAS update", "QA this worktree on my phone", "worktrees-gc", "clean up worktrees", "prune old worktrees", "tunnel doctor", "add project to tunnel", "onboard new mac to tunnel", or "debug caddy/portless/cloudflared".
---

# dev-up — local dev servers + worktree QA, one verb each

The day-to-day surface is the verbs: `dev-up`/`dev-down`/`dev-status` for any
checkout or worktree, `metro-takeover` + `expo-qa` for Expo QA, `worktrees-gc`
for cleanup. Underneath: a free Cloudflare Tunnel + a tiny host-rewriter in
front of [portless](https://github.com/vercel-labs/portless) replaces ngrok —
one persistent tunnel handles every web project under a single wildcard
subdomain, Expo apps get individual ingress entries. (This skill was formerly
named `cloudflare-tunnel-portless`.)

## dev-up / dev-down / dev-status — START HERE for day-to-day use

Once the machine setup below exists, agents and humans should not assemble the
workflow by hand. Three commands (symlinked into `~/.local/bin` from `dev.sh`
in this skill) own the whole lifecycle:

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
portless with the right name → wait for ready → probe the public URL → print:

```
✓ feature-x-drafty-web up
  Local:   http://feature-x-drafty-web.localhost:1355  (direct: http://127.0.0.1:4123)
  Public:  https://feature-x-drafty-web.jkyf.dev
  Log:     ~/.dev-up/feature-x-drafty-web/server.log
  Stop:    dev-down feature-x-drafty-web
```

Naming: main checkout → the portless name from the `dev` script (`portless
<name> …`), or the package.json name for `portless run`, or the repo dir
basename for plain dev scripts (which dev-up wraps in portless automatically).
Worktree → `<branch>-<name>`, flat single label so the wildcard TLS cert
covers it. Override with `DEVUP_NAME`. TLD comes from the pubproxy LaunchAgent
(`DEVUP_TLD` to override).

In an Expo `app/` dir, `dev-up` delegates to `metro-takeover.sh` (kills any
Metro on the project's pinned port, starts this worktree's, emits the
dev-client deeplink). Convention: `pnpm dev` in Expo apps is **simulator-local**
(no tunnel env, survives tunnel outages); `pnpm dev:phone` is the tunnel
variant for physical-device testing via `<project>-app.<DOMAIN>`.

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
- **portless** auto-allocates a free port for every `pnpm dev` and dispatches by Host header. Solves "I don't know which port my worktree will use." Also auto-prefixes worktree branch names so `feature-x.<project>.localhost` works without per-worktree config — load-bearing for spawning multiple coding agents in parallel worktrees.
- **pubproxy** is a tiny (~80 line) Node script in this skill (`pubproxy.js`). It listens on `:1354`, reads portless's `~/.portless/routes.json` directly to look up the dev port for the requested host, then forwards the request **without rewriting Host**. Replaces the original Caddy host-rewriter, which broke downstream URL builders (most painfully Clerk Dev's handshake — see Troubleshooting). Local browsing through portless on `:1355` is unaffected; pubproxy only sits on the public-tunnel path.
- **Cloudflare Tunnel** terminates TLS at Cloudflare's edge, no open ports on your machine, and uses the global Cloudflare network (faster than ngrok, no timeouts under load).

## Prerequisites the user does once

These steps require the user to make decisions and click in dashboards. Surface them to the user and wait for confirmation.

1. **Pick a tunnel domain.** Any domain you own works, but it MUST be on Cloudflare DNS — Cloudflare Tunnel's `*.domain → cfargotunnel.com` CNAME doesn't work from external DNS providers. If the domain is currently parked, that's ideal. If it serves a real site, the apex/www records survive the migration since you'll re-create them in Cloudflare.
2. **Sign up at https://dash.cloudflare.com/sign-up** (free).
3. **Add the domain as a zone** (Free plan). Cloudflare scans existing DNS — accept the import.
4. **Switch nameservers at the registrar** to the two Cloudflare gives (e.g. `ariel.ns.cloudflare.com`, `coraline.ns.cloudflare.com`). Propagation: 5–30 min.
5. **Confirm propagation:** `dig +short <domain> NS @1.1.1.1` should return Cloudflare nameservers.

Once the user confirms, proceed with the automated setup below.

## One-time machine setup

Substitute `$DOMAIN` (e.g. `your-domain.dev`) below. Everything else is generic.

### 1. Install dependencies

```bash
brew install cloudflare/cloudflare/cloudflared
```

**Don't use `pnpm add -g cloudflared`.** That installs a node-wrapper script which fails under launchd because launchd doesn't put `node` in PATH (`exec: node: not found`). The brew formula installs a real native binary that works directly.

(Earlier versions of this skill installed Caddy here. It's no longer needed — pubproxy from this skill replaces it.)

### 2. Authenticate to Cloudflare

```bash
cloudflared tunnel login
```

Pops a browser tab — user clicks "Authorize" for `$DOMAIN`. Writes `~/.cloudflared/cert.pem`.

### 3. Create the tunnel

```bash
cloudflared tunnel create dev
```

Outputs the tunnel UUID and writes credentials to `~/.cloudflared/<uuid>.json`. Capture the UUID — you'll need it for the config file.

### 4. Wildcard DNS

```bash
cloudflared tunnel route dns -f dev "*.$DOMAIN"
```

If this fails with `Failed to create record *.$DOMAIN with err An A, AAAA, or CNAME record with that host already exists`, the user needs to delete that wildcard record from the Cloudflare dashboard (DNS → Records → find `*` row → Delete), then retry. Cloudflare sometimes auto-creates a wildcard A record on import.

### 5. Write `~/.cloudflared/config.yml`

```yaml
tunnel: <UUID>
credentials-file: <HOME>/.cloudflared/<UUID>.json

ingress:
  # --- Expo projects (specific entries, ordered before the wildcard) ---
  # Add one per Expo app. Pin Metro's port so you can hardcode it here.
  # - hostname: myapp.<DOMAIN>
  #   service: http://127.0.0.1:8081

  # --- Web projects via pubproxy (catch-all) ---
  - hostname: '*.<DOMAIN>'
    service: http://127.0.0.1:1354

  # Catch-all
  - service: http_status:404
```

Substitute the real UUID, `$HOME`, and `$DOMAIN`.

### 6. Run pubproxy on `:1354`

`pubproxy.js` lives next to this `SKILL.md`. It reads `~/.portless/routes.json` and forwards public-tunnel traffic to the underlying dev port without rewriting Host. Env vars: `PUBPROXY_PORT` (default 1354), `PUBPROXY_TLD` (default `example.dev`), `PUBPROXY_ROUTES` (default `~/.portless/routes.json`).

Foreground sanity check:

```bash
PUBPROXY_TLD=<DOMAIN> node /path/to/dev-up/pubproxy.js &
sleep 1
curl -sI -H "Host: <some-running-project>.<DOMAIN>" http://127.0.0.1:1354/
```

Persistent setup is in step 9.

### 7. Start the services (foreground first to verify)

```bash
PUBPROXY_TLD=<DOMAIN> node /path/to/pubproxy.js &
cloudflared tunnel run dev &
```

Verify the tunnel is established by checking cloudflared logs — should see ~4 "Registered tunnel connection" lines.

### 8. Smoke-test

Assuming portless is running on :1355 and at least one project (`<myproj>`) is registered with portless:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "https://<myproj>.$DOMAIN/"
# expected: 200
```

### 9. Make services persistent

#### pubproxy via launchd

User-level LaunchAgent. Resolves the absolute Node binary path so launchd doesn't trip over PATH. Substitute `$DOMAIN` and the absolute path to `pubproxy.js`.

```bash
cat > ~/Library/LaunchAgents/com.<short-tag>.pubproxy.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.<short-tag>.pubproxy</string>
    <key>ProgramArguments</key>
    <array>
      <string>$(which node)</string>
      <string>/absolute/path/to/dev-up/pubproxy.js</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$HOME/.portless/pubproxy.log</string>
    <key>StandardErrorPath</key><string>$HOME/.portless/pubproxy.log</string>
    <key>EnvironmentVariables</key>
    <dict>
      <key>HOME</key><string>$HOME</string>
      <key>PUBPROXY_PORT</key><string>1354</string>
      <key>PUBPROXY_TLD</key><string>$DOMAIN</string>
    </dict>
  </dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/com.<short-tag>.pubproxy.plist
launchctl list | grep pubproxy   # status code should be 0
```

#### cloudflared via launchd

User-level LaunchAgent (no sudo). Resolves the absolute brew path so launchd can find the binary:

```bash
cat > ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.cloudflare.cloudflared</string>
    <key>ProgramArguments</key>
    <array>
      <string>$(brew --prefix)/opt/cloudflared/bin/cloudflared</string>
      <string>tunnel</string>
      <string>--config</string>
      <string>$HOME/.cloudflared/config.yml</string>
      <string>run</string>
      <string>dev</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$HOME/.cloudflared/cloudflared.log</string>
    <key>StandardErrorPath</key><string>$HOME/.cloudflared/cloudflared.log</string>
    <key>EnvironmentVariables</key>
    <dict>
      <key>HOME</key><string>$HOME</string>
    </dict>
  </dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist
launchctl list | grep cloudflared    # status code should be 0
```

Verify it's running: `tail ~/.cloudflared/cloudflared.log` — should show 4 "Registered tunnel connection" lines.

Note: writing the plist may require the user to approve a sandbox permission prompt (it's an auto-launch persistence action). Surface this to the user and let them paste the `cat > ...` command themselves if your tool environment blocks it.

`sudo cloudflared service install` is the canonical alternative if you want a system-level daemon — but the user LaunchAgent above is sufficient and avoids sudo.

## Doctor — verify the setup

`doctor.sh` (next to this `SKILL.md`) runs the full health check chain and prints each result with a concrete fix command on failure. Run it after first-time setup, after a macOS update, or whenever something feels off.

```bash
/abs/path/to/dev-up/doctor.sh
```

Checks, in order (✓ pass / ✗ infra failure / ⚠ advisory):

1. `cloudflared` is the brew binary (rejects `~/Library/pnpm/cloudflared`, the node-wrapper that fails under launchd).
2. cloudflared LaunchAgent is loaded with status 0; recent log shows ≥3 "Registered tunnel connection" lines.
3. `~/.cloudflared/config.yml` parses; tunnel UUID matches its credentials file; has a `*.<DOMAIN>` wildcard rule and an `http_status:404` fallback.
4. portless installed; proxy listening on `:1355`.
5. pubproxy LaunchAgent loaded; `node` listening on `:1354` (warns if it's `caddy` from an old skill version).
6. DNS: `dig +short doctor-probe.<DOMAIN> @1.1.1.1` returns Cloudflare IPs.
7. End-to-end: picks the first project from `portless list`, hits it through the public URL, expects non-502.
8. Lists each Expo ingress entry; for each, says whether Metro is currently listening on the configured port (informational — Metro not running is fine if no one's working on that app).
9. Audits `.env*` in CWD for `(EXPO|NEXT)_PUBLIC_*` vars containing secret-like values (compiled into the client bundle).

Exit 0 if all infra checks pass (warnings don't fail). Exit 1 on any infra failure.

## Lock down access (do this immediately after setup)

The tunnel is permanent and the wildcard subdomain is enumerable via Certificate Transparency logs (Cloudflare issues a public-facing TLS cert for `*.<DOMAIN>` — that lands in [crt.sh](https://crt.sh) within minutes). Treat your subdomain names as **public**, not secret. Anyone who guesses or scrapes a name reaches your dev server while it's running.

Without hardening, that means: random scanners can sign up via your dev Clerk instance, burn free credits, trigger paid API calls (DashScope / OpenAI / etc.), spam test-mode Stripe checkouts, and pull source-mapped JS bundles with full filesystem paths.

Two free settings remove ~95% of the risk.

### 1. Cloudflare Access — login wall in front of `*.<DOMAIN>`

Free, built into the Cloudflare account. Anyone hitting any subdomain first sees a Cloudflare-hosted login page; only you (and anyone you allowlist) get through. Browser session lasts ~24 h on each device.

In the Cloudflare dashboard:

1. **Zero Trust → Access → Applications → Add an application → Self-hosted.**
2. Application name: `dev tunnel` (or anything). Domain: `*.<DOMAIN>`. Session duration: 24 hours (or longer).
3. Click **Next** → **Add policy.** Policy name: `me`. Action: **Allow**. Include rule: **Emails** → list your own email(s).
4. Save, save, done.

Test: open an incognito window → `https://<anything>.<DOMAIN>` → should see Cloudflare's login page. Authenticate → forwarded to the dev server.

#### Expo / dev-client caveat

The Expo dev client doesn't render Cloudflare's HTML login page, so a vanilla Access policy will break the Expo Go connection. Either:

- **Carve out a bypass for the Expo subdomain.** Add a second Access application for `<project>-app.<DOMAIN>` with a **Bypass** policy. The Expo subdomain stays public; the rest stays gated. Acceptable because the Expo subdomain name is unguessable in practice and Metro's bundle is mostly already-public client code.
- **OR use a Service Token.** Mint a service token in Zero Trust, configure the Access app to allow the token, and set Metro's requests to include `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers. More work; rarely worth it.

### 2. Bot Fight Mode

Cloudflare dashboard → **Security → Bots → Bot Fight Mode → On.** Free, no config. Blocks obvious bots and known-bad UAs before they ever reach the tunnel. Pair with Access for defense-in-depth.

### 3. Audit `*_PUBLIC_*` env vars

`EXPO_PUBLIC_*`, `NEXT_PUBLIC_*`, and similar prefixes get **compiled into the client bundle** and are downloadable by anyone fetching the dev bundle. Confirm no real secrets are stored under those prefixes:

```bash
grep -rE "^(EXPO_PUBLIC|NEXT_PUBLIC)" .env .env.local .env.* 2>/dev/null
```

API keys for client-callable services (Mapbox public token, Clerk publishable key) are fine. Secret keys, server tokens, DB URLs, webhook signing secrets are NOT fine — move them to non-`PUBLIC_` env vars.

### 4. Habit, not config: kill dev servers when done

The tunnel is always-on. The dev servers behind it are not. If `pnpm dev` for a given project isn't running, `<project>.<DOMAIN>` returns portless's 404 — nothing exposed. Only run dev servers for projects you're actively working on. The blast radius is whatever's running right now.

### What's still safe regardless

- **The cloudflared daemon itself** — outbound-only, no inbound ports on your Mac, Cloudflare absorbs DDoS for free, HTTPS terminated at Cloudflare's edge.
- **Webhook endpoints** — signature-verified (svix / Stripe / GitHub) reject forged requests with a 400.
- **Tunnel credentials at rest** — `~/.cloudflared/cert.pem` + `<uuid>.json` are sensitive but useless without local shell access. Standard Mac hygiene (FileVault on, no shared accounts) is sufficient. If leaked: `cloudflared tunnel delete dev` and recreate.

## Per-project conventions

This is the part that determines how each project type uses the new tunnel.

### Web project with portless (Next.js, Vite, etc.) — zero per-project config

The `pnpm dev` script wraps the dev command with portless:

```json
{ "scripts": { "dev": "portless run next dev" } }
```

Once running, the project is reachable at:

- **Local:** `http://<project>.localhost:1355`
- **Public:** `https://<project>.<DOMAIN>`

#### How portless picks `<project>`

`portless run` infers the name in this order:
1. `package.json "name"` field, walking up directories.
2. Git repo root directory name.
3. Current directory basename.

(Dots → hyphens automatically — directory `foo.bar` becomes `foo-bar` because subdomain labels can't contain dots.)

If the inferred name is bad (e.g. a workspace package literally named `"web"`), use the explicit form:

```json
{ "scripts": { "dev": "portless myproj-web next dev" } }
```

That gives `myproj-web.localhost:1355` and `myproj-web.<DOMAIN>` regardless of what `package.json "name"` says.

Inspect what portless thinks via `portless list`.

#### Worktrees

`portless run` auto-prepends the branch as a **nested** subdomain — a worktree of
`my-project` on branch `feature-auth` becomes `feature-auth.my-project.localhost`
/ `.<DOMAIN>`. That works **locally**, but **breaks over the tunnel**: Cloudflare's
free Universal SSL only certs `<DOMAIN>` + `*.<DOMAIN>` (one level), so a two-deep
host like `feature-auth.my-project.<DOMAIN>` has **no TLS cert** — HTTPS fails the
handshake (curl `000`). A deeper `*.my-project.<DOMAIN>` DNS record resolves but
still has no cert without paid Advanced Certificate Manager.

**Use flat, single-label worktree hosts instead** — they're covered by the
existing `*.<DOMAIN>` cert. Run the worktree's dev server with the **direct**
portless form (which does *not* nest), naming it `<branch>-<project>`:

```bash
portless feature-auth-my-project bun dev   # -> https://feature-auth-my-project.<DOMAIN>
```

(`portless <name> <cmd>` gives exactly `<name>.localhost` — no worktree prefix —
unlike `portless run`. So you control the flat name.)

**Cross-origin artifact origins (e.g. Marky's `art-<host>` iframe) work too:**
`art-feature-auth-my-project.<DOMAIN>` is still a single label, so it's cert-covered,
and `pubproxy` routes an unregistered `art-<name>` host to `<name>`'s server (it
strips the `art-` prefix as a fallback). No extra portless entry per worktree.

##### Worktree cleanup (`worktrees-gc.sh`)

`worktrees-gc.sh` (next to this `SKILL.md`, works in any repo — web or Expo)
prunes agent worktrees under `.claude/worktrees/` whose work has landed. A
worktree is removed only when **all three** hold: clean working tree, HEAD is an
ancestor of `origin/<default-branch>` (detected — main, master, whatever
origin/HEAD says), and nothing outside build dirs (`node_modules`, `.next`,
`.expo`, `ios/build`, `ios/Pods`, `android/build`, `android/.gradle`) was
touched in 6 hours — so a co-running agent session is never yanked. Everything
kept is listed with its reason. `--dry-run` to preview. Run it after a ship
lands, or whenever worktrees pile up; idempotent, never touches the main
checkout. Note pnpm worktrees cost far less disk than `du` suggests
(hard-linked store), so run this for hygiene, not panic.

```bash
cd <repo>
/abs/path/to/dev-up/worktrees-gc.sh --dry-run   # preview
/abs/path/to/dev-up/worktrees-gc.sh             # prune
```

#### Converting an existing project to portless

For a project that runs `next dev` directly:

1. Change `"dev": "next dev"` → `"dev": "portless run next dev"` (or `portless <name> next dev` for monorepo workspaces).
2. **Drop any hardcoded port flag** like `-p 3010` — portless picks a free port and injects via the `PORT` env var.
3. Drop any per-project tunnel script (`pnpm ngrok`, etc.).
4. Update CLAUDE.md / README to reference the new `<project>.<DOMAIN>` URL.
5. Smoke-test: `pnpm dev`, then `curl https://<project>.<DOMAIN>/`.

### Drop the old `pnpm ngrok` script

Remove `"ngrok": "ngrok http ..."` from `package.json`. The Cloudflare Tunnel runs as a persistent daemon, not a per-project task. Update CLAUDE.md (or equivalent) to document the new public URL.

### Webhooks pointing at the public URL

Anywhere a webhook URL was `https://<old-ngrok>/api/webhooks/foo`, change it to `https://<project>.<DOMAIN>/api/webhooks/foo`. Examples: Clerk webhook endpoints, Stripe webhook endpoints, GitHub webhooks. Update both `.env` and the upstream provider dashboard.

### Expo project (React Native / Expo Go)

Expo doesn't fit the portless dispatch pattern — Metro is one HTTP+WS server on a known port. Add a per-project ingress entry to `~/.cloudflared/config.yml`, ordered **before** the wildcard.

#### Naming convention

If the Expo app lives inside a project that also has a web side (monorepo with `app/` and `web/`), use `<project>-app.<DOMAIN>` so the two coexist:

| Surface | Public URL | Reaches |
|---|---|---|
| Web (via portless) | `myapp.<DOMAIN>` | wildcard → Caddy → portless |
| Expo Metro | `myapp-app.<DOMAIN>` | specific ingress → `127.0.0.1:8081` |

For a standalone Expo project (no web side), `<project>.<DOMAIN>` is fine since the wildcard would otherwise hand it to portless and 404 anyway.

#### Config

```yaml
ingress:
  - hostname: myapp-app.<DOMAIN>
    service: http://127.0.0.1:8081

  # ... other Expo apps here, each on a unique Metro port ...

  - hostname: '*.<DOMAIN>'
    service: http://127.0.0.1:1354
  - service: http_status:404
```

Then restart cloudflared:

```bash
launchctl unload ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist
launchctl load ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist
# or: brew services restart cloudflared
```

#### Expo dev script

Replace any `ngrok http ... 8081 & expo start` wrapper with a clean `expo start` that just sets the env vars Metro reads when constructing the dev URL:

```json
{
  "scripts": {
    "dev": "EXPO_PACKAGER_PROXY_URL=https://myapp-app.<DOMAIN> REACT_NATIVE_PACKAGER_HOSTNAME=myapp-app.<DOMAIN> expo start --dev-client --port 8081"
  }
}
```

`EXPO_PACKAGER_PROXY_URL` controls the URL written into the dev manifest's `launchAsset.url` (what the dev client downloads the bundle from). `REACT_NATIVE_PACKAGER_HOSTNAME` is what Metro advertises via the QR code. Both must match the public hostname.

Pin Metro's port (`--port 8081`) so the cloudflared ingress can hardcode it.

#### Multiple Expo worktrees simultaneously

Default workflow: only one Expo Metro runs at a time. To preview a different worktree, kill Metro and start it in the other tree — same port, same URL. The `metro-takeover.sh` script next to this `SKILL.md` automates the swap (see "Switching Metro between worktrees" below).

If you actually need two Expo worktrees live at the same time, pin different ports per worktree and add an ingress entry for each:

```yaml
- hostname: myapp.<DOMAIN>
  service: http://127.0.0.1:8081
- hostname: myapp-feature-x.<DOMAIN>
  service: http://127.0.0.1:8082
```

#### Switching Metro between worktrees

`metro-takeover.sh` (next to this `SKILL.md`) kills any running Metro, starts the current worktree's, waits for ready, and emits a clickable dev-client deeplink as an OSC-8 hyperlink. Designed for the serial-QA pattern: agent in worktree A finishes coding, takes over Metro, runs simulator QA (e.g. via the `agent-device` skill); when done, agent in worktree B takes over and reloads the dev client by tapping/clicking its own deeplink.

```bash
cd <any-worktree-of-the-project>
/abs/path/to/dev-up/metro-takeover.sh
```

Autodetects everything from the project's existing skill-conformant setup:

| Variable | Default source | Override env var |
|---|---|---|
| App dir | git root, prefer `<root>/app` if it has an expo dep, else `<root>` | `MT_APP_DIR` |
| Port | `--port N` parsed from `app/package.json` `scripts.dev`; fallback 8081 | `MT_PORT` |
| Tunnel URL | `EXPO_PACKAGER_PROXY_URL=...` parsed from the dev script; fallback `http://localhost:<port>` | `MT_URL` |
| Scheme | `app.json` `expo.scheme` → fallback `expo config --json` (resolved with the dev script's env loaded so `isDev ? 'foo-dev' : 'foo'` returns the dev variant) | `MT_SCHEME` |

Output:

```
metro-takeover: killing Metro on :8081 (pid 12345)
metro-takeover: starting Metro in /path/to/repo/app (pnpm dev) → /tmp/metro-<branch>.log
metro-takeover: waiting for Metro on :8081........
metro-takeover: Metro ready

  Deeplink: <scheme>://expo-development-client/?url=<encoded URL>
  App dir:  /path/to/repo/app
  Branch:   <git branch>
  Log:      /tmp/metro-<branch>.log
```

Click the deeplink (in iTerm, Ghostty, Warp, WezTerm — any OSC-8 terminal) on a Mac with the dev client installed in the iOS Simulator, or scan it on a physical device, to reopen the app pointed at the new bundle.

The pnpm monorepo case is handled — `npx --no-install` doesn't always walk up to find the hoisted `expo` binary, so the script resolves `<app>/node_modules/.bin/expo` then `<root>/node_modules/.bin/expo` then `$PATH`. If none exist, set `MT_SCHEME` directly.

#### Expo QA: fingerprint gate + EAS Update publish (`expo-qa.sh`)

Metro takeover is the **inner loop** (HMR, one worktree at a time on the pinned port). `expo-qa.sh` (next to this `SKILL.md`) is the **correctness gate and the parallel review path**:

```bash
cd <any-worktree-of-the-project>
/abs/path/to/dev-up/expo-qa.sh gate                 # is the installed dev client valid for this branch?
/abs/path/to/dev-up/expo-qa.sh publish [--dry-run]  # gate, then eas update --branch wt/<branch>
```

**`gate`** computes the worktree's `@expo/fingerprint` hash (iOS by default, `--platform android` to switch) and compares it to the checkout on the repo's default branch. Match (exit 0) → the branch is JS-only relative to the baseline, so QA on the already-installed dev client — via Metro takeover or a published update — is valid. Mismatch (exit 2) → the branch changes the native layer; the shared dev client will NOT reflect it and any "verified on sim" claim through it is a false positive. The branch needs its own `eas build --profile development`. The differing fingerprint sources are printed so you can see *what* diverged. Run the gate before claiming any simulator verification on a worktree — this kills the verified-on-a-stale-native-client failure class, and it's the only protection on projects with a **pinned** `runtimeVersion` (where a native-drifted update would still load, then crash). On `runtimeVersion: { policy: 'fingerprint' }` projects the gate predicts whether a published update will even be loadable.

**`publish`** runs the gate, then `eas update --branch wt/<branch>` from the app dir with the dev script's env applied (so `APP_VARIANT`-style config variants resolve the same as the running dev client), and emits a dev-client deeplink (`<scheme>://expo-development-client/?url=<u.expo.dev update URL>`). This is the parallel-QA bus: N worktrees publish concurrently with zero Metro/port/sim contention, and any dev client — a simulator or a physical phone, no Mac involved — can load any branch. ~1–2 min publish latency, no HMR: it's the review path, not the dev loop; the two compose. The `wt/` branch prefix is enforced and publishing from the default branch is refused, so a publish can never reach a release channel (channels map to branches explicitly; nothing maps to `wt/*`). `--dry-run` prints the exact command without publishing. Where a project's OTA releases require separate authorization (e.g. recipes.im), that covers *channel-mapped* branches — `wt/*` QA publishes are agent infrastructure, but still surface them in your report.

| Variable | Default source | Override |
|---|---|---|
| App dir | git root, prefer `<root>/app` with an expo dep | `EQ_APP_DIR` |
| Baseline | the git worktree checked out on the default branch | `EQ_BASELINE_DIR` |
| Platform | `ios` | `EQ_PLATFORM` / `--platform` |
| Scheme | `app.json` → `expo config --json` with dev-script env | `EQ_SCHEME` |
| Message | last commit subject | `--message` |

pnpm gotcha (verified on journeys.im): each tree is fingerprinted with **its own** `node_modules/.bin/fingerprint` — a bin borrowed from another checkout resolves sources through its own symlinked store and hashes an identical tree differently. The script handles this; it also warns when the two trees carry different `@expo/fingerprint` versions (a mismatch may then be algorithm drift, not native drift). Both trees must have deps installed.

## Adding new projects later

| Action | Cost |
|---|---|
| New web project + worktrees | Zero. Just `pnpm dev`. |
| New Expo project | One ingress entry + restart cloudflared. |
| New tunnel domain (e.g. add `bar.dev` alongside `foo.dev`) | Add the new domain as a Cloudflare zone, run `cloudflared tunnel route dns dev "*.bar.dev"`, add new wildcard rule + Caddy regex alternation. |

## Troubleshooting

### `https://<project>.<DOMAIN>` returns portless's 404

Means portless doesn't know about a project with that name. Check:
- Is the dev server actually running? (`pnpm dev`)
- Does the project name match what portless registered? Run `portless list` to see all known projects with their ports. The URL must match the leftmost label of one of them (or be the worktree branch prefix + project name).
- Does the project's `dev` script use portless? `grep -E '"dev"' package.json` — should contain `portless run` or `portless <name>`. If not, the project isn't registered with portless yet.
- Is the tunnel/Caddy chain alive? `lsof -nP -iTCP:1354 -sTCP:LISTEN` and `lsof -nP -iTCP:1355 -sTCP:LISTEN` should both show a listener. `tail ~/.cloudflared/cloudflared.log` should show "Registered tunnel connection".

### Redirects / Clerk Dev bouncing to `<project>.localhost`

**This is what pubproxy fixes.** Earlier versions of this skill ran a Caddy host-rewriter on `:1354` so portless could dispatch by its hardcoded `.localhost` matcher. The rewrite broke downstream URL builders — Next.js redirects, OG `metadataBase`, and most painfully Clerk Dev's `dev_browser` handshake. Fresh devices visiting `<project>.<DOMAIN>` got bounced to `<project>.localhost:1355`, which on phones / external networks meant `ERR_CONNECTION_REFUSED`.

Verified 2026-04: replacing Caddy with pubproxy (which preserves Host) fixes both the framework drift and the Clerk Dev bounce in a single move. The Clerk dev_browser endpoint accepts the canonical `<project>.<DOMAIN>` origin once it actually arrives at the dev server intact.

If you're hitting a redirect-to-localhost symptom and pubproxy is in place, check:

- Is pubproxy actually running on `:1354`? `lsof -nP -iTCP:1354 -sTCP:LISTEN` should show `node` (not `caddy`).
- Is portless's routes file populated? `cat ~/.portless/routes.json` should list the project. If pubproxy can't find a route, it returns its own `404 pubproxy: no portless route for host "..."` rather than bouncing.
- Did you leave Caddy running? `brew services list | grep caddy` should be `none`. If both are listening, whichever bound `:1354` first wins (and it'll still mostly look like it works, just with the old broken behaviour).

If a project genuinely cannot use a Clerk Dev instance behind a tunnel for other reasons (rare), the fallback is to switch that project to a Clerk Production instance keyed to a real subdomain. Most invasive: requires a real domain for Clerk to verify, real DNS records, and you lose Clerk Dev's "any origin works" convenience locally. Only worth it if pubproxy + Clerk Dev together still don't satisfy the case.

### Cloudflared keeps reconnecting / one connection flaps

Normal. cloudflared establishes 4 redundant connections to Cloudflare's edge. Single-connection flaps are harmless as long as 3 are stable.

### Phone can't reach `<project>.<DOMAIN>` but laptop can

Check from the phone: open `https://1.1.1.1` first to confirm cellular works. Then try the URL. If laptop works and phone doesn't, the laptop is hitting some local DNS (e.g. portless's `/etc/hosts` entry for `.localhost`) that the phone doesn't have. Public DNS resolves `<project>.<DOMAIN>` to Cloudflare's IPs, which then route via the tunnel — that should work everywhere.

### `cloudflared tunnel route dns` fails with "record exists"

Use `-f` flag for CNAME-vs-CNAME conflicts. For A-record conflicts (Cloudflare's auto-import sometimes adds wildcard A records pointing at their own IPs), the user has to delete them manually in the Cloudflare DNS dashboard before retrying.

### WebSocket HMR isn't working

Cloudflare Tunnel + Caddy support WebSockets natively. If HMR doesn't work, check:
- Next 16 with Turbopack uses different HMR endpoints than Webpack-based versions. The HMR connection should originate from the page itself with the same hostname, so it should "just work."
- If the page constructs a WebSocket URL from the wrong host (`my-project.localhost` instead of `my-project.<DOMAIN>`), same root cause as the redirect issue — needs X-Forwarded-Host trust.

## Why this is better than ngrok

- **Free** vs $10/mo+ for ngrok with custom domains.
- **No timeouts under load** — Cloudflare's edge handles bursts that ngrok's free/cheap tier rate-limits.
- **Multi-project on one tunnel** — ngrok would need one tunnel session per subdomain.
- **Wildcard support** — new worktrees auto-reachable, no config or restart.
- **Faster** — typical RTT 100–300ms vs ngrok's 500–2000ms for the same request.
- **HTTP/2 + alt-svc h3** — Cloudflare upgrades automatically.

## File map

```
~/.cloudflared/
├── cert.pem                      # auth from `cloudflared tunnel login`
├── <UUID>.json                   # per-tunnel credentials
├── config.yml                    # ingress rules
└── cloudflared.log               # daemon log

~/Library/LaunchAgents/com.<short-tag>.pubproxy.plist     # pubproxy daemon
~/Library/LaunchAgents/com.cloudflare.cloudflared.plist   # cloudflared daemon
<this-skill>/pubproxy.js                                  # the proxy script itself
<this-skill>/dev.sh                                       # dev-up/dev-down/dev-status (symlinked in ~/.local/bin)
<this-skill>/metro-takeover.sh                            # Expo Metro worktree switcher
<this-skill>/expo-qa.sh                                   # Expo fingerprint gate + EAS Update wt/ publish
<this-skill>/worktrees-gc.sh                              # prune landed agent worktrees (any repo)
<this-skill>/doctor.sh                                    # health check

~/.dev-up/<name>/                                         # per-server pidfile + log (dev-up state)
```
