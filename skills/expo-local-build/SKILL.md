---
name: expo-local-build
description: Serve locally-built Expo IPAs/APKs from this Mac to a phone over the Cloudflare tunnel. The skill owns the install-page + tunnel ingress wiring; each project owns its own `eas build --local` invocation via package.json `:local` scripts. Triggers on "serve the build", "install page", "send build to phone", "deliver expo build", "expo install URL", "publish IPA", "ad-hoc install page".
---

# expo-local-build

This skill **does not build**. Each project owns its build via `pnpm <slot>:local` scripts that wrap `eas build --local`. This skill takes the output directory and publishes it as an install page over the Cloudflare tunnel, reachable from anywhere.

The split:

| | Lives in | Owns |
|---|---|---|
| **Build**   | each project's `app/package.json` + `app/scripts/local-build.sh` | `eas build --local` invocation, macOS PATH preamble, slot naming |
| **Serve**   | this skill's `deliver.sh` + `install-server.mjs` | install page, tunnel ingress, port allocation, launchd persistence |

## Usage

```sh
SKILL=~/.claude/plugins/marketplaces/johnkueh-skills/skills/expo-local-build/scripts
bash $SKILL/deliver.sh ~/Projects/myapp/app/build-output
#   -> https://myapp-install.example.dev/   (open on phone, tap Install)
```

That's it. No flags needed for the common case. The install server reads `build-output/` directly and re-scans on every request, so rebuilding overwrites in place and the page reflects the new build immediately.

### Flags

| Flag | What it does |
|---|---|
| `--label NAME` | Override the project label (default: grandparent dir name of the build-output path, e.g. `my.app` → `my-app`). |
| `--persist` | Run the install server under launchd (`~/Library/LaunchAgents/dev.jkyf.expo-localbuild.<label>.plist`, `KeepAlive`) so it survives logout/reboot. Default is an ad-hoc background process that dies with the shell. |
| `--unpersist` | Remove that LaunchAgent. Standalone: `deliver.sh --unpersist --label <name>` (no dir needed). |

Env: `TUNNEL_TLD` (default `example.dev`).

### What the install page shows

The page lists exactly the files in `build-output/` matching `<profile>-<platform>.<ext>`:

| Slot | Filename | Card |
|---|---|---|
| Dev iOS         | `dev-ios.ipa`       | ► Install (iOS OTA manifest) |
| Preview iOS     | `preview-ios.ipa`   | ► Install |
| Prod iOS        | `prod-ios.ipa`      | ► Install |
| Dev Android     | `dev-android.apk`   | ↓ Download APK |
| Prod Android    | `prod-android.apk`  | ↓ Download APK |

Order: prod → preview → dev, iOS before Android. Any file that doesn't match the pattern is ignored — no timestamped builds, no symlinks, no historical noise. Rebuilding a slot overwrites in place.

If you want a build older than the latest, rebuild from a git tag.

## How the tunnel ingress works

`deliver.sh` picks one of two modes automatically:

- **portless/pubproxy present** (something listening on `127.0.0.1:1354`): `install-server.mjs` registers `<label>-install.localhost` in `~/.portless/routes.json` on startup, and the tunnel's wildcard rule (`*.<TUNNEL_TLD>` → pubproxy `:1354`) forwards to it. URL: `https://<label>-install.<TUNNEL_TLD>/`. This is the full [dev-up](../dev-up/SKILL.md) setup.
- **no pubproxy** (e.g. the Mac mini, hand-curated per-host ingress): `deliver.sh` wires a dedicated cloudflared ingress rule straight to the install server's port — finds the running `cloudflared tunnel run <name>`, runs `cloudflared tunnel route dns <name> <label>-localbuild.<TUNNEL_TLD>`, upserts the hostname/service block into `config.yml` (inside a managed `# BEGIN expo-local-build` block), and `SIGHUP`s cloudflared. URL: `https://<label>-localbuild.<TUNNEL_TLD>/`. The `wire-ingress.mjs` helper does the YAML surgery and backs up `config.yml` to `config.yml.bak` once.

