# Publishing the Repository

What was checked before making this repository public (feat-022), and the steps only the owner
can take.

## Checked in the repository

| Check | Result |
|---|---|
| Provider keys, tokens and private keys in every commit on every branch | none found |
| `.env` files tracked | never; only `.env.example`, whose key values are empty |
| Local machine paths (user profiles, local project folders) in tracked files | none; rule `arch-107` now rejects them |
| Cloud project identifiers and personal email addresses in tracked files | removed from two session notes |
| License | MIT, copyright holder set to the owner |
| Vulnerability reporting | [`SECURITY.md`](../SECURITY.md) |
| Default database passwords (`change-me-*`) | placeholders for the local Docker database only |

Older commits still contain the two session-note details that were removed (a Google Cloud
project number, which grants no access, and the author's email). The commit author email is
public in every commit. Rewriting history for these was judged not worth breaking existing
clones and recorded verification evidence (D-020).

## Owner steps

These change account or repository settings, so the owner does them on GitHub:

1. **Commit email privacy (optional).** In GitHub, Settings → Emails, enable
   "Keep my email addresses private". This clone already commits with the GitHub noreply
   address.
2. **Private vulnerability reporting.** In the repository, Settings → Code security, enable
   "Private vulnerability reporting" so the `SECURITY.md` route works.
3. **Visibility.** In the repository, Settings → General → Danger Zone → Change visibility →
   Public. Anyone can clone the repository while it is public, so this cannot be fully undone.

## Before each later push

`npm run check` runs the architecture rules (keys, local paths) on tracked files. Stage new
files before running it: the rules see only tracked or staged files.
