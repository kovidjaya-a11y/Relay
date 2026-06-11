/* ═══════════════════════════════════════════════════════════
   Relay lead capture — Netlify Function
   POST /api/lead  { name, email, store, note, transcript }
   Captures the lead and notifies you via:
     1. Function logs (always)
     2. Email to LEAD_NOTIFY_EMAIL (default quickquoteiq@gmail.com) via Resend,
        when RESEND_API_KEY is set.
     3. A webhook (Slack / Zapier / Make), when LEAD_WEBHOOK_URL is set.
   Env vars:
     RESEND_API_KEY     required to send the notification email (https://resend.com)
     LEAD_NOTIFY_EMAIL  where leads are emailed   (default: quickquoteiq@gmail.com)
     LEAD_FROM_EMAIL    verified Resend "from"     (default: onboarding@resend.dev)
     LEAD_WEBHOOK_URL   optional Slack/Zapier/Make webhook
   ═══════════════════════════════════════════════════════════ */

const NOTIFY_EMAIL = process.env.LEAD_NOTIFY_EMAIL || "quickquoteiq@gmail.com";
const FROM_EMAIL = process.env.LEAD_FROM_EMAIL || "Relay Leads <onboarding@resend.dev>";

function esc(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function sendLeadEmail(lead) {
  if (!process.env.RESEND_API_KEY) return;

  const transcriptHtml = lead.transcript.length
    ? lead.transcript
        .map((m) => `<p style="margin:.2rem 0"><strong>${m.role === "user" ? "Visitor" : "Assistant"}:</strong> ${esc(m.content)}</p>`)
        .join("")
    : "<p><em>No chat transcript.</em></p>";

  const html = `
    <h2>New Relay audit request</h2>
    <p><strong>Name:</strong> ${esc(lead.name || "—")}</p>
    <p><strong>Email:</strong> ${esc(lead.email)}</p>
    <p><strong>Store / site:</strong> ${esc(lead.store || "—")}</p>
    <p><strong>Note:</strong> ${esc(lead.note || "—")}</p>
    <p><strong>Submitted:</strong> ${esc(lead.submittedAt)}</p>
    <hr><h3>Chat transcript</h3>${transcriptHtml}`;

  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: FROM_EMAIL,
      to: [NOTIFY_EMAIL],
      reply_to: lead.email,
      subject: `New audit request — ${lead.name || lead.email}`,
      html,
    }),
  });

  if (!res.ok) {
    throw new Error(`Resend ${res.status}: ${await res.text()}`);
  }
}

exports.handler = async (event) => {
  const headers = { "Content-Type": "application/json", "Cache-Control": "no-store" };

  if (event.httpMethod !== "POST") {
    return { statusCode: 405, headers, body: JSON.stringify({ error: "Method not allowed" }) };
  }

  let body;
  try {
    body = JSON.parse(event.body || "{}");
  } catch {
    return { statusCode: 400, headers, body: JSON.stringify({ error: "Invalid JSON." }) };
  }

  const email = String(body.email || "").trim();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return { statusCode: 400, headers, body: JSON.stringify({ error: "Valid email required." }) };
  }

  const lead = {
    name:  String(body.name || "").trim().slice(0, 120),
    email: email.slice(0, 160),
    store: String(body.store || "").trim().slice(0, 200),
    note:  String(body.note || "").trim().slice(0, 1000),
    transcript: Array.isArray(body.transcript)
      ? body.transcript
          .filter((m) => m && typeof m.content === "string")
          .slice(-20)
          .map((m) => ({ role: m.role, content: String(m.content).slice(0, 1000) }))
      : [],
    submittedAt: new Date().toISOString(),
    source: "website-chat",
  };

  // Always log — visible in the Netlify function logs as a baseline capture.
  console.log("NEW RELAY LEAD:", JSON.stringify(lead));

  // Email the lead (default: quickquoteiq@gmail.com) via Resend, if configured.
  try {
    await sendLeadEmail(lead);
  } catch (err) {
    // Don't fail the visitor's submission if email delivery hiccups — it's logged.
    console.error("lead email error:", err);
  }

  // Optionally forward to a webhook (Slack, Zapier, Make, email service, etc.)
  const webhook = process.env.LEAD_WEBHOOK_URL;
  if (webhook) {
    try {
      await fetch(webhook, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `New Relay audit request from ${lead.name || "(no name)"} <${lead.email}>` +
                (lead.store ? ` · ${lead.store}` : "") +
                (lead.note ? `\nNote: ${lead.note}` : ""),
          lead,
        }),
      });
    } catch (err) {
      // Don't fail the visitor's submission if the webhook is down — we still logged it.
      console.error("lead webhook error:", err);
    }
  }

  return { statusCode: 200, headers, body: JSON.stringify({ ok: true }) };
};
