---
name: kole-design-tips
description: House UI/UX design playbook distilled from Kole Jain's design tutorials. Use whenever designing or reviewing an app/website interface — dashboards, mobile screens, landing pages, settings, modals, empty states, charts, micro-interactions, or pricing pages. Covers typography, color, spacing, dark mode, components, motion, mobile patterns, dashboard structure, presentation, and the "vibe-coded" smell test. Triggers on "design this screen", "review this UI", "make this look professional", "fix this dashboard", "improve this layout", "color palette", "dark mode", "spacing", "rounded corners", "font size", "Figma", "mobile screen", "bottom sheet", "empty state", "micro-interaction", "looks AI-generated", "make this less generic", or "vibe coded".
---

# Kole Design Tips

How we design interfaces across all our apps. Distilled from a deep series of UI/UX tutorials. The voice is opinionated and specific — exact pixel values, hex modifiers, Figma settings — because vague rules don't ship better interfaces.

Default home is **app surfaces**: every screen, component, and interaction in our products should run through this guide. Marketing pages share most of the same rules with one big exception (see §13 Playful web).

If the design looks like every other AI-generated app, it's wrong. Pick fewer colors, more intentionally; use real icons, not emojis; design around user intent, not a card grid.

---

## 1. The four standards

Every screen should be:

- **Intent-led** — Start from what the user is trying to do. Build the smallest UI that gets them there, then expand only as their intent expands.
- **Hierarchical** — Size, color, position, and weight should make the most important thing impossible to miss and the least important thing easy to skip.
- **Restrained** — Fewer colors, fewer fonts, fewer lines, fewer plans, fewer KPIs. Adding is easy. The discipline is removing.
- **Specific** — Vague "professional" is the enemy. Pick the icon library, pick the spacing scale, pick the font, pick the four colors. Then stay consistent.

---

## 2. Start with user intent, not pixels

Design is storytelling, not art. Tell the story of the user's action, not your own aesthetic.

- Open every new screen by writing one sentence: *"The user comes here to ___."* If you can't, the screen shouldn't exist yet.
- Start with the **primary input or action** (the search bar, the create button, the destination URL), then layer features only as intent gets more specific.
- Honor 30+ years of web conventions: top→bottom and left→right flow, nav at the top, primary CTA prominent. Familiarity is a feature.
- **Progressive disclosure**: load more buttons over infinite scroll (users still need the footer); collapsible "Advanced options" sections; bottom sheets and pop-overs instead of stuffing every option into the first view.
- Animations and visual flourishes are debt unless they add clarity, feedback, or function. If the page works the same without it, cut it.

---

## 3. Typography

One sans-serif. One. Pick one of:

`DM Sans` · `Axiforma` · `SF Pro` · `Geist` · `Plus Jakarta Sans` · `Montserrat` · `Unbounded`

### Scale

**Landing pages / marketing** — wide range, big hero:

| Level | Size |
|---|---|
| H1 | 64px |
| H2 | 42px |
| H3 | 32px |
| H4 | 20px |
| H5 | 16px |
| H6 | 14px |

**Dashboards / app surfaces** — tight range, info-dense:

| Level | Size |
|---|---|
| H1 | 24px (often 20px) |
| H2 | 20px (often 16px) |
| H3 | 18px |
| H4 | 16px |
| H5 | 14px |
| H6 | 12px |

### Refinements
- **Letter-spacing for large text (>70px):** tighten to `-2%` to `-4%`. Default kerning falls apart at hero sizes.
- **Line-height for large headers:** `110–120%` of font size. Default 1.5 looks loose on a 64px H1.
- **Dashboard body:** keep gaps between text elements minimal — info density is the point.

---

## 4. Color & contrast

### Less, more intentionally
Not every element is a different color. If you have five accent colors on a file list, you have four too many. Pick the palette, then assign meaning to each.