Either way the URL only works while the Mac is awake **and** `cloudflared` is running. If it 502s, the tunnel/Mac is down — start `cloudflared tunnel run <name>` (or see the dev-up skill's `doctor.sh`). If `deliver.sh` can't find a running cloudflared it still starts the local server and prints `http://127.0.0.1:<port>/`.

State per project lives in `~/.expo-local-build/<label>/`: `server.pid`, `server.log`, and (under `--persist`) `server.out.log` / `server.err.log`. The IPAs/APKs are NOT copied here — the server reads the project's `build-output/` directly.

## Adding local builds to a new Expo project

Three pieces. Once they're in, `pnpm <slot>:local` builds and `deliver.sh` serves.

### 1. `app/scripts/local-build.sh` — env preamble wrapper

```bash
#!/usr/bin/env bash
# Wrapper for `eas build --local` that sets up the macOS PATH it needs:
#   - /opt/homebrew/bin first (so real node beats bun's node shim)
#   - Homebrew Ruby + its gem bin (where fastlane lives)
# Also unsets EXPO_TOKEN (Viewer-only robot token breaks credential resolution).
set -euo pipefail

export PATH="/opt/homebrew/bin:$PATH"

RUBY_BIN="/opt/homebrew/opt/ruby/bin"
if [ -x "$RUBY_BIN/gem" ]; then
  RUBY_GEMS_BIN="$("$RUBY_BIN/gem" env gemdir 2>/dev/null)/bin"
  export PATH="$RUBY_BIN:$RUBY_GEMS_BIN:$PATH"
fi

unset EXPO_TOKEN

eas build --local --non-interactive "$@"

# Build succeeded (set -e) — record the fingerprint this client was built from
# so expo-qa's gate (dev-up skill) can flag a stale installed client.
# Dev profile only; fail-soft so recording problems never break a build.
EXPO_QA="$HOME/Projects/claude-skills/skills/dev-up/expo-qa.sh"
if printf '%s ' "$@" | grep -q -- '--profile development' && [ -x "$EXPO_QA" ]; then
  platform=ios
  printf '%s ' "$@" | grep -q -- '--platform android' && platform=android
  EQ_PLATFORM="$platform" "$EXPO_QA" record || true
fi
```

`chmod +x` it. The trailing block pins what native baseline the dev client was
built from (`~/.expo-qa/<app>-<platform>.json`) so the dev-up skill's
`expo-qa.sh gate` can say "your installed client is stale — rebuild" *before*
you publish an update that would grey out on the device. Harmless if the
dev-up skill is absent.

### 2. `app/package.json` — one script per slot

```jsonc
"build:dev:local":            "scripts/local-build.sh --profile development --platform ios     --output build-output/dev-ios.ipa",
"build:dev:android:local":    "scripts/local-build.sh --profile development --platform android --output build-output/dev-android.apk",
"build:preview:local":        "scripts/local-build.sh --profile preview     --platform ios     --output build-output/preview-ios.ipa",
"build:prod:local":           "scripts/local-build.sh --profile production  --platform ios     --output build-output/prod-ios.ipa",
"build:android:prod:local":   "scripts/local-build.sh --profile production  --platform android --output build-output/prod-android.apk"
```

If your project sets `EXPO_APPLE_TEAM_ID` on the cloud scripts, prefix the corresponding `:local` ones too — credentials resolution needs it.

### 3. `app/.gitignore`

```
build-output/
```

### One-time machine setup (per Mac, not per project)

1. **Apple WWDR G3 cert** — download `AppleWWDRCAG3.cer` from <https://www.apple.com/certificateauthority/> and import into the **login** keychain (double-click, or `security import AppleWWDRCAG3.cer -k ~/Library/Keychains/login.keychain-db`). Required for iOS local signing — without it you get `errSecInternalComponent`.
2. **Homebrew Ruby** — `brew install ruby`. The wrapper script picks up the gem bin (where fastlane lives) automatically.
3. **EAS account** — `eas login` once. Don't set `EXPO_TOKEN` in your shell rc; the wrapper unsets it because the CI robot token is Viewer-only and breaks credential resolution.
4. **Apple Developer membership** — paid membership active under the team ID referenced in `eas.json`.
5. **Cloudflare tunnel** — see [dev-up](../dev-up/SKILL.md). The tunnel must be running for `deliver.sh` to publish a public URL.

### One-time project setup (per Expo project)

`eas init` so `app.config.ts` (or `app.json`) has an `extra.eas.projectId`. Without it, `eas build --local --non-interactive` fails with *"EAS project not configured."*

Register the device once: `eas device:create`. After that, every `development` build picks up the device automatically; `preview` / `production` ad-hoc builds need a rebuild after adding new devices.

## What this skill is NOT for

- **Shipping a real release.** App Store `.ipa` and Play `.aab` can't be sideloaded — they reject. Use the project's own `pnpm release` dispatcher.
- **Building in the cloud.** That's `eas build --profile <p> --platform <p>` (no `--local`) and lives in each project's non-`:local` `build:*` scripts.
- **Replacing the dev-client / Metro flow.** For day-to-day work, run `pnpm dev` and use the registered dev client. This skill is for handing a build to a phone — a release-config tester install, or a teammate's device, or "I'm out and need a working build now."

## Stop serving

Ad-hoc (default): `kill $(cat ~/.expo-local-build/<label>/server.pid)`
LaunchAgent (`--persist`): `deliver.sh --unpersist --label <label>`
