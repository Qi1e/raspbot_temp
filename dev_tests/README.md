# Development and Test Scripts

This folder is for follow-up development, smoke tests, and hardware checks.

Rules:

- Do not implement product behavior here.
- Import and call `raspbot_posture` package functions.
- Keep scripts small and focused on one verification target.
- Move reusable logic into `raspbot_posture/` before relying on it from more than one script.

HYROX detector synthetic dry run:

```bash
python3 -m dev_tests.hyrox_detector_dry_run
```
