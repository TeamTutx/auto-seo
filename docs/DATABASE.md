# Database: rebuild, migrate, move

Everything Signal stores lives in one Postgres database. This is the runbook for
creating a fresh one, moving to a different one, and checking afterwards that
the new database is actually correct.

Signal's schema is owned by Alembic migrations in `backend/alembic/versions/`.
`alembic upgrade head` on an **empty** database builds the whole thing from
scratch, and on an existing one applies only what's missing — so the same
command works for a new database and an upgrade.

---

## 1. Point a brand-new database at Signal

You need the connection URL of an empty Postgres database. On Render:
*New → Postgres*, then copy its **Internal Database URL** (same region as the
API) or the External one if you're connecting from your laptop.

```bash
export DATABASE_URL="postgresql://user:password@host:5432/dbname"
cd backend
.venv/bin/alembic upgrade head
```

That's the whole migration. It creates every table, every index and the starting
credit-pack catalog. Then verify it (§4) before sending traffic at it.

> **URL scheme.** Aiven (and others) hand out `postgres://`, which SQLAlchemy 2
> rejects. Both `app/database.py` **and** `alembic/env.py` rewrite that prefix, so
> either form works in `DATABASE_URL`. Both, because Alembic builds its own
> engine: fixing only the app left the API happy and killed every deploy on
> `alembic upgrade head` with `Can't load plugin: sqlalchemy.dialects:postgres`.
> That is how the Aiven cutover failed the first time.
> Add `?sslmode=require` when connecting to a managed database from outside its
> network.

### What a fresh database contains

| Table | What it holds |
| --- | --- |
| `user` | accounts, credit balance, Dodo customer id |
| `site`, `page` | what a user tracks, plus their chosen GSC/GA property |
| `audit`, `check` | each scan and its individual results |
| `keywordrank` | one row per rank measurement, with the location/device it used |
| `alert`, `appliedfix` | regression alerts and the fix-then-verify loop |
| `googleconnection` | one connected Google account per user (tokens encrypted) |
| `product` | the credit packs on sale — seeded, then edited in `/admin/pricing` |
| `credittransaction` | the credit ledger; it always sums to `user.credits_balance` |
| `payment` | money in and out, including refunds as negative rows |
| `adminauditlog` | every admin action and payment webhook |
| `sitejob` | progress of a crawl, keyword discovery or visibility run |
| `keywordidea` | suggested keywords and which source proposed them |
| `visibilitycheck` | one row per keyword per engine per visibility run |

The migration seeds three credit packs (10 for $2, 50 for $5, 200 for $15). They
are a starting point — change them in `/admin/pricing`, which is also where you
paste the Dodo product ids. The app re-seeds this catalog on startup **only if
the `product` table is completely empty**, so it can never undo your edits.

### Environment the app needs beyond `DATABASE_URL`

