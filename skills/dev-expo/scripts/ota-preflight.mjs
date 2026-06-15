// OTA preflight — canonical template. Copy into a project's `scripts/` and wire
// it into the `update:*` package.json scripts (see dev-expo SKILL.md).
//
// What it guards: with `runtimeVersion: { policy: "fingerprint" }` an OTA only
// lands on a binary whose native fingerprint matches. This script computes the
// local fingerprint and aborts the publish when it has drifted from the binaries
// already deployed on the channel — so you never ship a JS update that every
// installed build silently refuses (greyed out / crash-on-load).
//
// ⚠️ DO NOT "simplify" the remote lookup back to `--limit 1` / `currentPage[0]`.
// `eas update:list` returns PER-PLATFORM update groups, newest-first and
// INTERLEAVED across platforms. Comparing the most-recent group's runtimeVersion
// to a local iOS fingerprint false-aborts whenever that newest group is Android
// (iOS and Android fingerprints differ by construction). You MUST match the
// remote runtime to the same platform as the local fingerprint. This is the
// recurring bug; the per-platform filter below is the fix.
//
// Run:  node scripts/ota-preflight.mjs --channel production
//       node scripts/ota-preflight.mjs --channel production --platform ios
//       node scripts/ota-preflight.mjs --channel production --allow-runtime-bump
//
// Pairs with `fingerprint.config.js` (pins out cosmetic churn so a squash merge
// or version bump can't drift the hash off real native changes).

import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const APP_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/** Parse the first JSON object out of mixed CLI stdout. */
function firstJson(raw) {
  const i = raw.indexOf('{');
  if (i < 0) return null;
  try {
    return JSON.parse(raw.slice(i));
  } catch {
    return null;
  }
}

/** The local native fingerprint — exactly what an EAS build bakes into the binary. */
function readLocalFingerprint(platform) {
  const result = spawnSync(
    'npx',
    ['expo-updates', 'fingerprint:generate', '--platform', platform],
    { encoding: 'utf8', cwd: APP_DIR },
  );
  if ((result.status ?? 0) !== 0) {
    console.error(`[ota-preflight] fingerprint:generate failed:\n${result.stderr}`);
    process.exit(1);
  }
  const parsed = firstJson(result.stdout);
  if (!parsed?.hash) {
    console.error('[ota-preflight] fingerprint:generate returned no hash');
    process.exit(1);
  }
  return parsed.hash;
}

/** runtimeVersion of the latest update FOR THIS PLATFORM on the branch.
 *  See the header: filtering by platform is load-bearing, not optional. */
function readRemoteRuntimeVersion(channel, platform) {
  const result = spawnSync(
    'eas',
    ['update:list', '--branch', channel, '--limit', '50', '--json', '--non-interactive'],
    { encoding: 'utf8', cwd: APP_DIR },
  );
  if ((result.status ?? 0) !== 0) {
    console.error(`[ota-preflight] eas update:list failed for branch=${channel}:\n${result.stderr}`);
    return null;
  }
  const parsed = firstJson(result.stdout);
  const updates = parsed?.currentPage ?? [];
  // `platforms` is a comma-joined string, e.g. "ios" or "android, ios".
  const match = updates.find((u) =>
    String(u.platforms ?? '')
      .split(',')
      .map((p) => p.trim())
      .includes(platform),
  );
  return match?.runtimeVersion ?? null;
}

function main() {
  const args = process.argv.slice(2);
  const allowBump = args.includes('--allow-runtime-bump');
  const channelIdx = args.indexOf('--channel');
  const channel = channelIdx >= 0 ? args[channelIdx + 1] : 'production';
  const platformIdx = args.indexOf('--platform');
  // `update:<channel>` publishes every platform, so the gate checks every
  // platform — each compared ONLY against its own latest published runtime.
  const platforms = platformIdx >= 0 ? [args[platformIdx + 1]] : ['ios', 'android'];

  console.log(`[ota-preflight] channel=${channel}  platforms=${platforms.join(',')}`);

  let drifted = false;
  for (const platform of platforms) {
    const local = readLocalFingerprint(platform);
    const remote = readRemoteRuntimeVersion(channel, platform);
    const tag = `[ota-preflight] ${platform}:`;
    console.log(`${tag} local=${local}  remote=${remote ?? '(none — first OTA)'}`);

    if (!remote) {
      console.log(`${tag} PASS — no prior ${platform} OTA on this channel`);
      continue;
    }
    if (local === remote) {
      console.log(`${tag} PASS — fingerprint matches deployed binaries`);
      continue;
    }
    if (allowBump) {
      console.log(`${tag} PASS (--allow-runtime-bump) ${remote.slice(0, 12)}… → ${local.slice(0, 12)}…`);
      continue;
    }
    console.error(
      `${tag} ABORT — fingerprint drifted:\n` +
        `  local  = ${local}\n  remote = ${remote}\n` +
        `  Existing ${platform} binaries (${remote.slice(0, 12)}…) will NOT receive this OTA.\n` +
        `  Cut and distribute a new build first — or pass --allow-runtime-bump for the first OTA after a new build.`,
    );
    drifted = true;
  }

  if (drifted) process.exit(1);
  console.log('[ota-preflight] PASS — all checked platforms OK');
}

main();
