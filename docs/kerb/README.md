# Kerb Automation: site and go-to-market docs

```
kerb/                         ← the website. Deploy THIS folder to Netlify.
  index.html                  Home page with the "What's your database worth?" calculator
  pitch.html                  Personalised one-page pitch (?agency=&name=&contacts=&commission=), prints to A4
  privacy.html, terms.html    DRAFTS, to be reviewed by a lawyer
  thanks.html, 404.html
  assets/site.css
  assets/calculator.js        Calculator: 0.8% book rate, 1 in 5 list, $400 per appraisal
  netlify.toml, robots.txt
docs/kerb/                    ← internal, NOT deployed
  campaign-engine-blueprint.md
  agency-outreach.md
```

## Deploy on Netlify

**Option A: drag and drop (2 minutes).** Go to app.netlify.com → Add new site →
Deploy manually, then drag the `kerb` folder in.

**Option B: from this Git repo (auto-deploys on push).** Add new site → Import
from Git → pick this repo. Set **Base directory** to `kerb` and leave the build
command empty. `kerb/netlify.toml` sets the publish directory. (The repo root
still holds the older Relay site, which setting the base directory ignores.)

Then:

1. **Forms:** Site configuration → Forms → *Enable form detection*, then
   redeploy. The pilot application form (`name="pilot"`) shows up under Forms.
   Add a form notification to email you at hello@kerbautomation.com. Each
   submission includes the visitor's calculator numbers.
2. **Domain:** Domain management → add `kerbautomation.com` and point the DNS
   at Netlify. HTTPS is automatic.

## Placeholders to fill before going live

Find them with `grep -rn "\[ADD ABN\]\|\[STATE\]" kerb/`

- `[ADD ABN]` in every footer, and in privacy.html and terms.html
- `[STATE]` in terms.html §8 (governing law)
- Remove the `DRAFT` HTML comment at the top of privacy.html and terms.html
  once the lawyer has reviewed them

## Decisions baked in (easy to change)

- **No-shows:** credited if the agency reports them within 48 hours. This keeps
  the "you only pay for real appointments" promise without relying on the
  agency's word forever. Change it in `index.html` (Pricing → No-shows) and
  `terms.html` §3.
- **Example conversation:** "Harbour & Co" is labelled *Illustrative example*.
  Replace it with a real (permissioned) conversation after the pilots.
- **Pilot pricing:** the site advertises $0 setup + $400 per booked appraisal.
  The 6-month plan also mentions "half-price pilots". Pick one before you pitch,
  and don't advertise both.