`DATABASE_URL` alone gets the schema up. A working deployment also needs
`SECRET_KEY`, `FRONTEND_URL`, `CORS_ORIGINS`, `ADMIN_EMAILS`, the Google OAuth
client (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`,
`GOOGLE_LOGIN_REDIRECT_URI`), the vendor keys (`SERPAPI_KEY`, `OPENAI_API_KEY`)
and, for billing, `DODO_API_KEY` / `DODO_WEBHOOK_KEY` / `DODO_ENVIRONMENT`.
`backend/.env.example` is the full list; `render.yaml` is what production uses.

---

## 2. Moving an existing database somewhere else

Copy the data first, then let Alembic bring the copy up to date.

```bash
# 1. Stop writes. On Render: suspend the web service, or put it in maintenance.

# 2. Dump the old database.
pg_dump --no-owner --no-acl --format=custom "$OLD_DATABASE_URL" -f signal.dump

# 3. Restore into the new, empty one.
pg_restore --no-owner --no-acl --dbname="$NEW_DATABASE_URL" signal.dump

# 4. Apply anything the old database hadn't reached yet.
DATABASE_URL="$NEW_DATABASE_URL" .venv/bin/alembic upgrade head

# 5. Verify (§4), then repoint DATABASE_URL and restart the service.
```

`--no-owner --no-acl` matters: the role names on the old host almost certainly
don't exist on the new one, and without these flags the restore fails on every
`ALTER ... OWNER TO`.

Keep the old database around, read-only, until the new one has served real
traffic for a day. Render's free Postgres **expires 30 days after it is
created** and is then deleted — so this move is something you will have to do,
on a deadline, whether you planned to or not.

### How the Aiven move was actually done (2026-09-26)

Production moved off Render's free Postgres (due for deletion on 18 October) to
**Aiven free tier: PostgreSQL 18, DigitalOcean Bangalore, 1 CPU / 1 GB / 5 GB**.
The procedure above assumes `pg_dump`/`pg_restore`; neither was installed and
Docker wasn't running, so the copy ran through Python instead — worth recording
because it needs no client tools and is re-runnable:

1. `alembic upgrade head` against the empty Aiven database, then `alembic check`
   to prove the schema matches the models. All 14 migrations ran unchanged on
   PostgreSQL 18 against a source running 16.
2. Copy the data table by table in `SQLModel.metadata.sorted_tables` order (that
   is already foreign-key dependency order) with `COPY ... TO STDOUT` into
   `COPY ... FROM STDIN`, skipping `alembic_version` because Alembic owns it.
   Columns are listed explicitly so a schema mismatch fails loudly instead of
   silently shifting columns.
3. **Reset every sequence.** The ids arrive as literal values, so each table's
   identity sequence is still at 1 and the next insert collides with row 1.
   `setval(pg_get_serial_sequence(...), max(id))` per table.
4. Verify: per-table row counts on both sides, the credit invariant (each user's
   `credits_balance` equals the sum of their `credittransaction.delta`), and one
   insert inside a transaction that is rolled back, to prove sequences are sane.

The script is short enough to rewrite from this description; the important part
is steps 3 and 4, which a naive `--data-only` dump also needs and usually skips.

### Connection limits are the surprise

Aiven's free plan allows **20 connections and its own agents hold about 13**, so
roughly 7 are left for Signal. SQLAlchemy's default pool is 5 + 10 overflow per
process, which would exhaust that under any concurrency — including the
`alembic upgrade head` that runs on every deploy. `app/database.py` therefore
pins a small pool and enables `pool_pre_ping`, which also matters because the API
(Singapore) and the database (Bangalore) are now in different regions and idle
connections get dropped in between.

### Starting over from nothing instead

If the data doesn't matter (a staging box, a local reset), skip the dump: point
`DATABASE_URL` at the empty database and run `alembic upgrade head`. You'll get
the schema and the seeded packs, and no users. Your own account is recreated the
first time you sign in with Google; keep your address in `ADMIN_EMAILS` and
you're still the admin, because admin comes from that env var and is never
stored in the database.

---

## 3. Local development

`backend/signal.db` (SQLite) is built by `SQLModel.metadata.create_all()`, not by
Alembic — it has **no migration history**, and `alembic current` prints nothing
there. `create_all()` adds missing *tables* but never new *columns*, so after a
model change you have to either:

```bash
sqlite3 backend/signal.db "ALTER TABLE product ADD COLUMN badge VARCHAR;"
```

or delete `backend/signal.db` and let it rebuild empty. Don't assume writing the
migration fixed your dev database — it didn't.

To develop against Postgres instead (worth doing before any schema change):

```bash
docker run -d --name signal-pg -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=signal -p 5433:5432 postgres:16
export DATABASE_URL="postgresql://postgres:pw@localhost:5433/signal"
.venv/bin/alembic upgrade head
```

---

## 4. Verifying a database is correct

Run these against the new database before you trust it.

```bash
export DATABASE_URL="postgresql://…"   # the new one

# a) Alembic is at the newest revision
.venv/bin/alembic current                 # → "0011 (head)"

# b) The schema matches the SQLModel models exactly.
#    This is the real check: it diffs live tables against app/models.py.
.venv/bin/alembic check                   # → "No new upgrade operations detected."

# c) The app boots and serves real data
uvicorn app.main:app --port 8000
curl -s localhost:8000/pricing | head     # the seeded packs
curl -s localhost:8000/healthz
```

`alembic check` failing means the migrations and the models have diverged —
some column exists in one and not the other. Fix it with a new migration; never
edit a migration that has already run in production.

### And on Postgres specifically

```bash
TEST_DATABASE_URL="postgresql://…/signaltest" .venv/bin/python -m pytest -q
```

The suite defaults to SQLite, which is faster but **does not enforce enum
labels** — Postgres does. That difference once let every audit in production
save a score with zero checks (see `CLAUDE.md`, migration `0007`). Running the
suite against a real Postgres also switches on the concurrency tests, which need
row-level locking SQLite can't do. Do this before shipping any schema,
migration or billing change. Point it at a *throwaway* database: the suite
creates and drops tables.

---

## 5. Writing a new migration

```bash
cd backend
DATABASE_URL="postgresql://…" .venv/bin/alembic revision -m "what it does"
```

Autogenerate (`--autogenerate`) is a starting point, not an answer — read what
it produced. Then, in the file:

- Give it the next sequential id (`0011`, `down_revision = "0010"`).
- Write a real `downgrade()`. SQLite can't drop columns directly, so use
  `op.batch_alter_table(...)` there.
- Explain in the docstring *why*, not just what — the existing migrations do.

Then test it, in this order, before committing:

```bash
.venv/bin/python -m pytest -q                       # SQLite
.venv/bin/alembic upgrade head                      # on a throwaway Postgres
.venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head
.venv/bin/alembic check
TEST_DATABASE_URL="postgresql://…" .venv/bin/python -m pytest -q
```

Test it against a Postgres that has **data** in it, not just an empty one. A
migration that backfills or rewrites rows behaves completely differently on an
empty table, and an empty table is exactly what a fresh test database gives you.

### Things that have bitten this schema before

- **Enum labels.** SQLAlchemy stores an `Enum` column by member *name*, not
  value. `CheckStatus.pass_ = "pass"` needs the Postgres type's label to be
  `pass_`. Migration `0001` got this wrong and `0007` fixed it; in between,
  every audit on Render silently saved zero checks. New status-like columns are
  therefore plain `String`, validated in the API schemas, not database enums.
- **Never write `user.credits_balance` directly.** Every change goes through
  `apply_credit_delta()` in `app/services/credits.py`: a conditional `UPDATE`
  plus a `credittransaction` row in one transaction. A plain `-= 1` reintroduces
  the race where 12 parallel requests spent a 3-credit balance, and leaves the
  ledger disagreeing with the balance.

---

## 6. Production deploy

Render runs migrations on every deploy — `render.yaml`'s start command is
`alembic upgrade head && uvicorn …`, so pushing a migration to `master` applies
it. Watch the deploy log for the `Running upgrade` lines; if a migration fails
the service won't start, which is deliberate — a half-migrated schema serving
traffic is worse than being down.

Back up before a deploy that changes the schema:

```bash
pg_dump --no-owner --no-acl --format=custom "$DATABASE_URL" -f before-0011.dump
```
