# Security and Environment Handling

## Production rule

Never commit local configuration, secrets, browser profiles, OAuth tokens, generated dashboards, logs, or runtime data to GitHub.

All production secrets must be supplied through the deployment platform or GitHub Actions secrets.

## Required pre-launch checklist

Before any public deployment:

- Rotate any credential that may have appeared in local files, logs, screenshots, commits, or shared archives.
- Replace local `.env` values after rotation.
- Update GitHub Actions or cloud provider secrets with the new values.
- Confirm `.env` and local runtime files are not tracked by Git.
- Run a secret scan before merging production branches.
- Confirm webhook endpoints validate their configured shared secret.
- Confirm application-submitting flows are disabled unless explicitly approved.

## Environment files

Use `.env` only for local development. Use `.env.example` only for placeholders and documentation.

Safe pattern:

```env
TELEGRAM_BOT_TOKEN=replace_me
DATABASE_URL=postgresql://user:password@host:port/database
RICO_ENABLE_AUTO_APPLY=false
RICO_REQUIRE_APPROVAL_FOR_APPLICATIONS=true
```

Unsafe pattern:

```env
TELEGRAM_BOT_TOKEN=actual-token-value
DATABASE_URL=actual-production-connection-string
```

## Runtime defaults

Production defaults should be conservative:

```env
RICO_ENABLE_AUTO_APPLY=false
RICO_REQUIRE_APPROVAL_FOR_APPLICATIONS=true
RICO_INTERACTIVE_APPLY=false
NG_ENABLED=false
NG_DRY_RUN=true
```

Application submission, browser automation, and recruiter-facing actions must require explicit operator approval or an explicit environment flag.

## Logging rules

Do not log:

- tokens
- passwords
- full database URLs
- OAuth credential contents
- webhook secrets
- raw uploaded CV contents
- private email bodies unless explicitly needed for debugging in a secure environment

Allowed logs:

- whether a required variable is set
- non-sensitive service readiness
- counts, statuses, and error categories
- masked identifiers only when needed

## GitHub Actions and cloud deployment

Store production values in GitHub Actions secrets or the cloud provider secret manager. Do not place them in workflow YAML or Docker images.

Recommended checks before deployment:

```bash
git status --short
git ls-files .env .env.local credentials.json token.json
git grep -n "TOKEN\|PASSWORD\|SECRET\|DATABASE_URL\|API_KEY" -- . ':!docs/SECURITY.md' ':!.env.example'
```

The `git grep` command can produce false positives in documentation and placeholder files. Review results manually.

## Incident response

If a secret is exposed:

1. Revoke or rotate it in the provider dashboard.
2. Update deployment secrets.
3. Remove the local exposed file.
4. If committed, remove it from Git history using a history-cleaning tool.
5. Force-refresh affected services.
6. Review logs for unexpected usage.
