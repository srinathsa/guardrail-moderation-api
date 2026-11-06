# Guardrail Moderation API

A self-hostable, open-source content moderation API — an alternative to closed
commercial services (OpenAI Moderation, Azure Content Safety). It scores text
and images for harmful content, applies a **configurable Allow / Flag / Block
guardrail policy**, logs every decision to an audit trail, and closes the loop
with a **human review dashboard** so moderators can approve or reject any
automated decision.

## Key differentiator: human-in-the-loop review

Every moderation call is written to an audit log with `review_status =
pending`. Moderators use the review dashboard (or the `PATCH
/audit/logs/{id}/review` endpoint) to **approve** (overturn a flag/block) or
**reject** (confirm it) a decision, with a reviewer name, timestamp, and notes
recorded. This turns a one-shot filter into an auditable, correctable system.

## v4 addition: real user accounts + video posts

The feed now works like an actual social app instead of an anonymous demo:

- **Sign up** at `/signup` creates a real account (always `client` role — the
  same self-service signup any regular user would use). **Log in** at
  `/login`.
- **Posts and comments are always attributed to your logged-in account** —
  the author name is taken from your JWT, never from a text field, so no one
  can post as someone else. Posting/commenting requires being logged in;
  *browsing* the feed does not (same as viewing a public feed before
  signing in to a real platform).
- **Video posts** (`.mp4`/`.webm`/`.mov`, ≤50MB) are now supported alongside
  images. This project has no video-content-analysis pipeline, so — rather
  than silently trusting unscored video — **every video is automatically
  flagged for human review**, regardless of caption. You approve/reject it
  from the same `/review` dashboard as everything else.
- End-to-end example that's fully tested: **user1** signs up, posts a photo
  (auto-visible) and a video (auto-flagged, hidden); **user2** signs up and
  posts a toxic comment on user1's photo (auto-blocked, hidden, never shown
  under the post); **you** log in as admin at `/review`, see both pending
  items, approve the video → it goes live; the toxic comment stays rejected
  and hidden permanently once you reject it.

## v3 addition: live public social feed demo

- **`frontend/feed.html`** — an Instagram-style feed. Anyone (no login) can
  post a caption/image or leave a comment, exactly like a real social app.
- Every submission runs through the **full moderation pipeline** (toxicity
  model, image NSFW model, blocklist, PII detection) before it's stored.
- **`allow`** → visible immediately. **`flag`/`block`** → stored but hidden
  from the public feed, exactly the way a real platform would quietly hold
  back content pending review — the poster sees an inline status message
  ("posted!" / "flagged, pending review" / "blocked"), other users never see
  it at all.
- **You, the admin,** review anything hidden from the existing **Review
  dashboard** (`review.html`) — the same approve/reject flow as before. The
  moment you **approve**, that post or comment becomes publicly visible on
  next feed refresh (the feed auto-refreshes every 15s). Reject keeps it
  hidden permanently.
