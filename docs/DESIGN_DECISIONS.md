# ALBA ONE — Brand & Design Decisions (`docs/DESIGN_DECISIONS.md`)

## 1. Strict ALBACONNECT Brand Token Binding (`albaconnect.co.jp/about/brand`)
- **Typography**:
  - Japanese body & UI: `Zen Kaku Gothic New`
  - Latin body & numerals: `Manrope` (with `font-variant-numeric: tabular-nums` enforced on all tables and numeric KPIs)
  - Large English display headings: `Inter Tight`
- **Colour Palette (Light Theme Only; No Gradients or Heavy Shadows)**:
  - **Primary (`40 = #0052FF`)**: Primary actions, active navigation indicators, primary focus rings.
  - **Secondary (`40 = #006685`)**: Evidence chips (`ev_001`...), citations, structural accents, and verified/completed indicators.
  - **Tertiary (`40 = #8424DA`)**: Subtle accent badge for AI-generated artifacts (`AI推奨 / AI recommendation`, `proposed_lesson`).
  - **Quaternary (`40 = #B6250A`)**: Alerts, guardrail blocks, hard-constraint violations, and unverified-parameter warnings.
  - **Neutral Scale**: Text `#1B1B1B` (primary) to `#5E5E5E` (secondary/muted); structural rules/borders `#C6C6C6` and `#E2E2E2`; surfaces `#FFFFFF` and `#F7F7F7`.

## 2. Open Brand Question for Owner (`TODO(owner)` — Success / Done Colour)
- **No Green in Brand Palette**: The official ALBACONNECT brand specification has no green colour scale.
- **Current Implementation**: Per Principle 10, we do not invent a green hex code. All `"success / done / confirmed / passed"` states use an explicit checkmark icon (`✓`) + bilingual text label styled with **Secondary (`#006685`)** or **Neutral (`#1B1B1B`)** border/text so status is never conveyed by colour alone.
- **`TODO(owner)` Question for Design/Brand Owner**: Should ALBACONNECT add an official semantic success token to the brand system, or retain `Secondary (#006685)` + icon + text label permanently for completed/verified states?
