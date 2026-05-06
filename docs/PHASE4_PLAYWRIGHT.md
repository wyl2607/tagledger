# Phase 4 Playwright SaaS Submission

Phase 4 is currently a safe submission skeleton. Selectors are placeholders, and `dry_run` defaults to `true`, so the worker fills the form and saves screenshots without clicking the real submit button.

## Enable Optional Dependency

```bash
pip install -e ".[submit]"
playwright install chromium
```

The project does not install Chromium automatically. Run the Playwright install command manually on the host that will perform SaaS submission.

## Environment Variables

```bash
export SAAS_USERNAME="your-username"
export SAAS_PASSWORD="your-password"
```

If either variable is missing, startup forces `dry_run=True` even when `config/settings.yaml` says otherwise, and logs a warning.

## Selector Maintenance

Edit `config/saas_selectors.yaml`.

- `saas.login_url`: SaaS login page.
- `saas.form_url`: new equipment/record form page.
- `saas.selectors.login.*`: username, password, and login submit controls.
- `saas.selectors.form.*`: record fields, category radios, upload input, and submit button.
- `saas.selectors.success_indicator`: element that appears after a successful real submit.

All selectors must live in YAML. Do not hard-code real SaaS selectors in Python modules.

## Dry Run vs Real Submit

Default safe mode:

```yaml
app:
  dry_run: true
```

In dry-run mode, `SaaSClient` returns before clicking the submit selector and saves:

```text
data/screenshots/dryrun_<id>_<timestamp>.png
```

To enable real submit after selectors and credentials are verified:

```yaml
app:
  dry_run: false
```

Then set `SAAS_USERNAME` and `SAAS_PASSWORD` before starting the API. Without both variables, the app falls back to dry-run.

## Failure Recovery

`POST /confirm/{id}` dispatches the submit worker in the background. On restart, the FastAPI lifespan scans `confirmed` records and re-enqueues them.

Failures update the record with:

- `submission_attempts`
- `last_error`
- `error_screenshot`
- `submission_failed` after `submission_retries`

Retries use exponential backoff:

```text
5s -> 30s -> 2min
```

For troubleshooting, inspect:

```text
data/screenshots/
logs/playwright.log
```
