# Carbon8 Database Backup — Restore Guide

This document explains how to restore the Carbon8 platform database from the backup
dump file, in case it is ever needed. The figures below describe the **validated backup**
taken when the project was wound down (see *Validation* at the end).

## What the backup is

- **File:** `dump-postgres-202606161314.backup` (3.66 GB / 3,833,006,798 bytes)
- **Taken from a copy at:** `…\Newbound\Email Intelligence\backup\` — keep at least one
  **off-machine copy**; this single file is the safety net for the whole dataset.
- **Format:** PostgreSQL custom-format archive (`pg_dump -Fc`), gzip-compressed, archive
  version 1.16. This is a **binary** file — it is restored with `pg_restore`, not opened in
  a text editor.
- **Source:** the Supabase-hosted PostgreSQL database, **PostgreSQL 17.6** (dumped by
  `pg_dump` 17.0 on 2026-06-16 13:14).
- **Scope:** the **`public` schema only** — the complete application database:
  219 tables, 242 functions, 13 views, 2 materialized views, 281 indexes, 206 constraints,
  101 foreign keys, 20 triggers, and the row data for 61 tables.

### What is NOT in this backup

- **Supabase `auth` schema** (user logins, passwords, sessions) — **not in the main dump**, but captured separately in a companion file (see *Companion backup — `auth` schema* below).
- **Supabase `storage`** — empty (0 buckets, 0 objects; the platform uses Google Drive, not Supabase Storage), so there is nothing to back up there.
- **The extensions themselves.** The dump contains no `CREATE EXTENSION` statements, but the schema *uses* extension-provided types/functions — see *Restore prerequisites* below.
- Supabase roles/grants beyond the `public` schema ACL.

### Verified contents (row counts, 2026-06-16)

| Table                  | Rows        |     | Table             | Rows   |
| ---------------------- | -----------:| --- | ----------------- | ------:|
| qb_operations          | 631,528     |     | thread_status     | 66,486 |
| qb_quotes              | 152,801     |     | customer_contacts | 22,364 |
| qb_sales_line_items    | 81,324      |     | qb_customers      | 15,185 |
| qb_jobs                | 71,405      |     | user_profiles     | 11     |
| email_response_metrics | 69,099      |     | mailboxes         | 8      |
| emails                 | ≈262,000 \* |     | clients           | 3      |

\* `emails` was not counted directly during validation (its `embedding`/`body_text` columns make a data-only extract very large); the figure is the known table size from
`docs/DATABASE_DESIGN.md`. All other counts above were read directly from the backup.

## Companion backup — `auth` schema (user logins)

The main dump is `public`-schema only, so a separate dump of the Supabase **`auth`** schema was taken to preserve user logins:

- **File:** `auth-schema-202606161833.backup` (~113 KB), kept alongside the main backup.
- **Format:** PostgreSQL custom-format archive (`pg_dump --schema=auth -Fc`), gzip, from PG 17.6.
- **Contents:** all 23 `auth` tables — **`auth.users` (11 rows, incl. bcrypt `encrypted_password`
  hashes)**, `auth.identities` (11 rows — OAuth/Google/Microsoft linkages), plus sessions, refresh tokens, MFA, OAuth/SAML config, etc.
- **Validated** (2026-06-16): TOC lists cleanly (220 entries), full decompression test passed, `auth.users` confirmed at 11 rows in the archive.

### Does this help? (honest assessment)

- Passwords are **bcrypt hashes**, not plaintext — only useful **re-imported into another Supabase / GoTrue auth system**, where users would then keep their existing passwords. They cannot be reversed or used elsewhere.
- OAuth users (Google/Microsoft) have **no password**; their login is the `auth.identities` row — again only meaningful re-imported into Supabase.
- The **human-meaningful** user info (names, emails, roles) already lives in
  `public.user_profiles` in the main backup. This companion file only adds the actual **credentials/identity linkage**.
- **Bottom line:** worth keeping *only* if the app may be stood back up on a new Supabase project and you want users to keep their logins. Otherwise the main backup already preserves who the users are.

### Restoring the auth data (into a NEW Supabase project)

A fresh Supabase project already has its own `auth` schema (created by GoTrue), so restore the **data only** for the relevant tables — do **not** recreate the schema or restore ephemeral rows (sessions, refresh tokens, one-time tokens):

```
# users first (FK parent), then identities:
pg_restore --data-only --table=auth.users      --dbname "<NEW_PROJECT_CONNECTION>" "auth-schema-202606161833.backup"
pg_restore --data-only --table=auth.identities --dbname "<NEW_PROJECT_CONNECTION>" "auth-schema-202606161833.backup"
```

Caveats:

- The GoTrue `auth.users` layout can drift between Supabase versions. If a data-only restore errors on a column mismatch, extract the data to SQL (`pg_restore --data-only --table=auth.users -f users.sql …`) and adjust the column list to match the target before loading.
- Don't restore `auth.sessions` / `auth.refresh_tokens` / `auth.one_time_tokens` — they're short-lived and will be invalid on a new project; users simply log in again to get fresh ones.

## Restore prerequisites

1. A running **PostgreSQL 17 server (or newer)** to restore into — a new Supabase project, a self-managed Postgres, or any hosted Postgres (AWS RDS, etc.).

2. **PostgreSQL client tools** (`pg_restore`, `psql`) **version 17 or newer** on the machine doing the restore (must be ≥ the 17.6 source).

3. **The required extensions present on the target *before* restoring** — the dump references them but does not create them:
   
   - **pgvector** as **`public.vector`** — used by 5 embedding columns
     (`emails.embedding`, `customer_companies.embedding`, `ai_email_intelligence.embedding`, and others), all typed `public.vector(768)`.
   - **uuid-ossp** as **`extensions.uuid_generate_v4()`** — used as the default for `id`
     columns.
   
   Restoring into a plain Postgres that lacks pgvector will error on the `vector` columns — that is a target-setup issue, not a problem with the backup.
   
   **Self-managed Postgres** — run on the target DB first (pgvector must be installed on the server):
   
   ```sql
   CREATE SCHEMA IF NOT EXISTS extensions;
   CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA extensions;
   CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;   -- type must resolve as public.vector
   ```
   
   **New Supabase project** — enable the **vector** and **uuid-ossp** extensions
   (Database → Extensions) before restoring. If `pg_restore` reports a missing `public.vector` type, create/relocate the `vector` extension into the `public` schema.
   
   If `pg_restore` later reports any *other* missing extension (e.g. `pg_trgm`, `pgcrypto`), create that extension on the target and re-run — the rest of the restore is unaffected.

## How to verify the backup is intact (no database needed)

Two read-only checks, neither of which restores anything:

**1. List the catalog** — confirms the header and table-of-contents are readable:

```
pg_restore --list "dump-postgres-202606161314.backup"
```

It prints every object (tables, functions, indexes, …) and the archive header (source
version, format, compression). If it lists the tables without error, the catalog is sound.

**2. Full integrity test** — decompresses **every** data block to confirm none is corrupt or
truncated (writes the SQL to the null device, touches no database):

```
# Windows
pg_restore -f NUL "dump-postgres-202606161314.backup"
# macOS / Linux
pg_restore -f /dev/null "dump-postgres-202606161314.backup"
```

Exit code 0 with no errors means the entire archive reads cleanly. (For this backup it
completed in ~48 s.)

## How to restore

### Step 1 — Prepare the target

Create the target database and its extensions (see *Restore prerequisites*). For a local Postgres:

```
createdb carbon8_restored
psql -d carbon8_restored -c "CREATE SCHEMA IF NOT EXISTS extensions;"
psql -d carbon8_restored -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\" SCHEMA extensions;"
psql -d carbon8_restored -c "CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;"
```

(Or create a new Supabase project / hosted database, enable the extensions, and note its connection string.)

### Step 2 — Restore the dump

```
pg_restore --no-owner --no-privileges --jobs 4 \
  --dbname "postgresql://USER:PASSWORD@HOST:5432/carbon8_restored" \
  "dump-postgres-202606161314.backup"
