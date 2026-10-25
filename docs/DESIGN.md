# Talking — Design System & Visual Identity: "Proof Desk"

> *Talking is not a chatbot. It is a desk where a draft gets proofed before it is sent.*

---

## 1. Core Identity & Philosophy

Most AI products suffer from conversational and visual convergence: floating glass rectangles, glowing purple blobs, generic pastel pills, and sparkling stars. These metaphors imply a magical chatbot speaking on your behalf.

**Talking is an editorial proof desk.** It rejects conversational AI gimmicks in favor of physical print typesetting, newsroom copy-editing, and mechanical precision. 

- **No AI sparkles (`✦`), no emojis as interface icons.**
- **No glassmorphism, no backdrop-filter blur, no drop shadows, no color gradients.**
- **Flat ink and paper substrate with razor 1px hairline rules.**
- **Functional 24px baseline grid** behind the draft desk and composer, aligning typography to physical lines.
- **Single editorial accent (`#FF4F1F`)** inspired by a copy editor's proofing pencil.

---

## 2. The Two-Register Rule

Typography in Talking strictly separates human communication from machine instrumentation.

| Register | Purpose | Typography & Size | Rules |
| :--- | :--- | :--- | :--- |
| **Voice** | Anything that could be sent to another person (thread messages, drafts, composer input). | Humane Serif (`Newsreader`, `Source Serif 4`, `Georgia`), 15px size, 24px line height (`15px/24px`), high contrast. | Sits on the 24px baseline grid. Never styled in uppercase or tracked out. |
| **Machine** | Everything else (labels, counts, shortcuts, tone tabs, buttons, status dots, metadata tags). | High-legibility Monospace (`Geist Mono`, `JetBrains Mono`, `ui-monospace`), 12px size, 16px line height, uppercase, `+0.04em` tracking. | Never used for message text. Dense, precise, tabular. |

**The Invariant:** If a user could send it, it is **Voice**. Otherwise, it is **Machine**. *Never mix.*

---

## 3. Color Tokens & Material Substrate

### Light Mode (Primary Substrate: Warm Paper)
- **Paper Substrate (`--bg-app`)**: `#F2EFE8` (warm tactile newsprint/cream)
- **Ink (`--ink`, `--text-main`)**: `#16140F` (deep carbon black)
- **Surface / Desk (`--bg-surface`, `--bg-desk`)**: `#E8E4DC` / `#F7F5F0`
- **Hairline Rule (`--hairline`)**: `rgba(22, 20, 15, 0.18)` (18% ink)
- **Baseline Grid (`--grid-line`)**: `rgba(22, 20, 15, 0.06)` (6% ink, drawn strictly on composer & draft desk)
- **Flat Editorial Chrome**: Precision planar surfaces with razor-sharp hairline borders, zero drop shadows, and zero gradients.
- **Text Muted (`--text-muted`)**: `rgba(22, 20, 15, 0.62)`
- **Sole Accent (`--accent`)**: `#FF4F1F` (proofreader orange-red; used ONLY for caret, revision marks, active tab underline, focus ring)

### Dark Mode (Carbon Proof Board)
- **Background (`--bg-app`)**: `#0F0E0B`
- **Surface (`--bg-surface`, `--bg-desk`)**: `#17150F` / `#13120D`
- **Text / Paper (`--text-main`, `--ink`)**: `#ECE7DA`
- **Hairline Rule (`--hairline`)**: `rgba(236, 231, 218, 0.18)`
- **Baseline Grid (`--grid-line`)**: `rgba(236, 231, 218, 0.06)`
- **Flat Editorial Chrome**: Zero drop shadows, zero specular gradients.
- **Text Muted (`--text-muted`)**: `rgba(236, 231, 218, 0.62)`
- **Sole Accent (`--accent`)**: `#FF4F1F`

### Fluid Kinematics & Motion Physics (Apple Fluid Interfaces & Wispr Flow)
- **Rational Damped Springs**:
  - `--spring-fluid`: `cubic-bezier(0.16, 1, 0.3, 1)` (Apple hyperbolic settle curve for modal expansion)
  - `--spring-snappy`: `cubic-bezier(0.34, 1.45, 0.64, 1)` (Wispr tactile spring with subtle detent overshoot)
  - `--spring-squish`: `cubic-bezier(0.2, 0.8, 0.2, 1)` (Volume preservation click/launch squish)
