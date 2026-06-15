---
name: dev-expo
description: Build Expo IPAs/APKs locally (zero EAS build credits) and deliver them to a phone via Vercel Blob + a per-project drafty "builds" canvas with an Install button — works from anywhere, Mac asleep. The skill owns publish-build.sh (Blob upload + OTA manifest + canvas update); each project owns its own `eas build --local` invocation via package.json `:local` scripts whose wrapper also records the dev-client fingerprint for the dev-up skill's expo-qa gate. Triggers on "publish the build", "send build to phone", "deliver expo build", "install page", "builds canvas", "expo install URL", "publish IPA", "ad-hoc install", "local eas build".
---

# dev-expo
This skill **does not build**. Each project owns its build via `pnpm <slot>:local`
scripts that wrap `eas build --local` (zero EAS build credits — the build runs
on this Mac). This skill takes the built artifact and **publishes it durably**:
IPA + iOS OTA manifest to Vercel Blob, then one drafty canvas per project
("`<label>` builds") gets the Install button and history. Installs work from
anywhere — cellular, Mac asleep.

| | Lives in | Owns |
|---|---|---|
| **Build**   | each project's `app/package.json` + `app/scripts/local-build.sh` | `eas build --local` invocation, macOS PATH preamble, slot naming, fingerprint record |
| **Publish** | this skill's `publish-build.sh` | Blob upload, OTA manifest, the per-project builds canvas |

## Usage

```sh
SKILL=~/.claude/plugins/marketplaces/johnkueh-skills/skills/dev-expo/scripts
bash $SKILL/publish-build.sh ~/Projects/myapp/app/build-output
#   Canvas:  https://drafty.im/canvas/<label>-builds-<suffix>   ← stable; bookmark on the phone
#   Install: itms-services://?action=download-manifest&url=…    ← also on the canvas button
```

Flags: `--slot dev-ios` (default; any `<profile>-<platform>` filename in
build-output), `--label NAME` (default: the repo's root dir name, dots→hyphens,
e.g. `journeys.im` → `journeys-im`).

What it does: extracts bundle id / version / embedded runtime fingerprint from
the IPA → uploads IPA + generated `manifest.plist` to Blob under
`build-artifacts/<label>/<slot>-<commit>-…` → appends to the project's build
history → re-renders and pushes the **same canvas** (slug pinned after the
first push). Android APKs upload the same way and link as a plain download.

State:
- `~/.dev-expo/blob-token` — RW token for the shared `build-artifacts`
  Blob store (team store `store_fLNDBgquUTtfk9Ed`, connected to journeys-im-web
  as `BUILD_ARTIFACTS_*` for token minting). One store serves every project,
  path-namespaced. `$BLOB_READ_WRITE_TOKEN` overrides.
- `~/.dev-expo/<label>/builds.json` — history (newest first, capped 50).
- `~/.dev-expo/<label>/canvas-slug` — the drafty slug after first push.

Canvas notes: visibility follows drafty's default (sign-in-gated) — the owner
can `drafty canvas visibility <slug> public` for tap-from-anywhere; the real
protection is the unguessable Blob URLs. The Install button uses
`target="_top"` so the tap escapes the canvas artifact iframe.

Retired 2026-06-13: `deliver.sh` / `install-server.mjs` / `wire-ingress.mjs`
(the serve-from-this-Mac-over-the-tunnel path). Blob delivery replaced it —
the old way needed the Mac awake at install time. If you ever need the
nothing-leaves-the-Mac variant, it's in git history (pre-2026-06-13).

## Adding local builds to a new Expo project

Three pieces. Once they're in, `pnpm <slot>:local` builds and `publish-build.sh`
delivers.

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

