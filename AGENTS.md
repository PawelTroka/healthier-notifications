# Working on this repository

## Purpose and preferences

Maintain a reviewable notification policy for the user's OPPO phone and Garmin watch. Desired settings and setup context are recorded in `config/policy.json` and the device guide.

The user wants calls and direct messages across all communicator apps. Work hours are exactly Monday-Friday 10:14-18:14 Europe/Warsaw. Keep personal messaging separate from work quiet hours. Clock alarms must still sound during quiet hours and sleep/DND. The chosen weekday wake-up alarm is 10:09, giving 5 minutes to be at the desk by 10:14. `config/policy.json` holds the current intent; no sleep hours or installed-app list have been confirmed yet. The real alarm still needs configuring and verifying on the device via `test.wake_alarm`.

## Current implementation

- Python 3.10+ standard library, launched with `python -m healthier_notifications` or `notifications.ps1`.
- The original Windows workspace has Python 3.14 and portable ADB 37.0.1 under ignored `.tools/platform-tools`. Fresh clones need Platform-Tools installed. No device commands have run as of initial publication.
- `android.py` reads ADB metadata and selected-user runtime notification permissions. `model.py` validates policy and compares state. `cli.py` implements preview/apply/restore and manual checks.
- Android whole-app permission automation is supported only when the live metadata passes the implemented checks. Channels, app schedules, Garmin allowlisting and watch-native controls are guided manual steps.
- `state/` is an intentionally exported summary. `.local/` holds sensitive inventory, serials, permission journals and human check notes; keep it out of Git.

## Continue with a connected phone

1. Read README and the current policy. Check ADB availability; inspect the authorized device and actual Android user rather than assuming hardware details.
2. Run `init` for the first inventory. Identify communicator/work apps from installed packages. Keep useful app notifications and tune unwanted categories at their source.
3. Preview with `plan`. Follow the user's authorization for applying specific settings. Do not infer a request to block every unknown app from “quiet by default.”
4. Complete and test the app/watch choices. Only record an attestation after the corresponding check actually happened. Garmin state is not read automatically.
5. Export status, explain pending manual checks, and distinguish observed state from desired policy. Reconcile user edits deliberately; do not overwrite desired policy from a raw dump.

## Verification and change boundaries

Run `python -m unittest discover -s tests -v` for behavior changes. Use the synthetic examples for offline smoke checks. No live hardware has been tested as of initial preparation.

Preserve write-ahead journals, per-user parsing, shared-UID/system/role protections, live preflight and readback verification. Never interpret unknown parser output as denied/allowed. Device/firmware differences should produce an actionable manual path. Keep permission grants distinct from channel alert behavior and watch delivery. Do not collect notification text or private app databases to obtain configuration state.

Primary capability references and menu/version caveats are in `docs/sources.md` and `docs/device-guide.md`.