- **Volume Preservation ($\Delta V = 0$)**: On click/trigger, physical elements briefly squish along one axis while expanding along the other (`scale(0.96, 1.04)`) before releasing, conveying physical mass and surface tension without messy gooey SVG distortion.
- **Staggered Bubble Cascade**: Multi-bubble draft bursts cascade in with rational 40ms stagger delays.
- **Strictly No Mercury**: No SVG `feColorMatrix` blob merging or molten threshold filters. Razor-sharp optical refraction and geometry only.

---

## 4. Component Rules

### Chrome & Shape
- **Corner Radii**: Chrome panels, buttons, cards, and inputs strictly use `2px` radius.
- **Message Bubbles**: Asymmetrical `14px` radius with a sharp `2px` corner on the speech tail side:
  - *Received messages*: `14px 14px 14px 2px`, 1px solid hairline border, transparent paper fill.
  - *Sent messages*: `14px 14px 2px 14px`, solid ink fill (`#16140F`), paper text (`#F2EFE8`).
- **Drafts in Desk**: Right-aligned `1px dashed var(--accent)` or `var(--ink)` bubbles with mono index (`01`, `02`). Burst order. Solidifies to ink bubble upon approval.
- **Borders & Shadows**: Strict 1px hairline borders (`var(--hairline)`). `box-shadow: none` and `backdrop-filter: none` everywhere.

### Header
- Wordmark: lowercase `"talking"` set in the Voice serif, followed immediately by a solid rectangular block caret (`█`) blinking at `steps(1)` with a 1-second cycle.
- Fixed contact selector and status readouts cleanly spaced without overlapping.
- Memory counter in Machine mono: e.g. `266 MEM`.
- Mode switch: Machine mono toggle (`LIGHT` / `DARK`).

### Thread + Draft Desk
- Rigid flex column layout. The draft desk **never overlays or obscures** the chat thread.
- Thread auto-scrolls to keep the latest message in plain view.
- **Empty State**: Exact ~40px row reading `NO DRAFT · Ctrl+Enter to generate`.
- Takes / Variants: Replaces pill buttons with mono tab strips (`A · CHILL [2]`, `B · DIRECT`, `C · BANTER [2]`) highlighted with a 2px `#FF4F1F` bottom accent line.
- Revision Marks: Toggle button labeled `MARKS`. When active, newly generated or steered drafts highlight added words with accent underline and removed words with muted strikethrough.

### Composer
- Single Voice serif textarea resting directly upon 24px baseline grid rules.
- Secondary "margin-note" directive bar revealed via `Ctrl+K` or "NOTE" button.
- Native file input hidden with accessible 1.5px stroke Lucide attach button.
- Pro Mode toggle rendered as a discrete Machine mono switch (`PRO [ON/OFF]`).

### Contact Sidebar
- Replaces identical stacked form boxes with structured editorial sections:
  1. Name header block.
  2. Segmented control for Relationship Stage & Conversation Goal.
  3. Interactive tag chips for Interests (`#music ✕`).
  4. Line-separated Inside Jokes.
  5. Collapsible Notes drawer.
  6. Known Facts formatted as index-card rows with category mono tags (`PREF`, `WORK`, `PET`) and relative timestamp.
- Preserves all underlying DOM inputs, IDs, and event bindings for 100% test compatibility.

### WhatsApp Copilot (Shadow DOM)
- Isolated inside `container.attachShadow({ mode: 'open' })` to guarantee zero WhatsApp CSS leakage.
- Inherits WhatsApp Web's light or dark mode automatically via `document.body` class detection.
- Floating Pill: 2px radius rectangle with mono `TALK · Alt+D` and the blinking block caret.
- Modal: Reuses the Proof Desk draft desk tokens and tabbed layout.

---

## 5. Prohibited Patterns ("The Don'ts")

1. **NO Glassmorphism**: No frosted glass, `backdrop-filter: blur()`, or transparent acrylics.
2. **NO Drop Shadows**: No ambient glowing shadows, soft drop-shadow blurs, or layer elevations.
3. **NO Decorative Gradients**: No purple, lavender, pink, cyan, or pastel linear/radial gradients.
4. **NO Pill Capsules**: No rounded 9999px pills for chrome or buttons; only chrome `2px` and bubble `14px/2px`.
5. **NO Emojis as UI Icons**: No ✦, 💬, ⚡, 🎯, 🖼️, 📥, 🧬, 🎨, 💾. Use 1.5px stroke line icons.
6. **NO Wallpaper Grids**: The 24px baseline grid belongs strictly behind the draft desk and composer.
