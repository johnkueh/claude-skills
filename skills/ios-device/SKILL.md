---
name: ios-device
description: Interact with a physically paired iPhone/iPad over the wireless CoreDevice tunnel — stream app console output, gather a sysdiagnose, list processes, copy files in and out of an app sandbox, send Darwin notifications, trigger memory warnings, reboot. Use when the user wants to debug, inspect, or poke at a real iOS device (not a simulator). Triggers on "device logs", "iphone logs", "logs from my phone", "devicectl", "device console", "sysdiagnose", "real device debug", "app crash on device", "pull file off iphone", "push file to iphone", "memory warning", "reboot iphone".
---

# ios-device

Drive a physically paired iOS device using Apple's bundled `xcrun devicectl` (CoreDevice). This is the **first-party** path — works wirelessly once paired, no `libimobiledevice` install required.

Scope split:
- **This skill** — logs, processes, sysdiagnose, file copy in/out of app sandboxes, notifications, memory warnings, reboot.
- **`expo-local-build`** — building and delivering an `.ipa` / `.app` to the device.
- **`vercel-logs`** — server-side logs.

## When devicectl is the right tool

| Want | Use devicectl? | Notes |
|---|---|---|
| Stream a specific app's stdout/stderr | **Yes** | `process launch --console` |
| Full system syslog (every process, live) | No | devicectl has no syslog subcommand — use `idevicesyslog` (libimobiledevice, requires USB) |
| Full historical sysdiagnose archive | **Yes** | Heavy (~hundreds of MB); device must be unlocked |
| Crash reports / hangs / spindumps | **Yes** | Inside the sysdiagnose tarball |
| List running processes | **Yes** | `device info processes` |
| Install / uninstall / launch apps | **Yes** | Useful for QA harness setup |

## Bootstrap — find the device identifier

```sh
xcrun devicectl list devices
```

Returns a table including `Identifier` (UUID form) and `Name`. **Always use the Identifier** — name lookup is unreliable when the name contains a smart-quote (`John K's iPhone` → "device not found" because the apostrophe is U+2019). The Identifier is stable across reboots.

Stash it:

```sh
DEVICE=$(xcrun devicectl list devices 2>/dev/null | awk '/available \(paired\)/ {print $(NF-2); exit}')
echo "$DEVICE"   # e.g. 30612557-5967-5EB4-BFC2-DDF0EDB5DBA9
```

> The harmless `Failed to load provisioning paramter list ... No provider was found.` warning prints on every invocation. Ignore it — it does not affect the operation. Redirect stderr if scripting.

## Stream a single app's console

```sh
xcrun devicectl device process launch \
  --device "$DEVICE" \
  --console \
  --terminate-existing \
  <bundle-id>
```

What `--console` does: attaches the launched process's stdout/stderr to your terminal. You see exactly what the app prints (NSLog, `print()`, JS console for RN/Expo dev builds, etc.). Ctrl-C detaches; the process keeps running on device.

Flags worth knowing:
- `--terminate-existing` — kill an already-running instance first; otherwise launch silently no-ops.
- `--environment-variables '{"KEY":"VALUE"}'` — inject env vars at launch (JSON).
- `--arguments arg1 --arguments arg2` — pass argv.
- `--start-stopped` — launch suspended (pair with `process resume` for debugger attach).

The bundle ID is the **app** bundle ID, not the team/parent. For Expo dev builds it's the `ios.bundleIdentifier` from `app.config.ts`. For App Store apps you can find it with:

```sh
xcrun devicectl device info apps --device "$DEVICE" | grep -i <app-name>
```

## Pull a sysdiagnose (full system snapshot)

```sh
xcrun devicectl device sysdiagnose \
  --device "$DEVICE" \
  --destination ~/Desktop/sysdiagnose-$(date +%Y%m%d-%H%M)
```

- Takes 3–10 minutes on the device side, plus transfer.
- Device must be **unlocked** and stays unlocked through the process.
- Produces a tarball with crash logs, spindumps, system log archives, network state, etc.
- Add `--gather-full-logs` for the verbose variant (much bigger).

Inside the archive, the most useful directories:
- `crashes_and_spins/` — `.ips` crash reports per process
- `logs/` — `.logarchive` you can open with `Console.app` or query with `log show --archive <path>`
- `WiFi/`, `Network/`, `Accessibility/` — domain dumps

To slice the logarchive for a specific app/time after extracting:

```sh
log show --archive /path/to/system_logs.logarchive \
  --predicate 'process == "<process-name>"' \
  --start "2026-05-12 14:00:00" --end "2026-05-12 14:30:00" \
  --info --debug
```

