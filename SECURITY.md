# Security Policy

## Supported versions

Only the `main` branch is maintained. Fixes are not backported.

## Reporting a vulnerability

Please report security problems privately through GitHub: open the repository's
**Security** tab and choose **Report a vulnerability**. Do not open a public issue for a
suspected vulnerability.

Include what you found, how to reproduce it, and what an attacker could do with it. You can
expect an acknowledgement within a week.

## Scope

This is a portfolio project that runs on synthetic data. It ships with no real customer data,
no production credentials and no deployed service. Reports that matter most:

- a way around the tool gateway: a tool call, write or approval that skips its allowlist,
  role permission, argument or approval-binding checks;
- data crossing tenants, or a role reading documents or sales data it should not see;
- a secret, prompt or document text reaching logs, traces or evaluation reports;
- a live model call made without the explicit opt-in and budget the documentation requires.

Never commit a real provider key, even in an issue or pull request. The repository's
architecture rules reject key-shaped strings and local machine paths in tracked files.
