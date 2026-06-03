# Initiative: SEO/AEO launch toolkit (candidate skills)

**Status:** researched 2026-06-03, not built. Spun out of the glp3.wiki rebrand
relaunch (a YMYL medical wiki whose #1 channel is AI-assistant citations, ~7×
its Google organic traffic). Three reusable, free, CI-able checks that any
content site relaunch wants. Could ship as one `seo-launch` skill with
subcommands, or three small skills.

---

## 1. `structured-data-validate` — JSON-LD / schema audit

**Why:** redesigns silently break Article/MedicalWebPage/FAQ/Breadcrumb markup;
schema must also match visible page text or it's "valid but not performing."

**What it should do**
- Fetch rendered HTML (handles JS — Next App Router emits JSON-LD server-side),
  extract every `<script type="application/ld+json">`, parse, report per `@type`.
- Check required-in-practice fields by type and flag gaps:
  - **Article**: no fields are *required* by Google, but treat `headline`,
    `image`, `author`, `publisher(.logo)`, `datePublished`, `dateModified` as
    mandatory trust signals. Dates must be ISO-8601 **with timezone**.
  - **MedicalWebPage** (YMYL): `reviewedBy`, `lastReviewed`, `about` →
    `Drug`/`MedicalCondition`, `medicalAudience`. Not a rich-result type, but an
    AI/understanding signal.
  - **BreadcrumbList**: still a live rich result — `position` + `item` per entry.
- **Authors rule (Google Search Central "Authors", ~Feb 2026):** `Person` for
  people, **`Organization` for editorial teams (officially sanctioned)**.
  `author.name` = name only (no "Dr.", no titles, no publisher); one entry per
  author; markup must match the visible byline; recommend `url`/`sameAs` to a
  real author/editorial page. **Never invent a named medical reviewer for YMYL**
  — fabricated credentials are the single biggest Trust-pillar risk; org-author
  + cited primary sources is the honest, compliant pattern.
- **FAQPage:** rich results **fully removed May 7 2026** (was gov/health-only
  since 2023). Keep FAQ *content* (great for AI citation); the `FAQPage` wrapper
  is now zero-SERP overhead — flag as optional, not an error. Don't build tooling
  around it.

**How to validate (free, no manual Rich Results UI):**
- There is **no public Rich Results Test API**; `validator.schema.org` has an
  undocumented `POST /validate` but is rate-limited/blocked — don't depend on it.
- Recommended gate: **`schema-dts`** (Google's TS types) to type-check JSON-LD at
  build (`tsc` fails on malformed schema; glp3.wiki already uses this) + the
  **Schemar GitHub Action** (open-source schema.org validator, no rate limit) on
  the built preview. Lighthouse's structured-data audit is a coarse extra.

Sources: developers.google.com/search/docs/appearance/structured-data/article ·
schema.org/docs/meddocs.html · searchenginejournal.com (FAQ removal, May 2026) ·
github.com/google/schema-dts · johnnyreilly.com/schemar-github-action

## 2. `free-cwv` — Core Web Vitals / LCP without paid tools

**Why:** Vercel Speed Insights is paid; you can gate LCP on a preview URL for
free with the same Lighthouse engine.

- **PageSpeed Insights API** — free, **25k req/day**, *same Lighthouse engine as
  pagespeed.web.dev*, overlays CrUX field data. Add a free GCP API key for CI.
  ```sh
  curl -s "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=<PREVIEW>&strategy=mobile&category=performance&key=$PSI_KEY" \
    | jq '.lighthouseResult.audits["largest-contentful-paint"].displayValue,
          .lighthouseResult.categories.performance.score'
  ```
- **Lighthouse CI** (`npx @lhci/cli autorun --collect.url=<PREVIEW>`) — better PR
  gate: set assert budgets on LCP/CLS/TBT, get history.
- **unlighthouse** — crawls the whole preview site (good periodic full-site sweep).
- **CrUX API** — real-user field data, free, but needs traffic (low-traffic pages
  return no data); use on top pages as a reality check.
- Note: always measure **mobile** on a **production build / Vercel preview**, not
  `next dev` (dev is unoptimised and not representative). PSI scores swing ±10-15
  vs local Lighthouse — use for trend/gate, not absolute truth.

Sources: developers.google.com/speed/docs/insights/v5/get-started ·
unlighthouse.dev · github.com/GoogleChrome/lighthouse-ci

## 3. `og-rescrape` — refresh social/OG caches after a redesign

- **Facebook/Open Graph** (feeds many embeds): `POST
  https://graph.facebook.com/?id=<URL>&scrape=true` (needs an app access token).
  If `og:image` won't update, bump the image URL.
- **LinkedIn**: Post Inspector (linkedin.com/post-inspector) force-refreshes on
  inspect; manual only, no API; ~7-day cache otherwise.
- **X/Twitter**: Card Validator shut down 2022, no API; ~7-day cache self-heals;
  only workaround is a cache-busting query param.
- **Slack/Discord/iMessage**: per-message unfurl cache, short TTL, self-heals —
  not worth tooling.
- **Realistic minimum:** script one FB `?id=&scrape=true` POST per key URL; the
  single most robust cross-platform trick is **versioning the `og:image`
  filename** on redesign (sidesteps every cache at once). Everything else self-heals.

Sources: gist FrostyX/81d58222d1e835e24013 · linkedin.com/help/linkedin/answer/a6233775 ·
devcommunity.x.com (card validator gone)

---

## Myths to kill (carry into the skill copy)
- "FAQPage gives rich results" — dead since May 2026.
- "Need a named MD to rank YMYL" — false; Organization author is sanctioned; inventing one is the risk.
- "Twitter Card Validator refreshes cache" — gone since 2022.
- "validator.schema.org has a CI API" — no; use schema-dts + Schemar.
- "Need Vercel Speed Insights for CWV" — no; PSI API + Lighthouse CI are free, same engine.
