/**
 * src/styles/theme.js
 *
 * Single source of truth for every visual decision in the app.
 * All CSS custom properties in index.css are derived from this file.
 *
 * Design rationale:
 *   The palette mirrors the Hipocampus logo — pure black ground, pure white
 *   signal. No tint, no hue, no colour noise. Every element earns its place
 *   through contrast alone.
 *
 *   The one deliberate tension: user message bubbles are WHITE on the black
 *   canvas, while AI responses sit in dark charcoal. The human writes in
 *   light; the machine answers from the dark. This mirrors the hippocampal
 *   metaphor — memory retrieved from depth, user intent always foregrounded.
 *
 *   Semantic colours (error, warning, success) are the only hues allowed.
 *   They read as system signals, never decoration.
 *
 * Used by: every component that needs a design value,
 *          index.css (CSS custom property declarations).
 */

// ---------------------------------------------------------------------------
// Palette
// ---------------------------------------------------------------------------

export const colors = {
  /** Page background — pure black, matching the logo ground */
  bgBase: "#000000",

  /** Card / panel surface — barely lifted off pure black */
  bgSurface: "#0F0F0F",

  /** Input fields and subtle inset areas */
  bgInput: "#1A1A1A",

  /** Hairline borders and dividers */
  border: "#2A2A2A",

  /** Muted border for hover states */
  borderHover: "#3D3D3D",

  /** Primary body text — pure white */
  textPrimary: "#FFFFFF",

  /** Secondary / supporting text */
  textSecondary: "#9A9A9A",

  /** Placeholder text inside inputs */
  textPlaceholder: "#555555",

  /**
   * White accent — the signature element.
   * Replaces phosphor-green. Used for: primary CTAs, active states,
   * focus rings, the send button, key badges.
   * Never decorative — only for actionable or active elements.
   */
  accent: "#FFFFFF",

  /** Slightly dimmed accent for hover states on accent-coloured elements */
  accentHover: "#DDDDDD",

  /** Faint white fill for selected / active backgrounds */
  accentSubtle: "rgba(255, 255, 255, 0.06)",

  /**
   * User message bubble — WHITE.
   * The human's words appear on a white ground; text must be black.
   * See --color-bubble-user-text below.
   */
  bubbleUser: "#FFFFFF",

  /** Text colour on user bubble (white bg → black text) */
  bubbleUserText: "#000000",

  /** AI message bubble — dark charcoal, distinct from pure black base */
  bubbleAI: "#141414",

  /** Error / danger states */
  error: "#F87171",

  /** Warning / caution states */
  warning: "#FBBF24",

  /** Success confirmation */
  success: "#34D399",
};

// ---------------------------------------------------------------------------
// Typography
// ---------------------------------------------------------------------------

export const fonts = {
  display: "'Space Grotesk', sans-serif",
  body: "'Inter', sans-serif",
  mono: "'Fira Code', 'Cascadia Code', 'Consolas', monospace",
};

export const fontWeights = {
  regular: 400,
  medium: 500,
  bold: 700,
};

export const fontSizes = {
  xs:   "0.6875rem",  // 11px
  sm:   "0.8125rem",  // 13px
  base: "0.9375rem",  // 15px
  md:   "1.0625rem",  // 17px
  lg:   "1.25rem",    // 20px
  xl:   "1.625rem",   // 26px
  "2xl":"2.25rem",    // 36px
};

// ---------------------------------------------------------------------------
// Spacing (8-point grid)
// ---------------------------------------------------------------------------

export const spacing = {
  1:  "0.25rem",
  2:  "0.5rem",
  3:  "0.75rem",
  4:  "1rem",
  5:  "1.25rem",
  6:  "1.5rem",
  8:  "2rem",
  10: "2.5rem",
  12: "3rem",
  16: "4rem",
};

// ---------------------------------------------------------------------------
// Border radius
// ---------------------------------------------------------------------------

export const radius = {
  sm: "6px",
  md: "10px",
  lg: "999px",
};

// ---------------------------------------------------------------------------
// Shadows
// ---------------------------------------------------------------------------

export const shadows = {
  card:       "0 4px 24px rgba(0, 0, 0, 0.8)",
  popover:    "0 8px 40px rgba(0, 0, 0, 0.9)",
  // Subtle white glow — used on focused inputs and active send button.
  accentGlow: "0 0 16px rgba(255, 255, 255, 0.10)",
};

// ---------------------------------------------------------------------------
// Motion
// ---------------------------------------------------------------------------

export const transitions = {
  fast:   "120ms ease",
  base:   "200ms ease",
  smooth: "300ms cubic-bezier(0.4, 0, 0.2, 1)",
};

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export const layout = {
  chatMaxWidth:   "760px",
  headerHeight:   "56px",
  inputAreaHeight:"80px",
};