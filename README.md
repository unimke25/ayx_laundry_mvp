# AYX Limited Laundry App — MVP Backend

FastAPI + SQLite implementation of the AYX subscription laundry service MVP.

## 1. Architecture

```
ayx_laundry/
├── requirements.txt
├── ayx_laundry.db          (created automatically on first run)
└── app/
    ├── main.py              FastAPI app, router wiring, table creation
    ├── database.py          SQLite engine/session (SQLAlchemy)
    ├── models.py             ORM models: User, Admin, Subscription, Order, StripeEventLog
    ├── schemas.py            Pydantic request/response contracts
    ├── auth.py               Password hashing + JWT issuance/verification
    ├── subscription_logic.py Centralized "is this user allowed to book?" logic
    └── routers/
        ├── users.py          Register, login, /me, list plans
        ├── subscriptions.py  Subscribe/upgrade, status, cancel
        ├── orders.py         Booking (active-subscriber gate), order history
        ├── admin.py          Admin login, order management, view user subs
        └── stripe_webhook.py Simulated Stripe event endpoint
```

Modular by domain (users / subscriptions / orders / admin / stripe) rather
than by technical layer, so each feature area can be extended or peeled off
into its own service later without restructuring the whole app.

## 2. Setup

Requires Python 3.10+ (uses `tuple[bool, str]` style type hints).

```bash
cd ayx_laundry
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set AYX_SECRET_KEY to a real random value, e.g.:
python3 -c "import secrets; print(secrets.token_hex(32))"

uvicorn app.main:app --reload
```

`.env` and `*.db` are excluded via `.gitignore` -- never commit either.

Visit **http://localhost:8000/docs** for interactive Swagger UI — the
fastest way to exercise every endpoint without writing curl commands.

## 3. Database schema decisions

- **Separate `users` / `admins` tables** rather than one table with a role
  flag — keeps staff auth isolated from customer auth.
- **`subscriptions` is its own table** (FK to user), not columns on `users`
  — a subscription has its own lifecycle (status, renewal date, Stripe
  IDs) independent of profile data, and this shape supports subscription
  history later without a migration.
- **`orders.subscription_status_at_booking` and `plan_at_booking`** are
  snapshots taken at booking time, kept separate from the live FK — so if
  a subscription later expires/cancels, the order record still accurately
  reflects what was true when the order was placed (audit trail).
- **`stripe_event_logs`** stores every simulated webhook event with a raw
  JSON payload, mirroring how a real Stripe integration logs events for
  idempotency/debugging.

## 4. Security notes (MVP-appropriate, not production-final)

- Passwords hashed with bcrypt (passlib), never stored or logged in plaintext.
- JWTs are scoped (`"scope": "user"` vs `"scope": "admin"`) so a customer
  token cannot be replayed against admin endpoints.
- `AYX_SECRET_KEY` environment variable **must** be set to a strong random
  value before any real deployment — the default in `auth.py` is a dev
  placeholder and is intentionally named to be obvious if left in place.
- `/admin/register` is open in this MVP for bootstrapping/demo purposes
  only. Before going live, lock it behind an invite flow, internal
  network, or replace it with a one-off seed script.
- No payment data of any kind touches this codebase — Stripe is fully
  simulated via `/stripe/simulate-event`.

## 5. Enforcing "only active subscribers can book" (hard constraint)

This is implemented **once**, in `subscription_logic.can_book()`, and the
booking endpoint (`POST /orders/`) is the only place that calls it. A
subscription counts as active only if its status is `ACTIVE` **and** its
`current_period_end` hasn't passed — this protects against a stale
`ACTIVE` status if an expiry event hasn't been simulated/received yet.

## 6. Example walkthrough (curl)

