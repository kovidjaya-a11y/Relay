/* ═══════════════════════════════════════════════════════════
   Relay chat widget — frontend logic
   - Talks to the Claude-powered Netlify function at /api/chat
   - Falls back to a lead-capture form when a visitor wants to book
   ═══════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  const CHAT_ENDPOINT = "/api/chat";
  const LEAD_ENDPOINT = "/api/lead";
  const BOOK_TOKEN = "[[BOOK]]"; // control marker the model emits to trigger the booking form

  // ── elements ──────────────────────────────────────────────
  const root      = document.getElementById("relay-chat");
  const launcher  = document.getElementById("rc-launcher");
  const minBtn    = document.getElementById("rc-min");
  const messages  = document.getElementById("rc-messages");
  const quick     = document.getElementById("rc-quick");
  const form      = document.getElementById("rc-form");
  const input     = document.getElementById("rc-input");
  const sendBtn   = document.getElementById("rc-send");

  // ── state ─────────────────────────────────────────────────
  const history = []; // [{ role:'user'|'assistant', content:'…' }]
  let started = false;
  let busy = false;
  let leadShown = false;

  const GREETING =
    "Hey — I'm Relay's assistant 👋\nI can explain our automation packages, ballpark pricing, or help you book a free workflow audit. What are you working on?";

  const QUICK_REPLIES = [
    "What do you build?",
    "How much does it cost?",
    "Book a free audit",
  ];

  // ── helpers ───────────────────────────────────────────────
  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // minimal, safe formatting: **bold** and line breaks
  function format(text) {
    return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  function scrollDown() {
    messages.scrollTop = messages.scrollHeight;
  }

  function addMessage(text, who) {
    const el = document.createElement("div");
    el.className = "rc-msg " + who;
    el.innerHTML = who === "bot" ? format(text) : escapeHtml(text);
    messages.appendChild(el);
    scrollDown();
    return el;
  }

  function showTyping() {
    const el = document.createElement("div");
    el.className = "rc-typing";
    el.innerHTML = "<span></span><span></span><span></span>";
    messages.appendChild(el);
    scrollDown();
    return el;
  }

  function renderQuickReplies(list) {
    quick.innerHTML = "";
    list.forEach((label) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.addEventListener("click", () => {
        quick.innerHTML = "";
        sendUserMessage(label);
      });
      quick.appendChild(b);
    });
  }

  // ── open / close ──────────────────────────────────────────
  function openChat() {
    root.classList.add("open", "engaged");
    launcher.setAttribute("aria-expanded", "true");
    if (!started) {
      started = true;
      addMessage(GREETING, "bot");
      renderQuickReplies(QUICK_REPLIES);
    }
    setTimeout(() => input.focus(), 250);
  }
  function closeChat() {
    root.classList.remove("open");
    launcher.setAttribute("aria-expanded", "false");
  }
  function toggleChat() {
    root.classList.contains("open") ? closeChat() : openChat();
  }

  launcher.addEventListener("click", toggleChat);
  minBtn.addEventListener("click", closeChat);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && root.classList.contains("open")) closeChat();
  });

  // any element with [data-open-chat] opens the widget (e.g. the CTA button)
  document.querySelectorAll("[data-open-chat]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      openChat();
    });
  });

  // ── send a message to the AI ──────────────────────────────
  async function sendUserMessage(text) {
    text = (text || "").trim();
    if (!text || busy) return;

    addMessage(text, "user");
    history.push({ role: "user", content: text });
    input.value = "";
    quick.innerHTML = "";
    setBusy(true);

    const typing = showTyping();

    try {
      const res = await fetch(CHAT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history }),
      });

      typing.remove();

      if (!res.ok) throw new Error("bad status " + res.status);
      const data = await res.json();
      let reply = (data.reply || "").trim();

      // booking intent → show the lead form
      const wantsBooking = reply.includes(BOOK_TOKEN);
      reply = reply.replace(BOOK_TOKEN, "").trim();

      if (reply) {
        addMessage(reply, "bot");
        history.push({ role: "assistant", content: reply });
      }
      if (wantsBooking) showLeadForm();
    } catch (err) {
      typing.remove();
      addMessage(
        "Hmm, I couldn't reach the server just now. You can still book a free audit and we'll get right back to you.",
        "bot"
      );
      showLeadForm();
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  function setBusy(v) {
    busy = v;
    sendBtn.disabled = v;
    input.disabled = v;
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendUserMessage(input.value);
  });

  // ── lead-capture (booking) fallback ───────────────────────
  function showLeadForm() {
    if (leadShown) return;
    leadShown = true;

    const wrap = document.createElement("div");
    wrap.className = "rc-lead";
    wrap.innerHTML = `
      <div class="rc-lead-h">Book your free audit</div>
      <p class="rc-lead-p">Drop your details and we'll reach out within one business day to schedule your 30-minute workflow audit. No pitch, no obligation.</p>
      <input name="name" type="text" placeholder="Your name" autocomplete="name" />
      <input name="email" type="email" placeholder="Work email *" autocomplete="email" required />
      <input name="store" type="text" placeholder="Store / website (optional)" />
      <textarea name="note" placeholder="What's eating the most time right now? (optional)"></textarea>
      <div class="rc-err"></div>
      <button type="button">Request my audit →</button>
    `;
    messages.appendChild(wrap);
    scrollDown();

    const emailEl = wrap.querySelector('[name="email"]');
    const errEl   = wrap.querySelector(".rc-err");
    const btn     = wrap.querySelector("button");

    btn.addEventListener("click", async () => {
      const payload = {
        name:  wrap.querySelector('[name="name"]').value.trim(),
        email: emailEl.value.trim(),
        store: wrap.querySelector('[name="store"]').value.trim(),
        note:  wrap.querySelector('[name="note"]').value.trim(),
        transcript: history,
      };

      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(payload.email)) {
        errEl.textContent = "Please enter a valid email so we can reach you.";
        errEl.style.display = "block";
        emailEl.focus();
        return;
      }
      errEl.style.display = "none";
      btn.disabled = true;
      btn.textContent = "Sending…";

      try {
        const res = await fetch(LEAD_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error("lead failed");
        wrap.remove();
        addMessage(
          "You're all set ✅ We've got your details and we'll be in touch within one business day. Talk soon!",
          "bot"
        );
      } catch (err) {
        btn.disabled = false;
        btn.textContent = "Request my audit →";
        errEl.textContent = "Something went wrong sending that. Please try again, or email us directly.";
        errEl.style.display = "block";
      }
    });
  }
})();
