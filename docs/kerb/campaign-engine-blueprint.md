# Kerb campaign engine: blueprint

Database reactivation for real estate agencies. SMS and email go out to old
appraisals, past vendors and past buyers. AI handles the text replies and books
appraisals into the agent's diary. The fee is $400 per booked appraisal.

This covers the build order, the stack, message sequences, reply-handling logic,
the booking flow, the billing ledger and the dashboard.

---

## 0. The numbers the engine has to prove

| Book rate (of raw contacts) | Appraisals from 3,000 | Revenue per campaign | Campaigns needed for $236k |
|---|---|---|---|
| 0.5% | 15 | $6,000 | 40 |
| **0.8% (site assumption)** | **24** | **$9,600** | **25** |
| 1.0% | 30 | $12,000 | 20 |
| 1.3% | 40 | $16,000 | 15 |

- The 6-month plan (2 + 4 + 4 × 6.5 ≈ 32 campaigns plus reruns) clears $236k at
  0.8% even with the pilots discounted. **At 0.5% it doesn't** (32 × $6k = $192k).
  So the pilots need to measure one number above all: **booked appraisals ÷ raw
  contacts**.
- Expect only 60–75% of a raw CRM export to have a valid, unique mobile number.
  So 0.8% of raw contacts means roughly 1.1–1.3% of *sendable* contacts. Track
  both, and quote agencies on raw, because that's the number they know.
- The fee works out to $2,000 per listing (5 appraisals × $400), which is
  **10–13% of one listing's commission**. Lead every pitch with this.
- SMS cost (pass-through): about 2,100 sendable mobiles × 3 SMS, plus replies,
  is about 7,000 segments. At a typical 5–8c per segment that's about
  **$350–$560 per campaign**. Check current rates with your provider, and keep
  every outbound SMS to **one segment (≤160 GSM characters)** or the cost doubles.

---

## 1. Build order (don't automate before the pilots prove the rates)

**Pilot mode (month 1, about 1 week of build): semi-manual.**
A 3,000-contact campaign at 10% response is about 300 replies over 10 days,
roughly 30 a day. You can handle that yourself with AI-drafted replies. Only
automate what saves real time:

1. CSV cleaner script (normalise, dedupe, segment, suppress).
2. Bulk SMS from an SMS platform with a dedicated AU number and inbound webhooks.
3. Inbound replies go to a Claude classifier and draft reply. The draft is posted
   to a Slack channel or a simple review page, and you approve or edit it, then
   send it with one click.
4. Booking by hand in the agent's calendar (or a Cal.com link per agent).
5. A Google Sheet as the ledger and dashboard.

**Automated mode (month 2+, after about 50 approved conversations):**
auto-send the low-risk reply categories (see §4). Anything sensitive, or any
confidence below 0.8, still goes to a human. Add calendar API booking and a
per-agency dashboard. Hire the VA to work the review queue instead of you.

### Stack

| Job | Pilot choice | Why |
|---|---|---|
| SMS (two-way, AU number) | ClickSend or Cellcast (both Australian); Twilio as fallback | Dedicated AU mobile number, inbound webhooks, AU billing. A dedicated number (not an alphanumeric sender ID) is needed anyway so people can reply, which also sidesteps ACMA's SMS Sender ID Register for alphanumeric IDs. |
| Email | Resend or Postmark, from `mail.<agency-domain>` (agency adds DKIM/SPF), or from `<agency>.kerbautomation.com` | Sending in the agency's name from your domain looks spoofed. A subdomain protects both reputations. |
| Reply AI | Claude API (`claude-sonnet-5` for classification and drafts) | Already used in this repo's Netlify functions. |
| Backend | Netlify Functions + Supabase (Postgres) | Matches the existing Relay setup, and the free tiers cover pilots. |
| Review queue | Slack incoming webhook + interactive buttons, or a single Netlify page | Fastest human-in-the-loop. |
| Calendar | Google Calendar / Microsoft Graph API, or Cal.com per agent | Most agencies run Google Workspace or O365 alongside the CRM diary. |
| Dashboard | Google Sheet in pilots, then a Netlify page reading Supabase | |

**Alternative if you'd rather buy than build:** GoHighLevel (numbers,
workflows, calendars, conversation AI in one place, about US$97–297/mo). It
gets you live faster, but you'd be reselling a generic tool, which weakens the
"we built the engine" story and the margin. Build is the better choice given
your skills. GHL is the backup if the build slips past week 2.

### Data model (Supabase)

