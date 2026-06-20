/**
 * src/styles/theme.js
 *
 * Single source of truth for every visual decision in the app.
 * Import individual tokens in components rather than hardcoding values.
 * All CSS custom properties in index.css are derived from this file,
 * keeping JS animations and CSS in sync without duplication.
 *
 * Design rationale:
 *   Hipocampus is a memory system — the palette leans into deep indigo
 *   (neural, nocturnal, focused) contrasted with a phosphor-green accent
 *   (#7EE8A2) that suggests live electrical activity. The signature element
 *   is the accent: one pure pop of bioluminescent green on a near-black
 *   surface, used sparingly so it always reads as "signal, not noise."
 *
 * Used by: every component that needs a design value,
 *          index.css (CSS custom property declarations).
 */

// ---------------------------------------------------------------------------
// Palette
// ---------------------------------------------------------------------------

export const colors = {
  /** Page background — deep navy-black, not pure #000 to avoid harsh contrast */
  bgBase: "#0D0F1A",

  /** Card / panel surface — one step lighter than bgBase */
  bgSurface: "#161829",

  /** Input fields and subtle inset areas */
  bgInput: "#1E2135",

  /** Hairline borders and dividers */
  border: "#2A2D45",

  /** Muted border for hover states */
  borderHover: "#3D4166",

  /** Primary body text — near-white with a faint cool tint */
  textPrimary: "#E8EAF6",

  /** Secondary / supporting text — dimmed but still readable */
  textSecondary: "#8B90B8",

  /** Placeholder text inside inputs */
  textPlaceholder: "#5A5F80",

  /**
   * Phosphor-green accent — the signature element.
   * Use only for: primary CTAs, active states, the logo glyph,
   * and the send button. Never for decorative purposes.
   */
  accent: "#7EE8A2",

  /** Darker tint of accent for hover states on accent-coloured elements */
  accentHover: "#5EC988",

  /** Faint accent fill for selected/active backgrounds (low opacity) */
  accentSubtle: "rgba(126, 232, 162, 0.08)",

  /** User message bubble background in the chat window */
  bubbleUser: "#1E2135",

  /** AI message bubble background — slightly lighter to differentiate */
  bubbleAI: "#252840",

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
  /**
   * Display face — used for headings, the logo wordmark, and the login key.
   * Space Grotesk's slight irregularity prevents the cold sterility common
   * in tech products while remaining rigorously geometric.
   */
  display: "'Space Grotesk', sans-serif",

  /**
   * Body / UI face — used for everything else: labels, body copy,
   * chat messages, form inputs, nav items.
   * Inter is optimised for on-screen readability at small sizes.
   */
  body: "'Inter', sans-serif",
};

export const fontWeights = {
  regular: 400,
  medium: 500,
  bold: 700,
};

export const fontSizes = {
  /** 11px — timestamps, fine print */
  xs: "0.6875rem",
  /** 13px — secondary labels, captions */
  sm: "0.8125rem",
  /** 15px — primary body text, chat messages */
  base: "0.9375rem",
  /** 17px — slightly emphasised body */
  md: "1.0625rem",
  /** 20px — section headings */
  lg: "1.25rem",
  /** 26px — page headings */
  xl: "1.625rem",
  /** 36px — hero / display text */
  "2xl": "2.25rem",
};

export const lineHeights = {
  tight: "1.2",
  normal: "1.5",
  relaxed: "1.7",
};

// ---------------------------------------------------------------------------
// Spacing (4px base grid)
// ---------------------------------------------------------------------------

export const spacing = {
  "0": "0",
  "1": "0.25rem",  /*  4px */
  "2": "0.5rem",   /*  8px */
  "3": "0.75rem",  /* 12px */
  "4": "1rem",     /* 16px */
  "5": "1.25rem",  /* 20px */
  "6": "1.5rem",   /* 24px */
  "8": "2rem",     /* 32px */
  "10": "2.5rem",  /* 40px */
  "12": "3rem",    /* 48px */
  "16": "4rem",    /* 64px */
};

// ---------------------------------------------------------------------------
// Border radius
// ---------------------------------------------------------------------------

export const radius = {
  /** Sharp — used for code blocks and the login key display */
  none: "0",
  /** Subtle rounding — inputs, cards */
  sm: "6px",
  /** Default — most buttons and panels */
  md: "10px",
  /** Pill — tags, small badges */
  lg: "999px",
};

// ---------------------------------------------------------------------------
// Shadows
// ---------------------------------------------------------------------------

export const shadows = {
  /** Subtle lift for cards and modals */
  card: "0 4px 24px rgba(0, 0, 0, 0.4)",
  /** Stronger lift for dropdowns / popovers */
  popover: "0 8px 40px rgba(0, 0, 0, 0.6)",
  /** Accent glow — used on the send button and active accent elements */
  accentGlow: "0 0 16px rgba(126, 232, 162, 0.25)",
};

// ---------------------------------------------------------------------------
// Transitions
// ---------------------------------------------------------------------------

export const transitions = {
  /** Fast — hover colour changes, button states */
  fast: "120ms ease",
  /** Default — most UI transitions */
  base: "200ms ease",
  /** Smooth — panel slides, modal entries */
  smooth: "300ms cubic-bezier(0.4, 0, 0.2, 1)",
};

// ---------------------------------------------------------------------------
// Breakpoints (used in media queries)
// ---------------------------------------------------------------------------

export const breakpoints = {
  /** Mobile-first: styles above this are "tablet and up" */
  md: "768px",
  /** Desktop */
  lg: "1280px",
};

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------

export const layout = {
  /** Maximum width of the chat column */
  chatMaxWidth: "760px",
  /** Height of the top navigation bar */
  headerHeight: "56px",
  /** Height of the chat input area at the bottom */
  inputAreaHeight: "80px",
};