### The 60-30-10 split
- **60%** dominant neutral (background, surfaces)
- **30%** secondary (cards, sections)
- **10%** accent (primary CTA, active state, focus)

When a screen feels noisy, count colors. You're almost always violating this ratio.

### Building a palette (HSB)

Use HSB — it makes hue/depth math obvious.

**Monochromatic ramp** (one color, multiple depths):
- Darker shade: **+20 saturation, −10 brightness**
- Lighter shade: **−20 saturation, +10 brightness**

**With a hue shift** (more harmonious):
- Darker: shift hue **+20 toward blue/purple** (blues read darker), then apply the sat/brightness move
- Lighter: shift hue **−20 toward yellow/red**, then the sat/brightness move

**Generators worth using**: `coolors.co`, Tailwind's full palette.

**Tailwind shortcut**:
- Light mode → background `50`, accent `500`
- Dark mode → background `950`, accent `300`

### Never pure black or pure white
- Light backgrounds → very light tint of accent color. Examples: `#FBF8F6` (light orange tint), `#F5F5FF` (light purple tint).
- Dark backgrounds → very dark tint of accent. Examples: `#040533` (dark blue), `#171720` (dark purple).
- Pure `#000000` and `#FFFFFF` make the UI feel sterile and break brand integration.

### Semantic colors (don't override these)
- **Blue** — focus / trust / "in progress"
- **Green** — success / new / positive confirmation
- **Yellow** — warning
- **Red** — danger / destructive / error
- **Even if red isn't a brand color, use it for destructive actions** (Delete buttons, irreversible confirms). Brand-color delete buttons confuse users and undermine the action's gravity.

### Contrast (non-negotiable)
- Check every text/background pair against **WCAG AA**.
- If your brand accent fails on white (e.g., orange at 2.34:1), darken it until it passes (e.g., 4.05:1). The brand survives a darker shade; an unreadable button doesn't.
- **Don't max out contrast everywhere**: pure-black-on-pure-white for every label flattens hierarchy. Reserve max contrast for the most important text; use dark grey (or a tinted dark) for secondary labels, file sizes, dates, metadata.
- Borders: use light grey (or low-opacity tinted) — never high-contrast.

### Color use is information, not decoration
- Neutral icons by default (grey/black). Color the icon **only** when it carries status — active tab, unread badge, selected item.
- Don't color every file card a different color "for variety." It's noise.

---

## 5. Spacing, grids & rounded corners

### Base unit: 4px or 8px

Every spacing decision (gap, padding, margin) is a multiple of 4 or 8. Scaling for responsive is then trivial (1×, 0.5×, 0.25×).

- **Tight groups** (within a card, label-to-value) → 4px / 8px
- **Related elements** (card-internal sections) → 16px
- **Section breaks** → 32px
- **Larger elements** (>32px sizes): when strict 8-multiples look awkward, round to nearest 5 or 10, or jump exponentially (e.g., 200 / 264 / 360 / 488).

**Figma setting**: `Preferences > Nudge amount > Big nudge: 8` (default is 10). One-time change, lifetime of consistent spacing.

### Don't worship the 12-column grid
- 12-column grids matter for **repeating, structured content** (galleries, blog grids, dashboards) and for **defining responsive breakpoints** (8-col tablet, 4-col mobile).
- Custom landing pages don't need to obey it. Whitespace and rhythm matter more than column alignment.

### Rounded corners (nested elements)

When you put a rounded element inside another rounded element, **same radius makes them look optically wrong**. The rule:

```
Inner radius = Outer radius − distance between (padding)
```

Example: outer card radius 30px, padding 10px → inner element radius 20px.

**Exception**: pill shapes don't need it — equal distance from edge.

**Figma corner smoothing**: in the properties panel, set iOS corner smoothing to **100%** for subtler, softer corners (used heavily by Apple).

---

## 6. Light mode & dark mode

Dark mode is **not** light mode inverted. Build a separate palette.

