---
name: onboarding-tutorial
description: Build a full-bleed onboarding tutorial carousel for Expo/React Native apps. Generates watercolor background images via GPT Image Gen, creates animated widget overlays per slide, writes mailchimp-style copy, and wires into the existing auth flow. Use when adding onboarding to a new app, redesigning a welcome screen, or building a feature tour. Triggers on "onboarding", "tutorial", "welcome screen", "feature tour", "app intro", "first-time experience", "onboarding carousel", "walkthrough screens".
---

# Onboarding Tutorial Carousel

Build a swipeable onboarding tutorial for Expo/React Native apps. Full-bleed watercolor backgrounds crossfade between slides. Animated widget overlays demonstrate each feature concretely. Text fades in from below. Brand-colored CTAs.

Proven across recipes.im and journeys.im. Pattern B from Mobbin research — the most universal onboarding pattern (Kitchen Stories, Vrbo, IHG, CREME all ship it).

---

## 1. The pattern

Each onboarding is a **crossfade carousel** with 4-5 slides:

| Slide | Purpose | Widget type |
|-------|---------|-------------|
| 1. Welcome | Brand intro, tagline | None — image + text only |
| 2-4. Features | One value prop per slide | Animated UI mock (cards, pills, lists) |
| 5. Differentiator | What makes this app unique | Animated UI mock |

**Shared structure per slide:**
- Full-bleed watercolor background image (generated via GPT Image Gen)
- LinearGradient scrim from transparent → rgba(0,0,0,0.8) covering bottom 65%
- Headline: 28px, semibold, white, center-aligned, 4 words max
- Subtitle: 16px, regular, white 70% opacity, center-aligned, under 15 words
- Pagination dots: 8px circles, white active / white 30% inactive
- CTA button: brand accent color, white text, 52px tall, 14px border radius
- Last slide CTA: "Get started" instead of "Next"

**Animations:**
- Backgrounds: crossfade via reanimated shared opacity value, 500ms
- Text: fade-in-up (opacity 0→1, translateY 30→0, 400ms)
- Widgets: FadeIn 400ms with 200ms delay
- Navigation: fling gesture (left/right) via react-native-gesture-handler, with `runOnJS` bridge

---

## 2. Prerequisites

The target project must have these dependencies (all standard in Expo 54+):

```
expo-image
expo-linear-gradient
react-native-reanimated
react-native-gesture-handler
react-native-safe-area-context
```

Check with: `grep -E "expo-image|expo-linear-gradient|reanimated|gesture-handler" app/package.json`

---

## 3. Step-by-step workflow

### 3a. Gather context

Before writing any code:

1. **Read the app's CLAUDE.md** — find brand color, styling approach (Tailwind/inline), accent colors
2. **Find the welcome/auth screen** — the file that currently shows first to signed-out users
3. **Find the auth gate** — how the app routes between signed-out → signed-in states
4. **Find the sign-in screen path** — the route the carousel's "Get started" button should push to
5. **Check global.css or theme file** — extract accent color hex for buttons

### 3b. Design slides

For each app, identify 4-5 slides:

1. **Welcome** — brand name + one-sentence value prop. No widget.
2. **Core feature #1** — the primary thing users do. Widget: animated UI cards.
3. **Core feature #2** — the second key feature. Widget: animated UI mock.
4. **Core feature #3** — a differentiator or delight feature. Widget: animated UI mock.
5. **Collaboration/sync** — if multi-user. Widget: two side-by-side lists that sync.

### 3c. Write copy (mailchimp style)

Apply these rules to every headline and subtitle:

- **Active voice, second person** — "Save from anywhere", not "Recipes can be saved"
- **Headline: 4 words max** — front-load the verb
- **Subtitle: one sentence, under 15 words** — say what it does, not what it is
- **No exclamation marks** — the feature is the excitement
- **No marketing fluff** — "powerful", "seamless", "revolutionary" are banned
- **Contractions are fine** — "it's", "you're", "don't"
- **Avoid curly/smart quotes** — they break JS string literals. Use straight quotes, or wrap in double-quote strings for apostrophes.

### 3d. Generate watercolor backgrounds

Use the GPT Image Gen skill (`claude-skills:gpt-image-gen-2`) to generate one background per slide.

**Template prompt — adapt the subject for each slide:**

```
Editorial watercolor illustration of [SUBJECT DESCRIPTION].
[SPECIFIC DETAILS — objects, lighting, composition].
Organic brush strokes with subtle watercolor bleeding,
warm muted palette ([3-4 colors from the app's brand palette]),
textured paper feel. Bottom third fades to dark shadow.
No text, no people, no UI elements.
```

**Settings:**
- Size: `1024x1536` (portrait)
- Quality: `high`
- Format: `jpeg`
- Flag: `--no-open`

**Important:**
- All backgrounds in a set must share the same palette instruction for visual consistency
- The "bottom third fades to dark shadow" instruction is critical — it creates the natural gradient for white text
- Save to `app/assets/onboarding/` with descriptive names

**Cost:** ~$0.19 per image, ~$0.95 for 5 slides.

### 3e. Create the carousel component

The carousel component (`OnboardingCarousel.tsx`) is **identical across projects** — only the accent color in the CTA button changes. Copy from the template below and update:

1. The button `backgroundColor` to the app's accent color
2. Any import paths if the project uses a different alias structure

### 3f. Create widget components

Each widget is a self-contained component. Common widget types:

| Widget | Good for | Key elements |
|--------|----------|-------------|
| **Import cards** | "Save from anywhere" features | Staggered white cards with checkmark + source label, fade-in-up |
| **Voice pill** | Voice/audio features | White pill matching app's actual voice bar, streaming text cycling through phrases |
| **Grocery/checklist** | List features | White card with accent-colored animated checkmarks, staggered fade-in |
| **Nutrition bars** | Data/analytics features | White card with animated progress bars in accent color |
| **Timeline** | Sequential features (trips, events) | Vertical nodes with animated connecting lines, fade-in |
| **Chat bubble** | AI/agent features | Streaming text in a translucent bubble + typing indicator dots |
| **Sync lists** | Collaboration features | Two side-by-side mini checklists, "You" + "Household/Team", checks mirror with delay |

**Widget design rules:**
- Solid white backgrounds (not transparent) — must read against any background image
- Shadows: `shadowOpacity: 0.08-0.15`, `shadowRadius: 8-14`
- Border: `borderWidth: 1, borderColor: '#E5E5E5'`
- Border radius: 12-16px for cards, 999 for pills
- Use the app's accent color for checkmarks, progress bars, icons — never hardcode green
- Stagger animations 200-300ms apart for cascade effect
- Use `react-native-reanimated` for all animations

### 3g. Wire into the auth flow

Replace the existing welcome screen's content with the carousel:

```tsx
import { OnboardingCarousel } from '@/components/onboarding/OnboardingCarousel';
// ... import widgets and background images

export default function WelcomeScreen() {
  const router = useRouter();
  return (
    <OnboardingCarousel
      slides={SLIDES}
      onComplete={() => router.push('/sign-in')}
    />
  );
}
```

Keep any existing `<Stack.Screen>` options, `<StatusBar>` config, etc.

### 3h. Fix sign-in button colors

Check all auth screens (sign-in, create account, join) for `text-accent-foreground` on buttons — this resolves to black in dark mode on most apps. Replace with `text-white` for consistency with the onboarding carousel's white-on-accent buttons.

### 3i. Typecheck

**Always run `npx tsc --noEmit` before reporting completion.** Common issues:
- Curly/smart quotes (`'` `'`) in string literals — use straight quotes
- Missing icon imports — grep the codebase for the exact icon name before using it
- `require()` paths — verify asset files exist at the referenced path

---

## 4. Component templates

### OnboardingCarousel.tsx

Core carousel — crossfade backgrounds, gesture navigation, animated text.

**Customization points:**
- Line with `backgroundColor: '#FF5A5F'` — change to the app's accent color
- Import paths (`@/components`, `@assets`) — match the project's alias config

```tsx
// See recipes.im or journeys.im implementations for the full component.
// The structure is identical — only the accent color changes.
```

### Widget template (staggered card list)

```tsx
const ITEMS = [
  { title: '...', subtitle: '...', delay: 300 },
  { title: '...', subtitle: '...', delay: 600 },
  { title: '...', subtitle: '...', delay: 900 },
];

function Card({ title, subtitle, delay }) {
  const opacity = useSharedValue(0);
  const translateY = useSharedValue(16);

  useEffect(() => {
    opacity.value = withDelay(delay, withTiming(1, { duration: 300 }));
    translateY.value = withDelay(delay, withTiming(0, { duration: 300 }));
  }, []);

  const style = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }],
  }));

  return (
    <Animated.View style={[cardStyles, style]}>
      {/* accent-colored icon + title + subtitle */}
    </Animated.View>
  );
}
```

---

## 5. Reference implementations

- **recipes.im** — `app/src/app/onboarding/index.tsx` + `app/src/components/onboarding/`
  - 5 slides: Welcome, Save, Cook, Nutrition, Shop together
  - Accent: `#F97316` (orange)
  - Widgets: import cards, voice pill with streaming text, nutrition bars, syncing grocery lists

- **journeys.im** — `app/src/app/(auth)/welcome.tsx` + `app/src/components/onboarding/`
  - 5 slides: Welcome, Forward bookings, Trip assembled, Ask agent, Travel together
  - Accent: `#FF5A5F` (coral)
  - Widgets: email cards, timeline with animated lines, chat bubble with streaming text, syncing trip lists

---

## 6. Common pitfalls

- **Gesture callbacks need `runOnJS`** — fling `onEnd` runs on the UI thread; `setActiveIndex` is React state. Wrap with `runOnJS(callback)()`.
- **Smart quotes break JS** — LLMs love curly apostrophes (`'`). Always use straight quotes or wrap in double-quote strings.
- **`expo-image` transition is not animated opacity** — setting `opacity` inline on `<Image>` snaps; use a wrapping `<Animated.View>` with `useAnimatedStyle` for the crossfade.
- **Don't use emojis in widgets** — they look out of place against watercolor backgrounds. Use the app's actual icon library or solid-color shapes.
- **Metro caches images aggressively** — if updating images, rename the files (add `-v2`) to bust the cache.
- **Button text color** — always white on accent buttons regardless of dark/light mode. Don't use `text-accent-foreground` (resolves to black in dark mode on most themes).