```bash
# 1. Register a user
curl -X POST localhost:8000/auth/register -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","password":"supersecret1","full_name":"Jane Doe"}'

# 2. Log in (OAuth2 form -- note "username" is the email field)
curl -X POST localhost:8000/auth/login \
  -d "username=jane@example.com&password=supersecret1"
# -> { "access_token": "...", "token_type": "bearer" }

# 3. Try to book WITHOUT a subscription (should 403)
curl -X POST localhost:8000/orders/ -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"pickup_address":"1 Main St","pickup_time":"2026-07-01T09:00:00"}'

# 4. Simulate Stripe checkout completing -> activates subscription
curl -X POST localhost:8000/stripe/simulate-event -H "Content-Type: application/json" \
  -d '{"event_type":"checkout.session.completed","user_id":"<USER_ID>","plan":"BASIC"}'

# 5. Book again (should now succeed)
curl -X POST localhost:8000/orders/ -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"pickup_address":"1 Main St","pickup_time":"2026-07-01T09:00:00"}'

# 6. Admin: register, log in, view all pending orders
curl -X POST localhost:8000/admin/register -H "Content-Type: application/json" \
  -d '{"email":"staff@ayx.com","password":"adminpass1","full_name":"AYX Staff"}'
curl -X POST localhost:8000/admin/login -d "username=staff@ayx.com&password=adminpass1"
curl localhost:8000/admin/orders?status_filter=PENDING -H "Authorization: Bearer <ADMIN_TOKEN>"
```

## 7. Known MVP limitations / explicit alternatives considered

- **Real Stripe integration**: swap `/stripe/simulate-event`'s manual
  trigger for a real webhook endpoint that verifies signatures with
  `stripe.Webhook.construct_event`; the event-dispatch logic inside stays
  the same.
- **SQLite → Postgres**: only `DATABASE_URL` in `database.py` needs to
  change, since all queries go through SQLAlchemy's ORM rather than raw SQL.
- **Migrations**: currently `Base.metadata.create_all()` at startup. Add
  Alembic once the schema needs versioned, reversible changes in production.
- **Rate limiting / abuse protection**: not implemented; add before
  exposing registration/login publicly at scale.

## 9. Deploying to Render

Render's build image otherwise defaults to the newest available Python
(currently 3.14), which doesn't yet have prebuilt wheels for some
dependencies (`pydantic-core`, `cryptography`) -- pip then tries to compile
them from source via Rust/maturin, which fails in Render's build sandbox
with a `Read-only file system` error. **Pin Python to 3.12** to avoid this
entirely (already done via `runtime.txt` and `render.yaml` in this repo).

**Option A — Blueprint (`render.yaml`, included):**
1. In Render, "New" → "Blueprint" → connect this repo. Render reads
   `render.yaml` automatically and sets build/start commands + Python
   version for you.
2. It auto-generates `AYX_SECRET_KEY` as a secret env var. No manual step
   needed there.

**Option B — Manual Web Service:**
1. "New" → "Web Service" → connect this repo.
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Environment → add `PYTHON_VERSION` = `3.12.7` and `AYX_SECRET_KEY` =
   (generate one locally with `python3 -c "import secrets; print(secrets.token_hex(32))"`).

**Note on SQLite + Render's free tier:** Render's filesystem is ephemeral
on the free plan -- `ayx_laundry.db` will be wiped on every redeploy/restart.
That's fine for a demo, but for anything persistent, attach a Render Disk
(paid) or migrate to a managed Postgres instance before relying on this
for real data.

## 10. Suggested next steps

1. Add automated tests (pytest + httpx `TestClient`) covering: booking
   blocked without subscription, booking allowed after simulated
   `checkout.session.completed`, pickup-limit enforcement for Basic/Premium,
   admin-only access to `/admin/*`.
2. Add Alembic migrations once the schema stabilizes.
3. Wire a real Stripe webhook endpoint behind a feature flag, in parallel
   with the simulated one, for staging tests.
4. Add the optional enhancements from the spec (push notifications,
   referral system, in-app chat, route optimization) as separate routers
   once the core flow is validated with real users.