### Light mode
- Neutral background (very light tinted, not pure white)
- White or near-white cards on the background
- **Subtle shadows** for elevation (low opacity, high blur). If the shadow is the first thing you notice, it's too strong.
- Cards: gentle shadow. Pop-overs/modals: stronger shadow.
- Borders: light grey for separation.

### Dark mode
- Dark tinted background (not `#000`)
- **Depth via brightness, not shadow** — shadows barely show on dark. Make elevated surfaces *lighter* than the base, not darker.
  - Stack rule: each elevation layer = **+4 to +7 brightness, −10 to −20 saturation** (in HSB) from the layer below.
  - Example base `H:230 S:39 B:13` → elevated card `H:230 S:48 B:17`.
- **Borders**: low contrast, low opacity — bright borders on dark surfaces create visual noise.
- **Most text**: light tinted grey, not pure white. Reserve `#FFF` for the single most important label per screen (logo, primary metric).
- **Logos**: slightly desaturate for dark mode so they don't glow.
- **Colors**: dim saturation and brightness across the palette so nothing glows. This frees you up to use rich darks (deep purples, reds, greens) instead of defaulting to navy.

---

## 7. Cards, lists, tables & layout

### Cards
- Group related info inside one card; that's the whole job.
- **Generous internal padding**. Cramped cards look cheap.
- **Don't double-nest cards.** A card inside a card creates padding-on-padding and burns space. Use whitespace to group instead.
- **Separation**: in light mode use background colors; in dark mode use borders. Pick one per design.

### Card content
- **Remove redundant labels.** If a number is obviously a price, drop the "Cost:" label. If "$437/night" is shown, no one needs the word "Price".
- **Group like with like** (name + location together, cost + rating together).
- **Rank by importance** — biggest type for the title, smaller for metadata.
- **Use icons** for context instead of more words (bed icon for bedrooms, pin for location, star for rating).
- **Strategic alignment**: title left, cost right. This creates a clear scan line.

### Lists & tables
- **Lose the lines.** Most table dividers are clutter. Replace with:
  - Generous row spacing, or
  - Subtle alternating row backgrounds (very low contrast).
- Tables become tools when you add: **search, filter, sort**, plus checkboxes for bulk actions.
- For bulk: checkboxes select → contextual **"Bulk actions"** button appears.

### Choosing modal vs pop-over vs new page
- **Pop-over** — simple, non-blocking choice (display settings, sort dropdown).
- **Modal** — form with multiple fields that needs focus but should keep context (Create link, Invite member).
- **New page** — large or permanent content (full link details, settings, profile). Add breadcrumbs/back nav.

### Forms inside modals (not flyouts)
Flyouts are sparse and waste space. A modal gives you room for collapsible "Advanced options" without cramming everything visible. Default the basics expanded, hide the advanced.

### Lose redundant KPIs
If the same total-clicks + click-rate header appears on the Dashboard, Links, Custom Domains, and Teams pages, three of those are wrong. KPIs belong on the page they describe.

---

## 8. Buttons, icons, inputs & states

### Icons
- **Sized to match line-height** of the adjacent text. 16px text → 16px icon. 24px text → 24px icon.
- **Use a real icon library**: Hugeicons. Never emojis in app UI.
- Icons stay **neutral by default** (grey/black). Color them only when they carry status.

### Buttons
- **Padding ratio: horizontal = 2× vertical.** (e.g., `py-4 px-8` / `16px vertical, 32px horizontal`.)
- **Ghost buttons** (transparent, no background until hover) for secondary actions — sidebar links, low-emphasis controls.
- **Verb-first** label. See `mailchimp-copy-style` for copy rules.

### Required button states (minimum four, often five)
| State | Treatment |
|---|---|
| Default | Base color |
| Hover | Slightly lighter / brighter |
| Pressed (active) | Slightly darker |
| Disabled | Desaturated; or light grey bg + white text |
| Loading | Spinner inside, locked-out |

