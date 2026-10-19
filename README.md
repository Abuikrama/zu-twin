# Zeeshan Usmani · Digital Twin (MVP)

A chat page that answers in Zeeshan Usmani's voice. The small Python backend holds the
Anthropic API key, so anyone you share the link with can chat without needing a key of their own.

```
server.py          backend (Python 3.9+, no packages to install)
public/index.html  chat page
knowledge.md       what the twin knows: edit this to improve it
.env               your key and settings (create from .env.example; never share or commit)
render.yaml        one-click hosting on Render
```

## 1. Run it on your Mac

```bash
cd ~/zeeshan-twin && cp .env.example .env && open -e .env
```

Paste your key after `ANTHROPIC_API_KEY=` and save. Optionally set an `ACCESS_CODE`.

```bash
cd ~/zeeshan-twin && python3 server.py
```

Open http://localhost:8000

## 2. Share it with Sir Zeeshan

`localhost` only works on your own computer, so the app has to be hosted somewhere public.
Easiest free option is **Render**:

1. Put this folder in a GitHub repo (the `.gitignore` keeps `.env` out of it).
2. On render.com: **New → Blueprint**, then pick the repo. It reads `render.yaml`.
3. When asked, enter `ANTHROPIC_API_KEY` (your key) and an `ACCESS_CODE`.
4. Send Sir Zeeshan the `https://zeeshan-twin-….onrender.com` link along with the access code.

The free plan sleeps when idle, so the first message after a break can take about 30 seconds.

## Protecting your key and bill
- The key stays on the server and is never sent to the browser.
- Set an **ACCESS_CODE** before sharing, so random visitors can't spend your credits.
- Each visitor is limited to 20 messages per 10 minutes (`RATE_LIMIT` in `server.py`).
- Set a monthly spend limit at console.anthropic.com → Billing.

## Making it sound more like him
Add transcripts, posts and his own answers to `knowledge.md`. The server re-reads it on every
message, so you don't need to restart. Have Zeeshan review the facts in it.
