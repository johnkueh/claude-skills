# GPT Image 2 Prompting Guide (distilled)

Distilled from OpenAI's official cookbook: *Image Generation Models Prompting Guide*. Read this when you need to engineer a prompt — pick the category template, fill in the user's specifics, and verify against the anti-patterns at the bottom.

## Universal structure

Always order the prompt: **Scene/Background → Subject → Key Details → Composition → Constraints**.

Use short labeled segments or line breaks for complex requests, not one wall of text. Be concrete about materials, shapes, textures, and the visual medium (photo / watercolor / 3D render / flat vector). Include **intended use** (ad, UI mock, infographic, logo) to give the model context.

For literal text in the image: put it in **quotes** or **ALL CAPS**, specify font style/size/color/placement, and spell tricky words letter-by-letter.

For exclusions: be **explicit and specific**. Say "no watermark, no extra text, no logos/trademarks" — not just "clean".

## Category templates

### Logo

> Original, non-infringing logo for **<brand>**, a **<what they do>**. The logo should feel **<adjectives: warm/timeless/sharp/playful>**. Use clean, vector-like shapes, a strong silhouette, and balanced negative space. Favor simplicity over detail so it reads clearly at small and large sizes. Flat design, minimal strokes, no gradients unless essential. Single centered mark with generous padding. Plain background.

Key rules:
- Describe brand personality and use case, not just visual style
- Emphasize **simplicity**, **scalability**, **balanced negative space**
- Default to flat, no gradients, single centered mark with padding
- Use `--background transparent` if user wants a clean cut-out

### Illustration

> A **<medium: watercolor / flat vector / 3D render / pencil sketch / oil painting>** illustration of **<subject doing action>** in **<setting>**. **<2–4 style cues: brushwork, palette, line weight, texture>**. Composition: **<framing>**, **<viewpoint>**. Mood: **<adjective>**. **<Exclusions>**.

Key rules:
- Lead with the medium — it anchors everything else
- 2–4 specific style cues beat a long list of adjectives
- Targeted quality levers ("film grain", "brushstrokes", "macro detail") only when needed

### Photoreal

> **Photorealistic** candid photograph of **<subject>** **<action>** in **<setting>**. **<Real-world details: skin texture, pores, fabric wear, imperfections>**. Shot like a **<35mm film / iPhone / professional>** photograph, **<framing: medium close-up / wide / eye-level>** using a **<lens, e.g. 50mm>**. **<Lighting: soft coastal daylight / golden hour / overcast>**, **<depth of field>**, **<grain>**, natural color balance. The image should feel honest and unposed.

Key rules:
- The word "photorealistic" must appear (engages photoreal mode)
- Alt phrases: "real photograph", "taken on a real camera", "iPhone photo"
- Ask for **real texture** — pores, wrinkles, fabric wear, imperfections
- **Avoid** "studio polish", "cinematic lighting", "dramatic color grading", "movie-poster" — these flip the model to stylized
- Camera specs are taste cues, not exact simulation — don't over-spec

### Infographic / educational diagram

> Create a **<format: clean classroom handout / slide / poster>** titled "**<title in quotes>**" for **<audience>**. Show **<concept>**. Include: **<list required components explicitly>**. Use arrows to connect the steps, and label **<key items>**. Clean flat visual system with consistent icon style, readable labels, enough white space. White background, simple icons. Do not include **<exclusions>**.

Key rules:
- Write like an instructional design brief: audience + objective + format + required labels
- **Explicitly list every required component** — model won't infer them
- Use `--quality high` for dense labels and diagrams
- Specify what should NOT appear (decorative clutter, stock-photo imagery)

### UI mockup

> A **<phone / desktop / tablet>** screen of **<app/product>** showing **<screen purpose>**. Real interface elements: **<list: nav bar, list rows, primary button, etc.>**. Layout: **<hierarchy and spacing cues>**. Typography: clean, readable. Subtle colors, minimal decoration. The screen should look like a usable, shipped interface — not concept art.

Key rules:
- **Describe as if the product already exists**
- "Shipped interface", not "design sketch of"
- Real interface elements with practical constraints

### Ad / marketing

Write like a **creative brief**, not a technical spec:

> Ad / fashion shot for **<brand>**, a **<positioning: hip young streetwear / luxury / family-friendly>**. The ad shows **<scene>** with the tagline "**<exact copy in quotes>**". Make it feel like a polished campaign image for **<target audience>**: **<3–4 mood adjectives>**. Use clean composition, **<color direction>**, **<pose direction>**, **<photography cues>**.

Key rules:
- Brand positioning + audience + concept + composition + exact copy, all in one prompt
- Let the model make taste-driven decisions inside those boundaries
- Quote in-image text exactly