## List running processes

```sh
xcrun devicectl device info processes --device "$DEVICE" \
  --json-output /tmp/procs.json 2>/dev/null
jq '.result.runningProcesses[] | {pid: .processIdentifier, name: .executable}' /tmp/procs.json
```

`--json-output` is **the only supported machine-readable interface**; the table that prints to stdout is for humans and can change between Xcode versions.

## Launch / terminate apps

```sh
xcrun devicectl device process launch --device "$DEVICE" <bundle-id>
xcrun devicectl device process terminate --device "$DEVICE" --process-identifier <pid>
```

For **installing** an IPA, see the dedicated `ios-install-ipa` skill.

## List installed apps (find a bundle ID)

```sh
xcrun devicectl device info apps --device "$DEVICE" \
  --json-output /tmp/apps.json 2>/dev/null
jq -r '.result.installedApplications[] | "\(.bundleIdentifier)\t\(.name)"' /tmp/apps.json
```

## Copy files in/out of an app's sandbox

Useful for swapping in test fixtures, pulling a SQLite DB / Realm file off the device, or grabbing an in-app log file.

```sh
# Push a local file into the app's Documents dir
xcrun devicectl device copy to \
  --device "$DEVICE" \
  --domain-type appDataContainer \
  --domain-identifier <bundle-id> \
  --source ./fixture.json \
  --destination Documents/fixture.json

# Pull a file off the device
xcrun devicectl device copy from \
  --device "$DEVICE" \
  --domain-type appDataContainer \
  --domain-identifier <bundle-id> \
  --source Documents/app.sqlite \
  --destination ./app.sqlite

# Browse what's in the sandbox first
xcrun devicectl device info files \
  --device "$DEVICE" \
  --domain-type appDataContainer \
  --domain-identifier <bundle-id> \
  --username mobile
```

`--domain-type` accepts `appDataContainer` (the most common — `Documents/`, `Library/`, `tmp/`), `appGroupContainer` (shared group), or `temporary`. The app must be signed with a profile your machine can talk to (i.e. a dev/enterprise build, not an App Store one).

## Force a memory-pressure warning

Triggers `applicationDidReceiveMemoryWarning` / `didReceiveMemoryWarning` codepaths without having to actually exhaust memory.

```sh
xcrun devicectl device process sendMemoryWarning \
  --device "$DEVICE" \
  --process-identifier <pid>
```

Find the pid via `device info processes` (see above).

## Post / observe Darwin notifications

System-wide notify keys — useful for triggering features gated on system events (locale change, dark mode, custom app notify keys).

```sh
# Trigger something the app is subscribed to
xcrun devicectl device notification post --device "$DEVICE" com.example.app.refresh

# Watch for a key being posted (debugging cross-process events)
xcrun devicectl device notification observe --device "$DEVICE" com.apple.system.timezone
```

## Reboot

```sh
xcrun devicectl device reboot --device "$DEVICE"
```

Returns immediately; the device drops off the tunnel for ~30–60s while it restarts.

## Gotchas

- **Smart-quote in device name** — `John K's iPhone` (curly `’`) fails as `--device`; always use the UUID Identifier.
- **`No provider was found.` warning** — printed on every command, ignore. It refers to provisioning-profile machinery you don't need for log/info ops.
- **`idevice_id -l` returns empty** — that means libimobiledevice (usbmuxd) doesn't see the device. devicectl uses CoreDevice and works over wireless pairing, so prefer it for any wireless-only device. If you want `idevicesyslog`'s live system syslog you must plug in via USB.
- **`process launch --console` doesn't show logs from already-running app** — you have to launch it under devicectl (or use `--terminate-existing`). It is not an attach-to-running-process tap.
- **Device must be unlocked** for sysdiagnose and most `info` commands. A locked device returns `Device is passcode protected` style errors.
- **No equivalent of `vercel logs --since 30m --query "foo"`** — devicectl is per-launch streaming or full snapshot only. For historical search across the system, you need the sysdiagnose logarchive + `log show --predicate`.

## What NOT to do

- Don't try `xcrun devicectl device logs` — there is no `logs` subcommand. The verb you want is `process launch --console` (per-app) or `sysdiagnose` (whole system, frozen point in time).
- Don't pipe `devicectl ... | grep ...` for scripts — parse `--json-output` instead. The human table format is unstable.
- Don't run sysdiagnose in the middle of a flaky network — transfer can take many minutes; let it finish before iterating.
- Don't reach for Homebrew `idevicesyslog`/`libimobiledevice` first. It only works on USB-tethered devices that usbmuxd can see; devicectl works for the wireless case too and is the supported Apple-bundled path.
