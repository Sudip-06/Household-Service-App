# Household Service App

A multi-role Flask web app for booking household services (plumbing,
cleaning, etc.). Three roles share one app: **Admin** (approves
professionals, manages services, views reports/charts), **Customer**
(browses services, books requests, rates completed work), and **Service
Professional** (accepts/rejects requests, uploads a CV at signup).

Full write-up of the original design: [`Report.pdf`](./Report.pdf).

## What was changed to make this deployable

The repo as uploaded had no dependency file and a few assumptions that only
hold on a normal always-on server with a writable local disk. Here's exactly
what changed and why:

| Change | Why |
|---|---|
| **Added `requirements.txt`** | Didn't exist at all — nothing could be installed or deployed without it. |
| **Added `vercel.json`** | Extends the function timeout to 60s for headroom on cold starts. Flask itself needs zero other config — Vercel auto-detects `main.py` as the entrypoint. |
| **SQLite path and CV upload folder now serverless-aware** | Vercel's filesystem is **read-only** outside `/tmp` (and `/tmp` is wiped on every cold start). The original code did `os.makedirs()` on a path under the deployed code directory *at import time* — on Vercel that throws immediately and the app never boots. It now detects the Vercel environment and uses `/tmp`, seeding it from the committed `data_base.sqlite3` and `static/cv/` on first request so existing data shows up right away. Local dev behavior is unchanged (still writes next to the code, still persists normally). |
| **`db.create_all()` now runs on import, not just under `if __name__ == "__main__"`** | That guard never executes when Vercel imports `main.py` as a WSGI module, so tables would never get created on a fresh `/tmp` database. Now idempotent and always runs. |
| **New `/uploads/cv/<filename>` route** | CVs were served via Flask's built-in `/static/...` route, which only serves files bundled at deploy time. A newly-uploaded CV saved to `/tmp/cv` was upload-successful but then unviewable (404) because the static route doesn't know about `/tmp`. The two "View CV" links in `manage_service_professionals.html` now point at this new route instead, which serves from wherever `UPLOAD_FOLDER` actually is. |

I verified all of this by actually running the app with `VERCEL=1` set
locally (simulating the read-only-filesystem environment) — home page,
login, a fresh customer signup, and a fresh professional signup with a CV
upload all round-tripped correctly against a `/tmp`-backed database before
I called it done.

**Left alone, on purpose:** `main.py`'s login route falls back to a
plaintext password comparison if the hash check fails
(`user_obj.password == form_password`), and the seeded `data_base.sqlite3`
does in fact contain plaintext demo passwords (see credentials below). I
didn't touch this, because changing it would break the existing seeded
accounts — but if this is ever used with real users' real passwords, that
fallback should come out and the DB should be rehashed.

## Deployment (Vercel)

1. Push this repo to GitHub.
2. [Vercel Dashboard](https://vercel.com/new) → **Add New → Project** →
   import the repo. Vercel detects `requirements.txt` and `main.py`
   automatically — no framework preset or build command needed.
3. Before the first deploy (or right after, then redeploy), go to
   **Settings → Environment Variables** and add:
   - `SECRET_KEY` — any long random string
     (`python -c "import secrets; print(secrets.token_hex(32))"`)
4. Deploy. Your app is live at `https://<project>.vercel.app/`.

### Persistence caveat (read this before using it for anything real)

This app stores data in a SQLite file and saves CVs to local disk — both
things a normal server keeps around indefinitely, but Vercel's serverless
functions don't. On Vercel, the database and any newly-uploaded CVs live in
`/tmp`, which:

- **Persists across requests within one warm instance** — so a normal test
  session (sign up, log in, book a service, log out) works exactly as
  expected.
- **Resets on a cold start** — after enough idle time, or on every new
  deployment, Vercel spins up a fresh instance and `/tmp` starts over from
  the committed `data_base.sqlite3` seed file. Anything written since (new
  signups, new bookings, new CVs) is gone.

That's fine for demoing or grading a single sitting. It is **not** fine for
a real multi-user deployment people rely on. If you need real persistence:

- **Database**: point `SQLALCHEMY_DATABASE_URI` at a hosted Postgres
  instance instead of SQLite — [Neon](https://neon.tech) and
  [Supabase](https://supabase.com) both have free tiers that work well with
  Flask-SQLAlchemy. Set it via the `DATABASE_URL` env var (already wired up
  in `main.py` — set the var and it's used automatically) and add
  `psycopg2-binary` to `requirements.txt`.
- **CV storage**: swap the local `cv_file.save(...)` call in the signup
  route for an object store — [Vercel Blob](https://vercel.com/docs/storage/vercel-blob)
  is the path of least resistance on Vercel; S3 or Cloudinary work too. The
  new `/uploads/cv/<filename>` route would then redirect to the object
  store's URL instead of calling `send_from_directory`.

Alternatively, if you'd rather keep the SQLite-on-disk approach entirely
un-modified, a platform with a real persistent volume (Render, Railway, a
plain VPS) avoids this problem altogether — the tradeoff is those aren't
Vercel.

## Local development

```bash
git clone <your-repo-url>
cd Household-Service-App-main
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # then set SECRET_KEY
python main.py
```

Runs at `http://localhost:5000`. Uses the committed `data_base.sqlite3`
directly — writes persist normally, nothing serverless-specific kicks in.

## Demo credentials

Seeded in `data_base.sqlite3` for testing each role:

| Role | Email | Password |
|---|---|---|
| Admin | `admin@test.com` | `a` |
| Customer | `c1@g.c` | `c` |
| Service Professional | `p1@p.c` | `p` |

These are intentionally trivial demo passwords for a seed dataset — not a
security recommendation. Don't reuse this pattern for real accounts.

## Environment variables

| Variable | Required | Purpose |
|---|:---:|---|
| `SECRET_KEY` | Recommended | Signs session cookies. Has a dev-only fallback so local runs work without it. |
| `DATABASE_URL` | Optional | Point at a hosted Postgres URL to replace the bundled SQLite file (see persistence caveat above). Unset = keeps using SQLite. |
| `VERCEL` | Automatic | Set by Vercel itself — this is how the app knows to use `/tmp` instead of the local disk. Don't set it manually except to test the serverless code path locally. |

## Tech stack

Flask · Flask-SQLAlchemy (SQLite by default) · Jinja2 templates · Bootstrap
· vanilla JS (Chart.js-driven `/chart-data/*` endpoints for the admin
dashboard graphs)

## Repo structure

```
main.py                  All routes: auth, admin/customer/professional dashboards,
                          booking flow, CV upload, chart-data JSON endpoints
model.py                 SQLAlchemy models: user, service, ServiceRequest,
                          RejectedRequest, RejectedDate, Report
templates/                Jinja2 templates, one+ per role/page
static/css, static/images CSS and image assets
static/cv                 Uploaded professional CVs (seed data locally;
                          serverless-aware at runtime, see above)
data_base.sqlite3         Seed database (admin, sample professionals, customers, services)
vercel.json                Function timeout config
requirements.txt           Python dependencies
.env.example                Documents SECRET_KEY / DATABASE_URL
Report.pdf                 Original project write-up
```