- New endpoints: `POST /feed/posts`, `POST /feed/posts/{id}/comments`,
  `GET /feed/posts`, `GET /feed/posts/{id}/status` — all public, no auth,
  matching how a real social platform's public-facing endpoints work. See
  [API reference](#api-reference) below.

## v2 additions

- **JWT login + role-based access control** — a proper dashboard login
  (`/auth/login`) issuing JWTs, with three roles: `admin` (manage users,
  blocklist, full access), `moderator` (review queue + analytics), `client`
  (no dashboard access). The `/moderate/*` endpoints still use the simple
  `x-api-key` scheme, since those are service-to-service calls, not human
  logins — see [Design notes](#design-notes).
- **PII detection** — text is checked for emails, phone numbers,
  credit-card-like numbers, and SSN-like numbers. Any hit auto-escalates an
  `allow` to `flag` (never straight to `block`) so a human decides.
- **Admin-managed blocklist** — admins add custom banned words/phrases via
  the dashboard or API; any match force-blocks the text regardless of model
  scores.
- **Analytics dashboard** — request volume, allow/flag/block trend over
  time, average score per toxicity category, review-status breakdown, and a
  **false-positive rate** (% of flagged/blocked content a human later
  approved) — a direct measure of how well the human-in-the-loop system is
  correcting the model.
- **Redesigned frontend** — five pages sharing one design system
  (`frontend/style.css` + `frontend/common.js`): `login.html`,
  `index.html` (public API-key demo), `review.html`, `analytics.html`
  (Chart.js), `admin.html` (user + blocklist management).

## Features

- **Text moderation**: auto language detection (`langdetect`) → routes English
  to a BERT-based toxicity model (Detoxify "unbiased") and French / Spanish /
  Italian / Portuguese / Turkish / Russian (or anything else) to a
  multilingual XLM-RoBERTa model (Detoxify "multilingual"). Scores:
  `toxicity, severe_toxicity, obscene, threat, insult, identity_attack`.
- **Image moderation**: NSFW vs. normal classification using a Hugging Face
  Vision Transformer (default `Falconsai/nsfw_image_detection`), loaded
  directly via `AutoImageProcessor` + `AutoModelForImageClassification`
  (not `pipeline()` — see [Design notes](#design-notes)).
- **Guardrail rules engine**: `THRESHOLD_FLAG` / `THRESHOLD_BLOCK` env vars
  (0.0–1.0). Any category ≥ block → `block`; else any category ≥ flag →
  `flag`; else → `allow`.
- **Audit logging**: every request logged (timestamp, content type, language,
  input preview, raw scores, decision, reasons, model used, processing time)
  to SQLite (default) or PostgreSQL via one `DATABASE_URL`.
- **Human review dashboard**: `review_status` (pending/approved/rejected) +
  `reviewed_by` / `reviewed_at` / `review_notes` fields, filterable listing,
  and a static web dashboard with Approve/Reject buttons.
- **Resilience**: if `detoxify` / `torch` / `transformers` aren't installed or
  model weights can't download (e.g. offline dev), the API automatically
  falls back to lightweight heuristic stubs and keeps working end-to-end.
  The response's `model_used` field always tells you which path ran
  (e.g. `detoxify-unbiased` vs. `heuristic-stub`).
- **API-key auth** via `x-api-key` header, structured so it's a one-file swap
  to JWT later (see `app/auth.py`).
- **CORS enabled**, Dockerfile + docker-compose (API + Postgres), static demo
  + review-dashboard pages, no frontend framework required.

## Project layout

```
app/
  config.py              # all env-var driven settings
  auth.py                 # x-api-key dependency (JWT-swappable)
  schemas.py               # Pydantic request/response models
  models/
    language_detect.py     # langdetect + heuristic fallback, en/multilingual routing
    text_moderation.py     # Detoxify (unbiased/multilingual) + heuristic fallback
    image_moderation.py    # HF ViT NSFW classifier + heuristic fallback
  guardrail/
    rules.py                # allow/flag/block decision logic
  db/
    database.py             # SQLAlchemy engine/session (SQLite/Postgres)
    models.py                # AuditLog ORM model
    crud.py                  # audit log create/list/update-review
  api/
    routes_text.py           # POST /moderate/text
    routes_image.py           # POST /moderate/image
    routes_admin.py            # GET/PATCH /audit/logs..., blocklist mgmt
    routes_auth.py              # login, JWT, user management
    routes_analytics.py          # GET /analytics/summary
    routes_feed.py                 # public social feed (posts/comments)
  main.py                       # FastAPI app, CORS, static mount, startup
frontend/
  style.css                      # shared design system (all pages)
  common.js                       # shared auth-guard / nav bar / API helper
  login.html                       # JWT login
  index.html                        # public text/image moderation demo (x-api-key)
  feed.html                          # public Instagram-style social feed demo
  review.html                         # human review dashboard (JWT: moderator/admin)
  analytics.html                       # charts + false-positive rate (JWT: moderator/admin)
  admin.html                            # user + blocklist management (JWT: admin only)
requirements.txt
Dockerfile
docker-compose.yml
.env.example
```

## Quickstart (local, no Docker)

```bash
python3 -m venv venv && source venv/bin/activate

# Minimal install (heuristic-stub mode only, fast, no ML deps):
pip install fastapi "uvicorn[standard]" pydantic python-multipart sqlalchemy \
            langdetect Pillow

# Full install (real ML models — large download, requires internet access
# to Hugging Face / PyPI the first time to fetch model weights):
pip install -r requirements.txt

cp .env.example .env   # edit API_KEY / thresholds as desired
export $(grep -v '^#' .env | xargs)   # or use a tool like direnv/dotenv

uvicorn app.main:app --reload --port 8000
```

Open:
- API docs (Swagger): http://localhost:8000/docs
- Public live feed: http://localhost:8000/
- Staff login: http://localhost:8000/login (after login: `/review`, `/analytics`, `/admin`)
- API testing demo: http://localhost:8000/demo

> **Note:** with only the minimal install, `TEXT_MODEL_MODE`/`IMAGE_MODEL_MODE`
> stay at `auto` and the app automatically falls back to the heuristic stub
> scorer — the whole pipeline (routing, guardrail thresholds, audit log,
> review flow) still works, just without real ML scoring. This was verified
> end-to-end in the environment this project was built in (no ML libs
> installed) — every endpoint, the allow/flag/block logic, and the
> approve/reject review flow all passed.

## Quickstart (Docker)

```bash
cp .env.example .env   # edit as desired
docker compose up --build
```

This starts the API (port 8000) wired to a Postgres container. For a
lightweight, ML-free build (heuristic stubs only, much faster to build):

```bash
docker compose build --build-arg SKIP_ML=1
docker compose up
```

## Configuration (environment variables)

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | `changeme-dev-key` | Shared secret required in `x-api-key` header |
| `AUTH_MODE` | `api_key` | `api_key` today; `jwt` reserved for future use |
| `THRESHOLD_FLAG` | `0.5` | Score ≥ this on any category → `flag` |
| `THRESHOLD_BLOCK` | `0.85` | Score ≥ this on any category → `block` (checked first) |
| `DATABASE_URL` | `sqlite:///./guardrail.db` | Any SQLAlchemy URL; use `postgresql+psycopg2://...` for Postgres |
| `CORS_ORIGINS` | `*` | Comma-separated list of allowed origins |
| `TEXT_MODEL_MODE` | `auto` | `auto` \| `ml` (force real model) \| `stub` (force heuristic) |
| `IMAGE_MODEL_MODE` | `auto` | Same options, for the image classifier |
| `HF_IMAGE_MODEL` | `Falconsai/nsfw_image_detection` | HF model id for image classification |
| `INPUT_PREVIEW_CHARS` | `200` | Max chars of text stored in the audit log preview |
| `SECRET_KEY` | `dev-secret-change-me-in-prod` | JWT signing secret — **set a real random value in production** |
| `JWT_EXPIRE_MINUTES` | `480` | Dashboard login session length |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `admin123` | Bootstrap admin account, auto-created on first startup if no users exist yet — **change immediately in production** |

## API reference

All endpoints (except `/health`) require header `x-api-key: <API_KEY>`.

### `POST /moderate/text`

Request:
```json
{ "text": "Some text to check" }
```

Response `200`:
```json
{
  "id": 42,
  "content_type": "text",
  "detected_language": "en",
  "decision": "flag",
  "reasons": ["insult=0.620 >= flag threshold 0.50"],
  "scores": {
    "toxicity": 0.61, "severe_toxicity": 0.02, "obscene": 0.05,
    "threat": 0.01, "insult": 0.62, "identity_attack": 0.03
  },
  "model_used": "detoxify-unbiased",
  "processing_time_ms": 84.2,
  "review_status": "pending"
}
```

### `POST /moderate/image`

`multipart/form-data` with a `file` field (JPEG/PNG/WEBP, ≤10MB).

Response `200`:
```json
{
  "id": 43,
  "content_type": "image",
  "detected_language": null,
  "decision": "allow",
  "reasons": ["all categories below flag threshold"],
  "scores": { "nsfw": 0.03, "normal": 0.97 },
  "model_used": "hf-vit-nsfw_image_detection",
  "processing_time_ms": 210.5,
  "review_status": "pending"
}
```
Note: only the `nsfw` score is evaluated against the guardrail thresholds —
`normal` is a safety signal, not a harm category.

Errors: `415` unsupported content type, `413` file too large, `400` empty file.

### `GET /audit/logs`

Query params (all optional): `review_status` (`pending`/`approved`/`rejected`),
`decision` (`allow`/`flag`/`block`), `content_type` (`text`/`image`),
`limit` (default 50, max 500), `offset`.

Response `200`:
```json
{ "total": 128, "items": [ { "...": "AuditLogOut objects" } ] }
```

### `PATCH /audit/logs/{id}/review`

Request:
```json
{
  "review_status": "approved",
  "reviewed_by": "moderator1",
  "review_notes": "False positive — sarcasm, not a threat."
}
```
`review_status` must be `approved` or `rejected`. Returns the updated
`AuditLogOut` object, or `404` if the id doesn't exist.

### `GET /health`
No auth required. Returns current thresholds and the active DB backend —
useful for container health checks.

### `POST /auth/login`
```json
{ "username": "admin", "password": "admin123" }
```
Returns `{ "access_token": "...", "token_type": "bearer", "username": "admin", "role": "admin" }`.
Use the token as `Authorization: Bearer <token>` on all `/audit/*`,
`/analytics/*`, and `/admin/*` endpoints (`/auth/me`, `/auth/users` too).

### `GET /auth/me`
Returns the current logged-in user's `username`/`role`.

### `GET /auth/users`, `POST /auth/users`, `DELETE /auth/users/{id}`
Admin-only. Create/list/remove dashboard accounts (`role`: `admin` |
`moderator` | `client`).

### `GET /admin/blocklist`, `POST /admin/blocklist`, `DELETE /admin/blocklist/{id}`
List is available to moderator/admin; add/remove is admin-only. Text
containing any blocklist term is force-blocked in `/moderate/text`,
regardless of model scores.

### `GET /analytics/summary`
Moderator/admin only. Returns totals, a day-by-day decision trend,
per-category average scores, review-status breakdown,
`false_positive_rate` (approved / (flag+block) — `null` if none reviewed
yet), and per-moderator review counts.

### `POST /auth/register` (public, no auth)
```json
{ "username": "user1", "password": "pass1234" }
```
Public self-signup for regular social-app users — always creates a `client`
role account (staff accounts are created separately by an admin via
`POST /auth/users`). Returns a `LoginResponse` (same shape as `/auth/login`)
so the new user is signed in immediately.

### `POST /feed/posts` (requires login — any role)
`multipart/form-data`, `Authorization: Bearer <token>`: `caption` (string,
optional), `media` (file, optional — JPEG/PNG/WEBP images ≤10MB, or
MP4/WEBM/MOV video ≤50MB). At least one of caption/media is required. The
author is always the logged-in username, never client-supplied. Runs the
full moderation pipeline and stores the post regardless of decision; video
is always at least `flag`'d (no automated video-content analysis — see
[Design notes](#design-notes)). Only `allow` (or later admin-approved) posts
show up in `GET /feed/posts`. Returns:
```json
{ "id": 12, "decision": "flag", "review_status": "pending", "visible": false,
  "reasons": ["text: insult=0.62 >= flag threshold 0.50"] }
```

### `POST /feed/posts/{post_id}/comments` (requires login — any role)
`multipart/form-data`, `Authorization: Bearer <token>`: `text`. Same
moderation + visibility rules as posts, author from the JWT. `404` if the
parent post doesn't exist.

### `GET /feed/posts?limit=30` (public, no auth)
Returns only currently-visible posts (and their currently-visible comments),
newest first. Browsing doesn't require login — only posting/commenting does.

### `GET /feed/posts/{post_id}/status` (public, no auth)
Lets the poster's browser check whether their own pending post has since
been approved — used by `feed.html`'s auto-refresh.

## Design notes

- **Video is always flagged, never scored.** This project doesn't include a
  video-content-analysis pipeline (frame extraction, per-frame NSFW scoring,
  audio transcription, etc.) — that's a substantially larger undertaking
  than image/text moderation. Rather than pretending to score it or silently
  auto-allowing it, every video post is deliberately routed to human review.
  This is a safe default, not a limitation to hide: it demonstrates the
  human-in-the-loop system handling a content type the automated layer
  can't (yet) judge on its own.
- **Feed browsing is public; posting is not.** `GET /feed/posts` needs no
  auth so anyone can view the feed (same as scrolling a public profile
  before signing in). `POST /feed/posts` and `POST /feed/posts/{id}/comments`
  require a valid JWT — the author is always derived from that token, never
  from client-supplied text, so people can't post as someone else.

- **Why not `transformers.pipeline()` for images?** The generic
  `pipeline()` factory eagerly imports a broad task-registry, including
  TensorFlow-backed pipeline code, which can crash at import time on
  environments with mismatched TF/protobuf versions — even when TF is never
  actually used. Loading `AutoImageProcessor` +
  `AutoModelForImageClassification` directly sidesteps that import graph.
- **Swapping to JWT auth later**: replace the body of
  `app.auth.verify_api_key` with a JWT decode + claims check. Route files
  never change since they only depend on `Depends(verify_api_key)`.
- **Resilience**: `text_moderation.py` / `image_moderation.py` each attempt
  the real ML import/load inside a `try/except`, and fall back to a
  deterministic heuristic scorer using the *same* category schema on any
  failure (missing package, no internet to fetch weights, corrupt cache,
  runtime error). This is exercised automatically — no flag needed — and can
  be forced either way with `TEXT_MODEL_MODE=ml|stub` /
  `IMAGE_MODEL_MODE=ml|stub`.
- **Guardrail evaluates only harm categories.** For images, `normal` is
  excluded from thresholding so a confidently-safe image can't accidentally
  trigger a block just because its "normal" score is high.
- **Two separate auth schemes, deliberately.** `x-api-key` on `/moderate/*`
  represents *your app's backend calling this service* — a shared secret is
  the right fit. JWT on `/audit/*`, `/analytics/*`, `/admin/*` represents *a
  human logging into the dashboard* — it carries an identity and a role so
  routes can enforce who's allowed to review content, see analytics, or
  manage users/blocklist. Don't merge them: a leaked API key shouldn't grant
  dashboard/user-management access, and vice versa.
- **PII escalates, never auto-blocks.** Emails/phone numbers/etc. are common
  in perfectly legitimate messages (support requests, contact forms), so
  detecting PII only bumps `allow → flag` for a human to look at — it never
  forces a `block` the way a blocklist hit does.

## Connecting to real social platforms

The self-contained `feed.html` demo simulates a social platform end to end,
entirely within this project. If you want to moderate content on an
**actual** external platform instead, two ready-to-run bridge scripts are
included in `integrations/` — each pulls real content and pipes it through
this project's own `/moderate/text` endpoint:

- **`integrations/reddit_moderator.py`** — checks posts/comments from any
  public subreddit (free API access via a "script" app at
  reddit.com/prefs/apps). Supports a one-time batch check or continuously
  streaming new comments in real time.
  ```bash
  pip install praw
  python integrations/reddit_moderator.py --subreddit test --limit 20
  python integrations/reddit_moderator.py --subreddit test --stream
  ```

- **`integrations/instagram_moderator.py`** — checks comments on posts
  belonging to **your own** Instagram Professional (Business/Creator)
  account via Meta's official Graph API, with an optional `--auto-hide` flag
  to automatically hide comments that get `block`ed. Note: Meta does not
  allow free/open access to arbitrary public Instagram content — only
  content on an account you control, authenticated via your own access
  token. Full setup steps (Meta developer app, permissions, finding your
  account ID) are in the script's docstring.
  ```bash
  python integrations/instagram_moderator.py --limit 5 --auto-hide
  ```

Both scripts read credentials from `.env` (see `.env.example`) and default
to calling `http://localhost:8000` with your `API_KEY` — start the main API
server first, then run either script in a second terminal.

## Testing it yourself

```bash
# health
curl http://localhost:8000/health

# text
curl -X POST http://localhost:8000/moderate/text \
  -H "Content-Type: application/json" -H "x-api-key: changeme-dev-key" \
  -d '{"text":"You are a wonderful person!"}'

# image
curl -X POST http://localhost:8000/moderate/image \
  -H "x-api-key: changeme-dev-key" -F "file=@photo.jpg;type=image/jpeg"

# audit logs
curl "http://localhost:8000/audit/logs?review_status=pending" \
  -H "x-api-key: changeme-dev-key"

# review
curl -X PATCH http://localhost:8000/audit/logs/1/review \
  -H "Content-Type: application/json" -H "x-api-key: changeme-dev-key" \
  -d '{"review_status":"approved","reviewed_by":"alice"}'
```

## Connecting to real social media content (Reddit)

`integrations/reddit_moderator.py` pulls real posts/comments from Reddit and
runs each one through this project's own `/moderate/text` endpoint — a
working example of how a real platform would plug in a moderation service.

Reddit's API is free for this kind of read-only use (Twitter/X removed free
read access in 2023 and now requires a paid developer tier, so Reddit is the
practical choice for a demo).

**Setup (~2 minutes):**
1. Go to https://www.reddit.com/prefs/apps → **create app** → type **script**
2. Note the client ID (under the app name) and client secret
3. Add to `.env`:
   ```
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_client_secret
   REDDIT_USER_AGENT=guardrail-bridge by u/your_reddit_username
   ```
4. `pip install praw requests` (already in `requirements.txt`)

**Run it** (with your Guardrail API already running):
```bash
# Check the 10 newest posts in r/test, one-time batch
python integrations/reddit_moderator.py --subreddit test --limit 10

# Also check each post's top-level comments
python integrations/reddit_moderator.py --subreddit test --limit 10 --include-comments

# Watch new comments live, in real time (Ctrl+C to stop)
python integrations/reddit_moderator.py --subreddit test --stream
```

Each item is printed with its decision (✅ allow / 🟡 flag / 🔴 block) and
reasons, and — because it calls your real `/moderate/text` endpoint — every
check also lands in your audit log and review dashboard exactly like any
other request.

## Connecting to Instagram

`integrations/instagram_moderator.py` fetches comments on **your own**
Instagram Professional (Business/Creator) account's posts via Meta's
official Graph API, moderates each one, and can automatically **hide**
comments that get blocked — directly on Instagram.

Unlike Reddit, Instagram does not offer free open access to arbitrary public
content. Meta only exposes comments on posts belonging to an Instagram
Professional account you control, via the Graph API with a valid access
token. This is a real, working integration, but it can only act on your own
account's content — not other people's posts.

**Setup (~10-15 minutes, one-time):**
1. Convert your Instagram account to **Professional** (Business or Creator):
   Instagram app → Settings → Account type and tools → Switch to
   professional account.
2. Connect it to a **Facebook Page** (Meta requires this — you'll be
   prompted during step 1, or do it via Meta Business Suite → Settings →
   Linked accounts).
3. Create a Meta developer app at https://developers.facebook.com/apps →
   **Create App** → type **Business** → add the **Instagram Graph API**
   product.
4. In the [Graph API Explorer](https://developers.facebook.com/tools/explorer),
   generate a User access token with permissions: `instagram_basic`,
   `instagram_manage_comments`, `pages_show_list`, `pages_read_engagement`.
   (A short-lived token from the Explorer — valid ~1 hour — is fine for
   testing; exchange it for a long-lived token per Meta's docs for
   anything longer-running.)
5. Find your Instagram Business Account ID: call `GET /me/accounts` in the
   Explorer to find your connected Page ID, then call
   `GET /{page-id}?fields=instagram_business_account` to get the ID.
6. Add to `.env`:
   ```
   META_ACCESS_TOKEN=your_token
   IG_BUSINESS_ACCOUNT_ID=your_ig_business_account_id
   ```

**Run it** (with your Guardrail API already running):
```bash
# Check comments on your 5 most recent posts
python integrations/instagram_moderator.py --limit 5

# Same, but automatically hide any comment that gets BLOCKED
python integrations/instagram_moderator.py --limit 5 --auto-hide
```

Like the Reddit integration, every checked caption/comment is logged to
your audit trail and shows up in the Review dashboard and Analytics page.

## License

MIT — do whatever you like, no warranty.