```
agencies      id, name, abn, timezone, sms_number, email_from, status
agents        id, agency_id, name, mobile, calendar_id, booking_rules(json)
campaigns     id, agency_id, name, segment, starts_at, status, sms_cost_quote
contacts      id, agency_id, first_name, last_name, mobile_e164, email,
              property_address, suburb, segment(appraisal|vendor|buyer),
              relationship_date, source_row(json), suppressed(bool), suppressed_reason
sends         id, campaign_id, contact_id, step, channel, body, provider_id, sent_at, status
messages      id, contact_id, direction(in|out), channel, body, at, provider_id
conversations id, contact_id, campaign_id, state, category, confidence, owner(ai|human), updated_at
bookings      id, conversation_id, agent_id, starts_at, address, owner_name,
              confirmed_text_message_id, calendar_event_id,
              status(booked|attended|no_show|cancelled|credited), billable(bool)
invoices      id, agency_id, week_start, lines(json), sms_cost, total, sent_at, paid_at
suppressions  agency_id, mobile_e164, email, reason, at   -- global per agency, survives reruns
```

---

## 2. Intake: CRM CSV to sendable list

1. **Map columns**, because every CRM names them differently (Rex, VaultRE,
   AgentBox, Box+Dice). Keep a mapping preset per CRM.
2. **Normalise mobiles** to E.164 (`04xx xxx xxx` → `+614xxxxxxxx`). Drop
   landlines from SMS but keep them for email.
3. **Deduplicate** on mobile, then email. Merge segments (a past buyer who also
   had an appraisal is one contact, tagged with their most recent relationship).
4. **Suppress** CRM "do not contact" flags, prior opt-outs, the Kerb suppression
   list for that agency, agency staff and suppliers, anyone the agency names,
   and **deceased-estate or sensitive flags** where the CRM has them.
5. **Recency cap:** exclude relationships older than about 7 years unless the
   lawyer says otherwise (see §7). Older contacts respond less and weaken the
   inferred-consent argument.
6. **Segment:**
   - `appraisal`: appraised, never listed with the agency.
   - `vendor`: sold with the agency 2+ years ago.
   - `buyer`: bought through the agency 3–10 years ago.
7. **Output a pre-flight report** for the agency: raw count, valid mobiles, valid
   emails, suppressed, final sendable per segment, and the SMS cost quote. This
   report is also a sales tool (see the outreach playbook).

---

## 3. Message sequences

Rules for every message:

- **Identify the sender:** agent's first name plus agency name in every SMS and
  email.
- **Opt-out on every message:** "Reply STOP to opt out" on SMS, and an
  unsubscribe link plus postal/contact details in email.
- **≤160 GSM characters** per SMS, with straight quotes and no emoji (emoji
  switch the message to UCS-2, where the limit is 70). The sender should compute
  length per contact and fall back from `{suburb}` to "your area" when a long
  suburb pushes the message over 160.
- **No price claims or figures.** Never "prices are up 20%" or "worth $1.2m".
  That avoids misleading-conduct risk under the ACL and state underquoting
  rules, and the agent gives the figure at the appraisal anyway.
- **Send window:** Mon–Fri 9:00–19:30 and Sat 10:00–16:00 in the agency's
  timezone. Never Sunday or public holidays. Stagger sends (e.g. 200 per 15
  minutes) so replies don't all arrive at once.
- The client approves every template before launch (keep the approval email).

Merge fields: `{first} {agent} {agency} {street} {suburb} {year}`

Character counts use a realistic worst case: first=Michelle, agent=Sarah,
agency=Harbour & Co, street=14 Wattle St, suburb=Bondi Junction.

### Segment A: old appraisals (strongest segment)

| Day | Channel | Message | Chars |
|---|---|---|---|
| 0 | SMS | Hi {first}, {agent} from {agency}. We appraised {street} in {year} and {suburb} has moved a lot since. Free updated figure? Reply STOP to opt out | 156 |
| 2 | Email | Subject: *{street}: what's changed since {year}*. 3 short paragraphs: we appraised it in {year}; a lot has changed locally (recent sales on nearby streets, taken from the agency's own sold list); 20-minute no-obligation update, reply with a time or pick one from the booking link. Signed by the agent, with unsubscribe. | – |
| 5 | SMS | Hi {first}, {agent} again ({agency}). Happy to pop by {street} for 20 mins this week or next, no obligation. Want a time? Reply STOP to opt out | 150 |
| 9 | SMS | Last one from me {first}. If you ever want a fresh figure on {street}, reply YES and I'll lock in a time. {agent}, {agency}. STOP to opt out | 147 |

### Segment B: past vendors

The address they sold is no longer theirs. Ask about the current home.

| Day | Channel | Message | Chars |
|---|---|---|---|
| 0 | SMS | Hi {first}, {agent} from {agency}. We sold {street} for you in {year}, hope the new place is going well. Curious what it's worth now? Reply STOP to opt out | 160 |
| 2 | Email | Subject: *Checking in, {first}*. Thanks for trusting us with {street}; if the current place is up for a rethink, free appraisal; reply or book. | – |
| 5 | SMS | Hi {first}, {agent} again ({agency}). Happy to do a free 20 min appraisal on your current place, no obligation. Want a time? Reply STOP to opt out | 149 |
| 9 | SMS | Segment A day-9 message, with "{street}" replaced by "your place" | ≤147 |

