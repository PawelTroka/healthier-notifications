# Shared status

Run `python -m healthier_notifications status --export` with the phone connected and a reviewed public policy selected to write `status.json` and `status.md` here. These are deliberate, shareable summaries of the configured apps and checks. The first connected observation was captured on 2026-09-15; each export retains its observation timestamp.

Full inventory, serial numbers, permission snapshots, rollback journals and free-text check notes stay in ignored `.local/`. Exports omit serials, fingerprints, unconfigured inventory entries and free-text check notes, but include every configured app's package, label, permission observation and watch choice, plus every manual instruction. A fully populated policy can therefore expose an app list. `local_only: true` refuses export; keep private-profile status local without `--export`. Review a diff before committing a public report.

The public policy leaves app rules empty, so its status contains review counts without installed-app names. It does not describe the private profile's setup progress. See the [connected-session report](../docs/hardware-session.md) for selected configuration observations and remaining delivery checks.

An export describes one observation time. It is not continuous device synchronization. Manual checks are labelled as self-reported; stale, failed and unverified checks remain visible. Restoring `.local/` from another machine does not establish trust in the currently connected phone.
