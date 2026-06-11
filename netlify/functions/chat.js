/* ═══════════════════════════════════════════════════════════
   Relay assistant — Netlify Function (Claude-powered)
   POST /api/chat  { messages: [{role, content}, ...] }  ->  { reply }
   Requires env var: ANTHROPIC_API_KEY
   Optional env var: RELAY_MODEL (defaults to claude-sonnet-4-6)
   ═══════════════════════════════════════════════════════════ */
const Anthropic = require("@anthropic-ai/sdk");

const MODEL = process.env.RELAY_MODEL || "claude-sonnet-4-6";
const MAX_TURNS = 20;     // cap conversation length we forward
const MAX_CHARS = 1000;   // cap per-message length

const SYSTEM_PROMPT = `You are the assistant for Relay, an AI automation agency that builds done-for-you automation systems for e-commerce brands. You live in a chat widget on relay's website. You are friendly, sharp, and concise — never pushy.

# What Relay does
Relay builds AI-powered automation systems that eliminate manual work, recover lost revenue, and connect the tools a brand already uses (Shopify, Klaviyo, CRMs, 3PLs, etc.). Common builds: abandoned cart recovery, CRM sync, invoice & payment reminders, inventory alerts, post-purchase sequences, supplier comms, reporting dashboards, lead follow-up flows. Builds use tools like Make.com and Klaviyo — no code needed on the client's end.

# Packages (give ranges, never invent exact quotes)
1. Starter Build — $800–1,200. One high-impact workflow built end-to-end, delivered within ~7 business days, Loom walkthrough + docs, 14-day support.
2. Full Automation Stack — $1,500–2,500 (most popular). 2–4 connected workflows: CRM sync + segmentation, email/SMS sequences, inventory alerts + supplier comms, automated reporting dashboard, 30-day support.
3. Monthly Retainer — $300–500/mo. Ongoing management, one new workflow added each month, monthly performance report, 24-hr priority support.

# Process
Every engagement starts with a FREE 30-minute workflow audit (no commitment — the client keeps the workflow map regardless). Then Relay builds it (5–10 business days, most builds), then hands over docs + a Loom + a support window. Most clients see results in the first week.

# How to behave
- Keep replies short: 2–4 sentences, conversational. Use plain language.
- You may use **bold** sparingly for emphasis. Do not use markdown headings, bullet lists with dashes, or links.
- Answer questions about services, pricing ranges, process, tools, and timelines using ONLY the facts above. If asked something you don't know (exact custom quotes, contractual terms, anything not above), say it's best covered in the free audit and offer to set one up. Never invent facts, metrics, client names, or guarantees.
- Always be steering gently toward the free audit as the natural next step.

# Booking
When the visitor expresses intent to book, get a quote, start, talk to a human, or share their contact details, append the exact token [[BOOK]] on its own at the very END of your reply. This triggers a short booking form in the UI. Write a brief friendly sentence before the token (e.g. confirm you'll grab their details). Only include [[BOOK]] when there is clear booking/contact intent — never in a normal informational reply.`;

exports.handler = async (event) => {
  const headers = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
  };

  if (event.httpMethod !== "POST") {
    return { statusCode: 405, headers, body: JSON.stringify({ error: "Method not allowed" }) };
  }

  if (!process.env.ANTHROPIC_API_KEY) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: "Server is missing ANTHROPIC_API_KEY." }),
    };
  }

  let incoming;
  try {
    incoming = JSON.parse(event.body || "{}");
  } catch {
    return { statusCode: 400, headers, body: JSON.stringify({ error: "Invalid JSON." }) };
  }

  // sanitise + clamp the conversation
  const messages = Array.isArray(incoming.messages) ? incoming.messages : [];
  const clean = messages
    .filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string")
    .slice(-MAX_TURNS)
    .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_CHARS) }));

  if (clean.length === 0 || clean[clean.length - 1].role !== "user") {
    return { statusCode: 400, headers, body: JSON.stringify({ error: "No user message." }) };
  }

  try {
    const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    const resp = await client.messages.create({
      model: MODEL,
      max_tokens: 400,
      system: SYSTEM_PROMPT,
      messages: clean,
    });

    const reply = resp.content
      .filter((b) => b.type === "text")
      .map((b) => b.text)
      .join("")
      .trim();

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ reply: reply || "Sorry, could you rephrase that?" }),
    };
  } catch (err) {
    console.error("chat function error:", err);
    return {
      statusCode: 502,
      headers,
      body: JSON.stringify({ error: "Assistant is unavailable right now." }),
    };
  }
};