### Segment C: past buyers

| Day | Channel | Message | Chars |
|---|---|---|---|
| 0 | SMS | Hi {first}, {agent} from {agency}. You bought {street} through us in {year}. Curious what it's worth today? Free, no obligation. Reply STOP to opt out | 155 |
| 2 | Email | Subject: *{street}, {year} → today*. What's sold nearby; free update; reply or book. | – |
| 5 | SMS | Hi {first}, {agent} again ({agency}). Outgrown {street}, or just curious? I can do a free 20 min appraisal. Want a time? Reply STOP to opt out | 149 |
| 9 | SMS | Same as the Segment A day-9 message | 147 |

**Stop the sequence for a contact** as soon as they reply (any category),
opt out, bounce or book. Replies move to the conversation flow in §4.

**Quarterly rerun:** new wording (never repeat the same opener), exclude
anyone who booked, opted out or said "not interested" in the last 6 months,
and only include people who didn't reply at all or said "not now, try in X
months" where X has passed.

---

## 4. Reply handling

### 4.1 Pipeline

```
inbound SMS/email webhook
  → store message, find contact + active conversation
  → HARD RULES (regex, before any AI):
       STOP | UNSUBSCRIBE | REMOVE | "stop texting" | "don't contact" | "take me off"
       → suppress immediately, send one confirmation:
         "You're unsubscribed from {agency} messages. {agent}"
       → conversation.state = opted_out, notify agency (for CRM update)
  → Claude classify + draft (JSON output)
  → routing:
       auto_send allowed AND confidence ≥ 0.8 AND category in AUTO_SAFE → send (after pilot phase)
       otherwise → review queue (Slack/page), SLA 15 min in send hours
  → update conversation state, stop the outbound sequence
```

Late-evening replies (after 20:00) are queued for the morning unless the owner
is mid-booking.

### 4.2 Categories and what to do with each

| Category | Example | Action | Auto-send after pilots? |
|---|---|---|---|
| `BOOK_INTENT` | "yes", "sure", "what times?" | Offer 2 specific slots (§5) | Yes |
| `QUALIFY_NEEDED` | "maybe, what's involved?" | Explain (20 mins, free, no obligation, agent gives a figure and recent sales), then offer 2 slots | Yes |
| `PRICE_QUESTION` | "just text me a number" | Explain that an accurate figure needs a quick look, the agent can do 15 minutes, and offer 2 slots. **Never give a figure.** | Yes |
| `FUTURE_TIMING` | "not till next year" | Thank them, ask whether a check-in closer to then is OK, and store `follow_up_at` | Yes |
| `NOT_INTERESTED` | "no thanks" | One polite close, suppress for 6+ months | Yes |
| `SOLD_OR_MOVED` | "sold that years ago" | Ask whether they own elsewhere now, then either offer slots or close | Yes |
| `WRONG_PERSON` | "wrong number" | Apologise, suppress that mobile | Yes |
| `OPT_OUT_SOFT` | "please stop", "leave me alone" | Treat as STOP. Suppress. (The regex should catch most of these; the classifier is the backstop.) | Yes (suppress) |
| `SENSITIVE` | death, divorce, illness, financial hardship, complaint, anger, "who gave you my number" | **Human only.** Draft a brief, kind reply; suppress where appropriate; tell the agency | Never |
| `OTHER` | anything else, or low confidence | Human | Never |

### 4.3 Classifier prompt (starting point)

System prompt, per agency, cached:

```
You handle SMS replies for {agency}, a real estate agency in {suburb_region}.
Messages went to people who previously dealt with the agency, offering a free,
no-obligation updated appraisal with {agent}.

Goal: if the person is open to it, book a 20-minute appraisal. Otherwise close
politely. Never be pushy. Send at most one follow-up question at a time.

Rules:
- Never state a price, value, range, percentage or market statistic.
- Never claim to be a person. If asked, say you're {agent}'s assistant at {agency}.
- Keep replies under 300 characters and write in plain Australian English.
- Offer only the slots given in AVAILABLE_SLOTS.
- If they mention death, illness, separation, money trouble, a complaint,
  anger, or ask how we got their number, category = SENSITIVE.

Return JSON only:
{"category": "...", "confidence": 0-1, "reply": "...",
 "extracted": {"owner_name": null, "property_address": null,
               "timing": null, "chosen_slot": null, "follow_up_at": null},
 "notes_for_agent": "..."}
```

