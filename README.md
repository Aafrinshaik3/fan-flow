# FanFlow AI

A GenAI-enabled stadium operations assistant built for **PromptWars — Challenge 4: Smart Stadiums & Tournament Operations**.

> **Note on the live deployment:** The GenAI chat and incident-triage features
> are fully implemented and tested (see the 39-test suite below, which
> includes mocked Anthropic API calls). If the live demo shows a fallback
> message instead of a live AI reply, it's because the Anthropic account
> currently has no API credit balance, not a code issue — the app is
> designed to fail safely in exactly this situation rather than crash.

FanFlow helps fans, volunteers, and venue staff during FIFA World Cup 2026 with:

| Challenge area | How FanFlow addresses it |
|---|---|
| **Navigation** | `/api/navigate` recommends the least-congested gate/zone in real time |
| **Crowd management** | `/api/crowd` streams a live occupancy snapshot per zone with normal/warning/critical staffing recommendations |
| **Accessibility** | The assistant answers step-free route and accessible-seating questions; the UI itself follows WCAG-minded patterns (see below) |
| **Multilingual assistance** | The GenAI assistant replies in whatever language the visitor writes in |
| **Operational intelligence** | The crowd engine classifies zones against occupancy thresholds and generates concrete staffing actions, not just raw numbers |
| **Workflow optimization (staff/organizers)** | `/api/incident` lets any steward describe a problem in plain language; GenAI classifies category + priority and returns a concrete first action, in seconds instead of a radio call and manual triage |
| **Sustainability** | `/api/sustainability` monitors recycling/waste stations and flags collection needs before overflow; UI shows live bin status per zone |
| **Transportation** | `/api/transport` recommends the lowest-carbon reasonable way home for a given distance, with an estimated CO2 saving vs. solo rideshare, so the tradeoff is concrete rather than abstract |
| **Real-time decision support** | Staff (crowd dashboard + incident triage) and fans (chat + gate finder + transport advisory) both get actionable, live guidance from the same platform |

## Architecture

```
fanflow-ai/
├── app.py                  Flask routes, validation, rate limiting, security headers
├── config.py                Environment-based configuration (no hard-coded secrets)
├── services/
│   ├── ai_assistant.py       Anthropic Claude wrapper -- multilingual Q&A
│   ├── crowd_monitor.py      Crowd telemetry simulation + recommendation engine
│   └── security.py           Input sanitization + in-memory rate limiter
├── templates/index.html      Semantic, accessible single-page UI
├── static/css/style.css      Design system (see tokens below)
├── static/js/app.js          Vanilla JS wiring the UI to the API (no build step)
└── tests/                    27 pytest unit + integration tests
```

**Why this shape:** `crowd_monitor.py` simulates the sensor/turnstile telemetry a
real venue would provide (CCTV people-counting, Wi-Fi/BLE density, turnstile
counts) behind a clean interface, so the actual operational-intelligence logic
— thresholding, staffing recommendations, "find me a quieter gate" — is fully
implemented and testable today, and can be pointed at real telemetry by
swapping one function.

## Security

- No secrets in source; `ANTHROPIC_API_KEY` and `FLASK_SECRET_KEY` are read from
  the environment only (see `.env.example`).
- All chat input is length-capped and control-character-stripped before use
  (`services/security.py`); Flask's `MAX_CONTENT_LENGTH` caps request bodies.
- Per-client sliding-window rate limiting on the chat endpoint.
- Security headers (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`) and an explicit CORS allow-list on every response.
- The assistant **fails closed**: any API error or missing key returns a
  generic, safe message and tells the visitor to ask a steward — it never
  leaks stack traces or exception internals to the client.
- Jinja auto-escaping (on by default) and `textContent`-only DOM writes in
  `app.js` prevent reflected-content injection.

## Accessibility

- Semantic landmarks (`header`, `main`, `section`), one `h1` per page, visible
  skip-to-content link.
- Live regions (`aria-live`, `role="status"`/`role="log"`) announce crowd
  updates and chat replies to screen reader users without a page reload.
- Visible focus rings on every interactive element; `prefers-reduced-motion`
  is respected.
- Color choices keep body text and interactive elements at 4.5:1+ contrast
  against the dark background.
- The assistant itself is an accessibility feature: it answers step-free
  route and accessible-seating questions in plain language on demand.

## Running it

```bash
cp .env.example .env        # then add your ANTHROPIC_API_KEY
pip install -r requirements.txt
python app.py                # http://localhost:5000
```

`.env` is loaded automatically via `python-dotenv` (see `config.py`) — no
manual `export` needed.

Without an API key, the app still runs: the crowd dashboard and gate finder
work fully on simulated data, and chat responds with a clear "ask a steward"
fallback instead of failing.

## Code quality tooling

- `ruff` (config in `pyproject.toml`) enforces linting rules (unused
  imports, import order, bug-prone patterns, simplifications) on every run.
- `.github/workflows/ci.yml` runs the full test suite and `ruff check`
  automatically on every push and pull request to `main`.
- Run locally:
  ```bash
  pip install ruff
  ruff check .
  pytest -v
  ```

## Testing

```bash
pytest -v
```

55 tests cover input validation edge cases, rate-limit behavior, crowd
threshold boundaries (74/75%, 91/92%), recycling-bin threshold boundaries
(69/70%, 89/90%), route status codes, malformed/adversarial AI-output
parsing for the incident triage feature, and the chat + incident +
sustainability endpoints with the Anthropic client mocked out (no network
or API key needed to run the suite). A GitHub Actions workflow
(`.github/workflows/ci.yml`) runs the full suite plus `ruff` linting on
every push.

## Possible next steps

- Replace the simulated telemetry in `crowd_monitor.py` with real turnstile/
  camera feed integration.
- Add push notifications (webhook or SMS) when a zone crosses "critical".
- Persist chat transcripts (opt-in, anonymized) to spot recurring pain points
  across a tournament.
