# Shared status

Run `python -m healthier_notifications status --export` with the phone connected to write `status.json` and `status.md` here. These are deliberate, shareable summaries of the configured apps and checks. No device has been observed yet.

Full inventory, serial numbers, permission snapshots, rollback journals and free-text check notes stay in ignored `.local/`. The exported files contain no serial, fingerprint, complete installed-app inventory or free-text check notes. App names and packages already present in the policy can appear in the summary. Review a diff before committing it.

An export describes one observation time. It is not continuous device synchronization. Manual checks are labelled as self-reported; stale, failed and unverified checks remain visible. Restoring `.local/` from another machine does not establish trust in the currently connected phone.
