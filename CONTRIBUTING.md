# Contributing

The project uses Python 3.10+ and the standard library. You can work on parsing, policy comparisons and command behavior without a phone or ADB installation.

```sh
python -m healthier_notifications validate
python -m healthier_notifications --policy examples/policy.demo.json plan --snapshot examples/snapshot.demo.json
python -m unittest discover -s tests -v
```

## Changes to device behavior

- Preserve preview defaults, explicit apply/restore, live preflight, write-ahead journals and readback verification.
- Keep unknown device state unknown. Do not infer a permission grant from its manifest declaration or another Android user's state.
- Preserve system, clock, communication, shared-UID and safety protections. Keep alarms independent of work quiet hours.
- Distinguish Android notification permission from app categories, actual alert delivery and Garmin settings.
- Add a mocked regression test for a behavior fix. Keep CI offline with respect to phones, watches and personal accounts.
- Document any actual hardware validation separately, including relevant software versions and practical limits.

## Reports and fixtures

Describe the expected behavior, the command, the observed error, and relevant Android/ColorOS or watch versions. Use synthetic package/permission fixtures for parser issues. Do not attach `.local/`, notification bodies, contact names, device serials, private account data or raw private app databases to a public issue.

The included policy is personal. Review it before applying it to another setup. Update the documentation when a change affects the intended workflow or supported controls.