On mobile (no hover): make the **press** state visually distinct — slightly darker, brief tactile feel.

### Inputs
Required states:
- **Default**
- **Focus** — visible ring/border (often the brand accent)
- **Error** — red border + red helper text *below* explaining the fix
- **Warning** — yellow border + helper text for non-blocking issues
- **Disabled** — desaturated, no cursor

### Tooltips
- Use them on icon-only buttons.
- **Delay before they show: ~1000ms** of hover. Instant tooltips clutter every interaction.

---

## 9. Feedback & states (the whole feedback model)

Every interaction needs a visible response.

### Toasts (non-blocking notifications)
| Type | Color | When |
|---|---|---|
| Success | Green | "Link created", "Recipe saved" |
| Warning | Yellow | "Link isn't redirecting" |
| Error | Red | "Link creation failed" |
| Info / Update | Blue | "A new update is available" |

Position: bottom-right by default. Brief copy (no "Successfully…").

### Optimistic UI
Show the change *before* the server confirms. Delete an email → it disappears immediately. The user shouldn't see a spinner for actions that almost always succeed. Reconcile if it fails.

### Empty states
- **First-time empty**: full-screen guidance, draw attention to the primary action (e.g., highlight the `+` button), pop-over explaining how to start.
- **No results**: imagery + "Nothing found" + suggestion ("Did you mean…?") + an action (clear filters, start over).
- Never just "No data." Empty states are onboarding moments.

### Loading
- Spinners on buttons during submit, skeleton blocks for incoming content. Don't leave the user wondering if anything is happening.

---

## 10. Dashboards (specific rules)

The sidebar is the **spine** of the product. Treat it accordingly.

### Sidebar
- **Top**: profile / company (avatar + name, click → account menu).
- **Body**: nav items as `icon + short label`. Recognizable icons matter; if you can't think of one, the label is wrong.
- Group related links; nest less-frequent ones under expandable parents (e.g., a `Customers ▾` group).
- **Notifications and "New" chips** belong here — small numeric badge or a "New" pill on a nav item.
- **Bottom**: rare-use links (Settings, Help Center, Logout). Account card at the very bottom expands a pop-over with Billing & Usage / Settings / Sign Out.
- Make the sidebar **collapsible** for power users.

### Main area
- **One job per dashboard**: link management → links front and center; project tracker → projects front and center. Don't try to show everything.
- **Strict grid** (e.g., 2-col × 2-row) for the cards on a dashboard view. Density matters; alignment matters more.
- **Tight typography**: H1 at 20–24px, not 64px. Smaller gaps. Information density is the goal.

### Charts
- Keep them boring: **simple line graphs** and **bar charts**. Don't invent chart types.
- **Always include** gridlines and axis numbers. Every dashboard ships without them and every dashboard is worse for it.
- Date range selector: `1d / 1w / 1m / 6m / 1y`.
- **Hover behavior**: bubble showing exact value + % change; dim other bars when hovering one.
- For bar charts of items (links, products, users) — show **favicons** beside each label for instant recognition.
- For analytics aggregate views: include a toggle for **Aggregate vs Individual** so users can compare specific items.
- **Donut charts** for split-by-category (devices, sources, browsers).
- **World maps** with shaded regions for geographic data, paired with a country table including flags.

### KPI cards
- Numbers alone are sparse. Pair with a **micro-chart** (small inline sparkline) showing the trend.
- Don't duplicate the same KPIs across every page.

### Settings pages
- **Tabs** to organize: e.g., `Usage` / `Billing` / `Account`.
- Usage tab: simple two-column layout with **small donut charts** ("Links 2/25", "Domains 0/0").
- Remove the placeholder "Current Plan" card if it doesn't do anything. Non-functional UI is worse than no UI.

