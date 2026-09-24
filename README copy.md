# Debate Coach

Record a practice debate speech, get it back marked up: pace,
pauses and filler words counted from the audio, and the
argument read back to you.

## Architecture

```
Browser ──PUT──> Object storage
   │                   │
   └──POST /start──> API ──> pipeline thread
                              │
                              ├─ ffmpeg        normalize to 16k mono PCM
                              ├─ Whisper       word-level transcript
                              ├─ Silero VAD    speech/silence/pauses
                              ├─ raw_metrics   pace, fillers, stutters
                              ├─ speech_analysis  segment labels (LLM)
                              └─ coaching_engine  5 rule checks + 5 LLM checks
```

The dividing line runs through the whole codebase: anything
countable is counted in plain code and is reproducible;
anything requiring judgment goes to a language model and must
come back as structured JSON. `raw_metrics/` and
`delivery_metrics` never make a network call. `speech_analysis/`
and the LLM half of `coaching_engine/` never count anything.

### Packages

| Package | Role |
|---|---|
| `api/` | Round-robin key pool, scheduler, rate limiters, queues, Whisper client |
| `audio/` | Transcription and Silero VAD |
| `raw_metrics/` | Deterministic delivery metrics |
| `speech_analysis/` | LLM segment labelling |
| `coaching_engine/` | Rule checks, LLM checks, aggregation, scoring |
| `app/` | FastAPI: auth, sessions, storage, job pool |
| `web/` | Next.js client |

## Running locally

See `MIGRATION.md` for setup. Short version:

```bash
cp .env.example .env     # fill in DATABASE_URL, JWT_SECRET_KEY, STORAGE_*
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

cd web && cp .env.example .env.local && npm install && npm run dev
```

## API

All routes under `/v1`. Bearer token auth.

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/signup` | Create an account, returns tokens |
| POST | `/auth/login` | Returns tokens |
| POST | `/auth/refresh` | Exchange a refresh token |
| GET | `/users/me` | Current user |
| POST | `/sessions` | Reserve a session, returns a presigned upload URL |
| POST | `/sessions/{id}/start` | Begin analysis, returns 202 |
| GET | `/sessions` | List sessions |
| GET | `/sessions/{id}` | Status and progress |
| GET | `/sessions/{id}/report` | Full result |
| DELETE | `/sessions/{id}` | Delete session and its files |
| GET | `/status` | Key pool and queue depth |

`POST /sessions/{id}/start` is idempotent. Repeating it while a
run is in flight returns the current state rather than starting
a second run over the same audio.

## Scope

- One speaker per session. No opponent or turn separation.
- English only for the filler, stutter and argument checks.
- Analysis is post-hoc. Nothing listens live.

## Before launch

- [ ] Point a custom domain at the web app and the API
- [ ] Fill every `[PLACEHOLDER]` in `/privacy` and `/terms`
- [ ] Have a lawyer read both
- [ ] Switch `create_all` for Alembic migrations
- [ ] Set the bucket CORS rule to the production origin only
- [ ] Set `TRUST_FORWARDED_FOR=true` if behind a proxy
- [ ] Rotate `JWT_SECRET_KEY` off any value used in development