User turn: the conversation so far, plus `AVAILABLE_SLOTS` (the next 2–4 open
slots from the agent's calendar) and the contact's CRM facts (segment, address,
year).

Validate the JSON. If it doesn't parse, or it contains a `$` or digits followed
by `k`/`%`/`m`, send it to the human queue.

### 4.4 Quality loop

- Every human edit to a draft is stored as (draft, final). Review these weekly
  and update the prompt and examples.
- Metrics: median first-reply time, % of drafts sent unedited, opt-out rate
  per 100 sends, complaint count (target zero).

---

## 5. Booking flow

```
BOOK_INTENT
 → offer 2 concrete slots: "Sarah can do Thu 4:30pm or Sat 10am. Which suits?"
     (next 5 business days, the agent's rules: appraisal hours, travel buffer, max per day)
 → owner picks → confirm the details in one message:
     "Great. Sat 10am at 14 Wattle St with Sarah. Is that the right address,
      and is it just you or will anyone else be there?"
 → owner confirms   ← this written confirmation is the billable event
 → create calendar event on the agent's calendar
     title:  "Appraisal: {owner} – {address} (Kerb)"
     notes:  segment, relationship year, conversation summary, timing, motivation, mobile
 → send confirmation SMS: "Done. Sarah will see you Sat 10am at 14 Wattle St.
     We'll text a reminder the day before. {agency}"
 → notify agent (SMS or email) with the notes
 → booking.status = booked, billable = true
 → T-24h reminder SMS, with a reschedule option ("reply R to change the time")
 → T+2h after the appointment: ask the agent "Did it go ahead? Y / N / Rescheduled"
     N  → status no_show → credit on next invoice (agency has 48h to report)
     no answer in 48h → stays billable
```

**Reschedules** keep the same booking row (not billed twice). **Cancellations
more than 24h ahead** that aren't rebooked become `cancelled` and are not billed.
Put this in the pilot agreement. It's fairer than the no-show rule and stops
disputes.

---

## 6. Billing ledger and dashboard

**Weekly invoice (every Monday):** one line per booking (date, owner, address,
agent), minus credits, plus SMS pass-through with the provider's cost report
attached. 7-day terms. Direct debit if you can arrange it (Stripe/GoCardless
AU BECS). That removes chasing, which matters at 6–7 campaigns a month.

**Agency dashboard, one page per campaign:**

- Sent / delivered / replied / booked / attended / opted-out, per segment
- Booked appraisals list with agent, time, address and notes
- "Not now" list with follow-up dates. **This is the rerun pipeline, so show
  it prominently.**
- Commission estimate: booked × 20% × average commission (their number)

**Your internal view:** book rate per raw and per sendable contact, by segment,
CRM and agency size. After 5 campaigns this is your pricing and forecasting
data, and your case-study material.

---

## 7. Compliance checklist (for the lawyer review)

Questions to put to the lawyer, with the proposed answer:

1. **Consent.** Do the segments have *inferred consent* under the Spam Act
   through an existing business relationship? Proposed: yes for appraisals,
   vendors and buyers within about 7 years, and never for purchased or scraped
   lists.
2. **Sender identification.** Is "{agent} from {agency}" plus a reply-able
   number enough identification and contact information for the authorising
   party? Is an ABN or website needed in the email footer? (Include both in
   email anyway.)
3. **Unsubscribe.** STOP handled instantly (the law gives 5 business days).
   Does a reply-STOP mechanism on a standard-rate number satisfy the
   "functional unsubscribe" requirement?
4. **Roles.** The agency is the authorising sender and Kerb is the service
   provider. Put this in the terms, with a warranty from the agency that its
   data qualifies (already drafted in `kerb/terms.html` §2).
5. **Privacy.** Kerb holds agency contact data as a contractor. The privacy
   policy covers overseas processing (the AI and SMS providers).
6. **Underquoting and ACL.** No price statements in automated messages.
   Confirm the "{suburb} has moved a lot since" wording is acceptable.
7. **AI disclosure.** The assistant never claims to be a person and says so if
   asked. Should replies be signed "{agent}'s assistant"?

Also get: professional indemnity plus cyber insurance before pilot 1 goes live.

---

## 8. Pilot success criteria (decide before launch)

| Metric | Kill / rethink | OK | Great |
|---|---|---|---|
| Reply rate (sendable) | < 4% | 8% | 15% |
| Booked ÷ raw contacts | < 0.4% | 0.8% | 1.2%+ |
| Opt-out rate per campaign | > 8% | 3–5% | < 3% |
| Complaints | any formal | 0 | 0 |
| Agent says appraisal was "real" | < 60% | 80% | 90%+ |
| Your hours per campaign | > 25 | 10–15 | < 8 |

If booked ÷ raw comes in under 0.5%, the per-appraisal fee alone won't reach
$236k. Options then: raise the fee for vendor/appraisal segments, add a small
setup fee after the founding pilots, or move into the second industry sooner.