### Pricing pages
- **3–4 plans, not 5.** Decision paralysis is real.
- Name them honestly: `Free / Standard / Team / Enterprise` (rename "Business" → "Enterprise" for the top tier).
- **Show discounts clearly**: `$10/mo` struck through next to `$2/mo (Early Adopter)`.
- For each plan, show **what's included now** with checkmarks and **what's missing from the next tier** with subdued indicators. The reader should see the upgrade case at a glance.

---

## 11. Mobile (specific rules)

Mobile is not a smaller desktop. The interaction model is different.

### Type & spacing scale *up*, not down
- iOS base font is **17px**, macOS base is **13px**. The smaller screen needs *bigger* text, not squished text.
- Spacing stays generous. Don't pack content tighter to fit; rethink what's on the screen.

### Navigation
- **Bottom bar**: 3–5 primary destinations + one prominent action (often a `+` that opens a sheet or composer).
- Touch targets: **≥48px tall, ~72px wide**.
- If you have more nav than fits in a bottom bar, dedicate a **full home screen to nav** (Notion's pattern): recent items, action counts, big bottom search/CTA.

### Layout
- **One scroll direction per section.** Vertical *or* horizontal. Never two directions inside a single section — mobile screens can't show grids properly.
- **Cards** are the building block (whitespace is scarce; cards give structure).
- **No double-nested cards** — padding on padding kills usable space.
- **One screen, one thing.** A note editor doesn't need "recent notes" and "templates" stacked beneath it. Put those in a bottom sheet or a separate screen.

### Bottom sheets
- Use for contextual choices that shouldn't replace the current screen (template picker, share options, confirm action).
- Background should subtly **zoom out** when the sheet rises, and zoom back in when dismissed.
- Support drag-to-dismiss.

### Gestures
- **Swipe right → back.** Animate the previous page in from the left by ~35% of screen width as the current page slides off right.
- **Swipe up → search** (Slack / Apple Notes pattern).
- **Long press → context menu.** Blur background, scale the pressed element slightly, show options with icons.

### Dynamic actions
- Show actions **only when relevant**. Editing a note? Hide global nav; show formatting + share. Selecting items? Hide regular actions; show Bulk operations.
- Animate the swap so it doesn't feel jarring.

### Empty states (mobile-specific)
- First open: full-screen guidance pointing at the primary action with a clear instruction.
- Empty search: animate an empty-folder icon in, "Oops, nothing found", suggestion, "Try again" / "Clear filters".

---

## 12. Motion & micro-interactions

Animations earn their place. Use them for:
- **Feedback** (button press, toggle flip, confirmation)
- **Continuity** (where did this element come from / go to?)
- **Delight** (sparingly — and only where it doesn't slow the user down)

### Figma defaults
- **Smart Animate** for nearly every transition.
- **Custom easing (spring)** for natural motion. Good starting points:
  - General hover/pop-up: `Stiffness 636, Damping 24, Mass 1, ~500ms`
  - Tooltip pop-in: `Stiffness 720, Damping 29, Mass 1, ~414ms`
- "Gentle" and "Quick" presets work for entrance animations on web.
- For simple hovers: ease-out, 150–250ms.

### High-leverage micro-interactions (worth building)
1. **Button hover with text mask** — slide the label down, slide a contextual line up (e.g., "Book a call" → "3 spots open"). Pair with `while pressing` scale-down for click.
2. **Animated toast lifecycle** — "Update available" → progress bar fills → confetti on done.
3. **Name tag on avatar hover** — animated fade-and-slide tooltip with the name.
4. **Delayed tooltip on icon hover** — 1000ms enter delay, springy reveal.
5. **Text hover pop-out** — hovering text reveals related illustrations/icons.
6. **Animated progress bar mask** — colored fill that slides along the bar as steps complete.
7. **Card swipe with restack** — top card flies out (rotate + fade), cards behind scale up and shift to fill.
8. **Expanding search bar** — magnifying glass icon expands into a full input on tap.
9. **Hover for upgrade compare** — current limit slides out, upgraded limit slides in.
10. **Shimmer/gradient stroke** — animate a gradient circle inside a masked stroke for a glowing border (use sparingly).

### Don't
- **Scroll-jacking** — only on rare, high-effort marketing pages (Apple AirPods style). Never in product.
- **Animation everywhere** — if everything moves, nothing draws attention.
- **Linear, robotic transitions** for entrance animations. Use easing.

---

## 13. Playful web (anti-corporate-AI-mush)

This section is **landing pages and marketing only** — not app surfaces. App UI stays restrained; marketing can be more expressive.

The web has gotten sterile. AI-generated landing pages and "minimalist" templates all look the same. To stand out, add personality back in — **deliberately, with discipline**.

### More is more, applied thoughtfully
- Surround the central message with contextual illustrations: doodles, characters, themed icons (money, calendars, hot air balloons, coins — whatever matches your product).
- Elements should **trail off** toward the edges (denser near the hero, sparser at the periphery) to guide the eye inward.
- Place some elements **slightly off-grid** for energy — but always so they guide attention to the center, never randomly scattered.
- Set a **playfulness level** per product (e.g., 1–5) and stick to it. A crypto wallet can be high; an invoicing tool is medium; a compliance tool is low.

### Motion for delight
- Entrance animations: rotate + pop, fly in + bob, fade + slide-down. Use easing (Gentle, Quick) — not linear.
- **Parallax** with generous margins adds life as the user scrolls.
- Hover micro-interactions on text and elements — short, surprising, not constant.

### Animated narratives
- Text is ~80% of most pages. Make key phrases interactive.
- Replace words with **animated elements**: "deadlines" → a progress bar that fills; "paid" → bouncing dollar signs that resolve to text + checkmark.
- Use blur reveals, fade-and-slide entries, scroll-triggered text animations on hero copy.

### Finishing touches
- **Friendly copy** over corporate jargon ("We sweat the details" beats "Our team is meticulously focused on quality"). Defer to `mailchimp-copy-style`.
- **Custom 404 page** that ties to the brand theme. Examples that work: image-tile "404", a puzzle, a character from your illustration set, an animated metaphor.

### Inspiration
**Mobbin** is the single most-used inspiration source — curated screens, sections (Hero / Pricing / Footer), styles (Bold / Editorial / Brutalist / Playful), and full user flows from real apps. Use it to learn patterns, not to copy them.

---

## 14. The "vibe-coded" smell test

If a screen looks AI-generated, it usually fails a predictable list of checks. Audit against these before shipping:

- [ ] **No emojis as icons.** Replaced with Hugeicons.
- [ ] **No more than one font.** And it's a sans-serif.
- [ ] **Color count is under control.** No five-different-cards-five-different-colors situations. 60-30-10 holds.
- [ ] **No pure black or pure white** for backgrounds or surfaces. Tinted neutrals.
- [ ] **No gradient profile circles with letters.** Use real avatars or a clean monogram.
- [ ] **No "Current Plan" cards or other placeholder UI** that does nothing.
- [ ] **Pricing is 3–4 plans**, named honestly, with discounts shown.
- [ ] **KPIs aren't duplicated** across every page.
- [ ] **Repeating card actions** are collapsed to a kebab menu, not three visible buttons.
- [ ] **Forms with multiple fields** live in modals, not sparse flyouts.
- [ ] **Charts have gridlines and axis numbers.** And the chart type is one of: line, bar, donut, world map.
- [ ] **Landing page features** use real product screenshots, not generic stock icons.
- [ ] **Dark mode is a separate palette**, not inverted colors.
- [ ] **Destructive actions are red**, even if red isn't a brand color.

A screen that fails three or more of these will read as AI-generated. Fix them.

---

## 15. Presenting work (portfolio vs client)

Different audiences, different presentations.

### For portfolio (Dribbble / case studies)
Goal: wow the viewer.
- Plain background colors: take an accent from the UI, **desaturate and darken** to a grey-ish tone, add a faint shadow. Subtler than a vivid background; lets the UI pop.
- Dark mode designs: place large blurred circles of the accent color behind the UI for ambient glow.
- Glass backgrounds with gradient strokes — adds depth and edge definition.
- "Explode the image" — extend a UI element (line, slider, pattern) off the canvas.
- **Skew** the UI slightly for energy: try `~2° vertical, ~-14° horizontal` (or whatever reads dynamic without distorting badly).
- "Pop out" an important element — offset it from the page with a soft shadow, leave a grey placeholder where it was.
- **Collages** for multiple screens — offset, slightly rotate, skew the whole arrangement. Works for landing pages; **doesn't work for dashboards** (details get too small). Zoom into a dashboard section and animate it instead.

### For client meetings
Goal: build confidence in the product.
- **Realistic mockups**: MacBook, iPad, Apple Watch, iPhone in lifestyle settings.
- For custom contexts: generate a realistic background with AI ("MacBook Air, green screen on screen, on an orange faux leather chair, notebook and stool in background. Background blurred, soft shadows, moody lighting. Natural, lived in.") → punch out the green screen → skew your UI in.
- **Interactive prototypes**. Show, don't describe. Swipe, modal animations, delete flows — the client should feel it, not be told.

Portfolio presentations don't work in client meetings; client presentations don't sell on Dribbble. Different audience, different style.

---

## 16. The 30-second checklist

Before shipping any screen, run through:

- [ ] What's the **one thing** the user came here to do? Is it the most prominent thing on the screen?
- [ ] **One font?**
- [ ] **Spacing on the 4 or 8 grid?**
- [ ] **60-30-10** holds — not five competing colors?
- [ ] **Pure black/white** purged for tinted neutrals?
- [ ] **Dark mode** is its own palette, not an inversion?
- [ ] All button **states** wired (default / hover / pressed / disabled / loading)?
- [ ] All input **states** wired (default / focus / error / warning)?
- [ ] **Icons** are real icons (Hugeicons) and sized to match adjacent text line-height?
- [ ] **Empty states** are designed, not blank?
- [ ] **Optimistic UI** for common actions?
- [ ] **Charts** have gridlines, numbers, and hover details?
- [ ] **Mobile** uses one scroll direction per section, ≥48px touch targets?
- [ ] No **double-nested cards**?
- [ ] No **redundant KPIs** across pages?
- [ ] Destructive actions are **red**?
- [ ] Does this look like every other AI-generated app? If yes → §14.

---

## 17. Patterns we keep getting wrong

A running list. Add when we spot one.

- **Five accent colors on a file list.** Pick one accent + neutral.
- **Pure-white card on pure-white background** with a hard border. Tint the surfaces.
- **Same corner radius nested.** Apply `inner = outer − padding`.
- **Default kerning on a 96px hero.** Tighten to `-3%`.
- **Linear easing on every entrance animation.** Use a spring or a curve.
- **3-button row on every list card.** Kebab menu.
- **Settings page with 11 fields and no tabs.** Group into Usage / Billing / Account.
- **"Successfully created" toast.** Just "Created" or the noun ("Recipe saved").
- **Pricing card with non-functional "Current Plan" badge.** Delete it.
- **"View all" infinite-scroll with no footer ever reachable.** Use a "Load more" button.
- **Dashboard hero typography (64px H1).** Crank it down to 20–24px.
- **Emoji icon in a B2B SaaS sidebar.** Hugeicons.
- **Bright color for a 1200×800 background.** Backgrounds recede; only accents pop.
- **Dark mode = `invert()`.** Build the palette from scratch.
- **Tooltip that appears in 0ms.** Delay 1000ms.
- **Card padding 8px on mobile.** Mobile needs MORE space than desktop, not less.