# Build succeeded — shared post-build tail. Records the dev-client fingerprint
# (for expo-qa's stale-client gate) AND publishes the artifact to the project's
# builds canvas. Dev-profile only, fail-soft; no-op if the skill is absent.
POST_BUILD="$HOME/Projects/claude-skills/skills/dev-expo/scripts/post-build.sh"
[ -x "$POST_BUILD" ] && "$POST_BUILD" "$@" || true
```

`chmod +x` it. The PATH preamble is the only per-project part you adapt; the
trailing one-liner hands off to `scripts/post-build.sh`, which is the single
source of truth for the two mechanical after-build steps (don't re-inline
them):

1. **`expo-qa record`** — pins the native baseline the dev client was built
   from (`~/.expo-qa/<app>-<platform>.json`) so the dev-up skill's
   `expo-qa.sh gate` can warn "your installed client is stale — rebuild"
   *before* you publish an update that would grey out on the device.
2. **`publish-build`** — auto-delivers the `--output` artifact to the project's
   "<label> builds" canvas, so the latest installable build is always one tap
   away (no manual publish step).

Both are dev-profile only and fail-soft — a hiccup never fails a build that
already succeeded — and both no-op cleanly if the skills aren't installed.

### 2. `app/package.json` — one script per slot

```jsonc
"build:dev:local":            "scripts/local-build.sh --profile development --platform ios     --output build-output/dev-ios.ipa",
"build:dev:android:local":    "scripts/local-build.sh --profile development --platform android --output build-output/dev-android.apk",
"build:preview:local":        "scripts/local-build.sh --profile preview     --platform ios     --output build-output/preview-ios.ipa",
"build:prod:local":           "scripts/local-build.sh --profile production  --platform ios     --output build-output/prod-ios.ipa",
"build:android:prod:local":   "scripts/local-build.sh --profile production  --platform android --output build-output/prod-android.apk"
```

If your project sets `EXPO_APPLE_TEAM_ID` on the cloud scripts, prefix the
corresponding `:local` ones too — credentials resolution needs it.

### 3. `app/.gitignore`

```
build-output/
```

### One-time machine setup (per Mac, not per project)

1. **Apple WWDR G3 cert** — download `AppleWWDRCAG3.cer` from <https://www.apple.com/certificateauthority/> and import into the **login** keychain (double-click, or `security import AppleWWDRCAG3.cer -k ~/Library/Keychains/login.keychain-db`). Required for iOS local signing — without it you get `errSecInternalComponent`.
2. **Homebrew Ruby** — `brew install ruby`. The wrapper script picks up the gem bin (where fastlane lives) automatically.
3. **EAS account** — `eas login` once. Don't set `EXPO_TOKEN` in your shell rc; the wrapper unsets it because the CI robot token is Viewer-only and breaks credential resolution.
4. **Apple Developer membership** — paid membership active under the team ID referenced in `eas.json`.
5. **Blob token** — put the `build-artifacts` store's RW token in `~/.dev-expo/blob-token` (chmod 600). The store lives on the Vercel team; mint a token by connecting the store to any project (env prefix keeps it inert).
6. **drafty CLI** — the drafty plugin must be installed and logged in (the canvas push runs as the owner).

### One-time project setup (per Expo project)

`eas init` so `app.config.ts` (or `app.json`) has an `extra.eas.projectId`. Without it, `eas build --local --non-interactive` fails with *"EAS project not configured."*

Register the device once: `eas device:create`. After that, every `development` build picks up the device automatically; `preview` / `production` ad-hoc builds need a rebuild after adding new devices.

## What this skill is NOT for

- **Shipping a real release.** App Store `.ipa` and Play `.aab` can't be sideloaded — they reject. Use the project's own `pnpm release` dispatcher.
- **Building in the cloud.** That's `eas build --profile <p> --platform <p>` (no `--local`) and lives in each project's non-`:local` `build:*` scripts.
- **Replacing the dev-client / Metro flow.** For day-to-day JS work, run `pnpm dev` and use the registered dev client (and the dev-up skill's `expo-qa.sh publish` for branch QA via EAS Update). This skill is for handing a *binary* to a phone — a new dev client after native changes, a release-config tester install, or a teammate's device.