```

Notes:

- `--no-owner --no-privileges` skip the original ownership/permissions — what you want when restoring into a different server with different roles (e.g. a new Supabase project). Without them you may see harmless role-related warnings.
- `--jobs 4` restores in parallel (faster); drop it if the target is constrained.
- Add `--clean --if-exists` **only** if you are intentionally overwriting an existing database.
- A 3.66 GB restore typically takes several minutes to tens of minutes.

### Step 3 — Verify the restore

```
psql "postgresql://USER:PASSWORD@HOST:5432/carbon8_restored"

-- then at the psql prompt, spot-check against the Verified contents table above:
SELECT count(*) FROM emails;                  -- ≈ 262,000
SELECT count(*) FROM customer_contacts;       -- 22,364
SELECT count(*) FROM qb_customers;            -- 15,185
SELECT count(*) FROM qb_quotes;               -- 152,801
SELECT count(*) FROM email_response_metrics;  -- 69,099
\dt                                           -- lists all restored tables
```

If the counts and tables match, the restore is complete.

## Common issues

- **Version mismatch:** if `pg_restore` is older than the dump's source (17.6) it may refuse or warn. Use client tools **17 or newer**. Docker alternative:
  `docker run --rm -v "/path/to/backup:/dump" postgres:17 pg_restore --no-owner --no-privileges --dbname "CONNECTION_STRING" /dump/dump-postgres-202606161314.backup`
- **`type "public.vector" does not exist` / errors on `embedding` columns:** the target is missing pgvector in the `public` schema. Install pgvector and run
  `CREATE EXTENSION vector SCHEMA public;`, then re-run the restore (see *Restore prerequisites*).
- **`function extensions.uuid_generate_v4() does not exist`:** create the `extensions` schema and `uuid-ossp` extension on the target (see *Restore prerequisites*).
- **Role/permission warnings:** harmless when using `--no-owner --no-privileges`; the data still restores correctly.
- **Auth/logins missing after restore:** expected — this backup is `public`-schema only and does not include the Supabase `auth` schema.

## Notes for re-deploying the full platform

This backup is the **data layer only**. A full platform restart would also need:

- The application code (this GitHub repository).
- Environment variables / secrets (Railway configuration — held separately; secrets are not in this backup or in the repo).
- The Railway service topology (the sync cron services for Gmail, Outlook, and QuickBase).
- Supabase **auth** users (and **storage**), if working logins are required — not in this backup.

The application code and a deployment runbook are in the GitHub repository; the environment configuration is documented separately (secrets scrubbed).

## Validation

This guide describes a backup that was validated on **2026-06-16** with `pg_restore` 18.4
against the actual file. Checks performed and passed:

- Archive header / format confirmed (`PGDMP`, custom format, gzip, archive v1.16; source PG 17.6).
- Catalog listing (`pg_restore --list`) — 1,181 TOC entries, no errors.
- Full decompression integrity test (`pg_restore -f NUL`) — all data blocks read cleanly, exit 0 in ~48 s.
- Row counts read directly from the archive for the key tables (see *Verified contents*).
- Schema scope confirmed `public`-only; extension dependencies (pgvector, uuid-ossp) identified.

**Verdict: the backup is intact, complete for the `public` schema, and restorable** into a PostgreSQL 17+ target that has the pgvector and uuid-ossp extensions available.