### Story panel / sequential art

> Panel **<N>** of **<story>**. Beat: **<what happens, concrete and action-focused>**. **<Character description, anchored each panel to avoid identity drift>**. **<Setting, time of day>**. Style: **<consistent medium and palette>**. **<Framing>**.

Key rules:
- One concrete action per panel
- **Re-describe each character every panel** to avoid drift
- Hold style + palette constant across panels

### Style transfer / moodboard (edit endpoint)

> Image 1: **<describe ref 1, e.g. style reference — watercolor brushwork, muted palette, paper texture>**.
> Image 2: **<describe ref 2, e.g. subject — woman standing on a cliff>**.
> Apply Image 1's **<specific style cues: brushwork, palette, texture>** to Image 2. Keep Image 2's **<composition, subject pose, framing>** unchanged. Do not copy Image 1's subject.

Key rules:
- **Always reference inputs by index** ("Image 1", "Image 2")
- Describe what each image is for in one short phrase
- Name the specific style cues to transfer (not "the style of Image 1")
- State explicitly what must NOT change in the subject image

### Edit (object remove / replace / change)

> **<Surgical instruction: "Remove the flower from the man's hand" / "Replace the white chair with a wooden chair">**. Preserve **<face, pose, lighting, background, camera angle, surrounding objects, saturation, contrast>**. Keep all other aspects of the image unchanged. **<Optional: photorealistic contact shadows and fabric texture>**.

Key rules:
- One surgical change per call — **iterate small, don't overload**
- **Repeat the preserve list every iteration** — the model doesn't remember previous turns
- For identity-sensitive edits, re-lock the subject's description every turn
- "Do not change anything else" is weak alone — list exactly what must remain

## Anti-patterns

- ❌ Long monolithic prompts that try to fix multiple things at once → iterate instead
- ❌ Assuming the model remembers previous edits → repeat preserve list each turn
- ❌ Generic stock-photo language for slides / diagrams / UI → write like an "artifact spec"
- ❌ Heavy camera specs hoping for exact simulation → use them for vibe only
- ❌ "Clean" / "professional" / "high-quality" without specifics → describe the actual visual properties
- ❌ Forgetting to quote literal text → spelling errors creep in
- ❌ For photoreal: words like "studio", "cinematic", "movie-poster", "dramatic" → flips to stylized
- ❌ For logos: detailed scenes, gradients, multiple colors → unscalable

## Worked examples (verbatim from the cookbook)

### Logo
> Create an original, non-infringing logo for a company called Field & Flour, a local bakery. The logo should feel warm, simple, and timeless. Use clean, vector-like shapes, a strong silhouette, and balanced negative space. Favor simplicity over detail so it reads clearly at small and large sizes. Flat design, minimal strokes, no gradients unless essential. Plain background.

### Photoreal
> Create a photorealistic candid photograph of an elderly sailor standing on a small fishing boat. He has weathered skin with visible wrinkles, pores, and sun texture, and a few faded traditional sailor tattoos on his arms. He is calmly adjusting a net while his dog sits nearby on the deck. Shot like a 35mm film photograph, medium close-up at eye level, using a 50mm lens. Soft coastal daylight, shallow depth of field, subtle film grain, natural color balance. The image should feel honest and unposed, with real skin texture, worn materials, and everyday detail.

### Infographic
> Create a simple biology diagram titled "Cellular Respiration at a Glance" for high school students. Show how glucose turns into energy inside a cell. Include glycolysis, the Krebs cycle, and the electron transport chain. Use arrows to connect the steps, and label the main molecules. Make it look like a clean classroom handout or slide, with a white background, simple icons, clear labels, and easy-to-read text.

### Ad
> Give me a cool in-culture ad / fashion shot for a brand called Thread. It's a hip young street brand. The ad shows a group of friends hanging out together with the tagline "Yours to Create." Make it feel like a polished campaign image for a youth streetwear audience: stylish, contemporary, energetic, and tasteful. Use clean composition, strong color direction, natural poses, and premium fashion photography cues.

### Edit (remove)
> Remove the flower from man's hand. Do not change anything else.

### Style transfer
> In this room photo, replace ONLY white chairs with chairs made of wood. Preserve camera angle, room lighting, floor shadows, and surrounding objects. Keep all other aspects of the image unchanged. Photorealistic contact shadows and fabric texture.

## Quality decision

| Use case | Quality |
|---|---|
| Drafts, exploration, thumbnails, high-volume | `low` (~$0.008) |
| Most everyday work — illustrations, basic ads | `medium` (~$0.04) |
| Logos (sharp lines), photoreal portraits, dense infographics, small text, identity-sensitive edits | `high` (~$0.13) |
