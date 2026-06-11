# Relay — site + AI assistant

Static marketing site for Relay (AI automation for e-commerce brands) plus a
Claude-powered chat assistant that answers questions and captures audit bookings.

```
index.html              Marketing page
assets/chat.css         Chat widget styles
assets/chat.js          Chat widget frontend
netlify/functions/
  chat.js               Claude-powered assistant   (POST /api/chat)
  lead.js               Booking / lead capture      (POST /api/lead)
netlify.toml            Hosting + /api redirects
```

## How the bot works

1. Visitor opens the chat bubble (bottom-right) or clicks "Book your free audit".
2. Messages go to `/api/chat`, which calls Claude server-side with a Relay system
   prompt (services, pricing, process). Your API key never reaches the browser.
3. When the visitor wants to book, the model emits a `[[BOOK]]` marker and the
   widget shows a short lead form that posts to `/api/lead`.

## Deploy (Netlify)

1. Push this folder to a Git repo and connect it in Netlify (or `netlify deploy --prod`).
2. In **Site settings → Environment variables**, add:
   - `ANTHROPIC_API_KEY` — **required**, from https://console.anthropic.com/
   - `RESEND_API_KEY` — *to email leads*, from https://resend.com. Leads are emailed
     to `quickquoteiq@gmail.com` by default (override with `LEAD_NOTIFY_EMAIL`).
   - `LEAD_FROM_EMAIL` — *optional*, the verified "from" address (default
     `onboarding@resend.dev`; use your own domain once verified in Resend).
   - `LEAD_WEBHOOK_URL` — *optional*, also push leads to a Slack/Zapier/Make webhook.
   - `RELAY_MODEL` — *optional*, defaults to `claude-sonnet-4-6`.

   Lead delivery is layered: leads are always written to the function logs, emailed
   when `RESEND_API_KEY` is set, and webhooked when `LEAD_WEBHOOK_URL` is set.
3. Build settings: publish dir `.`, functions dir `netlify/functions` (already in
   `netlify.toml`). Netlify installs `@anthropic-ai/sdk` from `package.json`.

## Run locally

```bash
npm install
cp .env.example .env   # add your ANTHROPIC_API_KEY
npx netlify dev        # serves the site + functions at http://localhost:8888
```

The static page renders without any keys; only the assistant needs `ANTHROPIC_API_KEY`.
