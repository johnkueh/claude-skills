#!/usr/bin/env bash
# post-build.sh — the shared "after a successful local dev build" tail for any
# Expo project's scripts/local-build.sh. Two mechanical steps, dev-profile only
# and fail-soft (a hiccup here never fails the build that already succeeded):
#
#   1. expo-qa record — pin the native fingerprint this dev client was built
#      from (~/.expo-qa/<app>-<platform>.json) so the dev-up skill's
#      `expo-qa.sh gate` can flag a stale installed client before you publish
#      an update that would grey out on the device.
#   2. publish-build  — ship the IPA/APK to the project's "<label> builds"
#      drafty canvas (Blob-backed install surface). Auto-published so the
#      canvas always has the latest installable build — no manual step.
#
# Wire a project by ending its scripts/local-build.sh with:
#
#   POST_BUILD="$HOME/Projects/claude-skills/skills/expo-local-build/scripts/post-build.sh"
#   [ -x "$POST_BUILD" ] && "$POST_BUILD" "$@" || true
#
# (pass the same eas-build flags through). Both steps no-op gracefully if their
# helper scripts are absent, so the wrapper works on a machine without these
# skills installed.
#
# NOT `set -e`: every step is best-effort. Only dev builds are handled —
# preview/prod `.ipa`/`.aab` are store artifacts that reject sideload.
set -uo pipefail

ARGS=("$@")
[ "${#ARGS[@]}" -gt 0 ] || exit 0
printf '%s ' "${ARGS[@]}" | grep -q -- '--profile development' || exit 0

SKILLS="$HOME/Projects/claude-skills/skills"

platform=ios
printf '%s ' "${ARGS[@]}" | grep -q -- '--platform android' && platform=android

# 1. record the fingerprint for expo-qa's stale-client gate
EXPO_QA="$SKILLS/dev-up/expo-qa.sh"
if [ -x "$EXPO_QA" ]; then
  EQ_PLATFORM="$platform" "$EXPO_QA" record || true
fi

# 2. publish the built artifact (the --output path) to the builds canvas
PUBLISH_BUILD="$SKILLS/expo-local-build/scripts/publish-build.sh"
if [ -x "$PUBLISH_BUILD" ]; then
  out=""; prev=""
  for a in "${ARGS[@]}"; do
    [ "$prev" = "--output" ] && out="$a"
    prev="$a"
  done
  if [ -n "$out" ] && [ -f "$out" ]; then
    "$PUBLISH_BUILD" "$out" || true
  else
    echo "[post-build] no --output artifact found; skipping builds-canvas publish" >&2
  fi
fi

exit 0
