# DESIGN.md

Project: Notes Toolkit Dashboard
Version: 1.0
Last Updated: 2026-04-23

## Intent

Create a clean, data-dense dashboard UI with Google-style clarity:
- calm surfaces
- clear primary actions
- strong information hierarchy
- fast scanability on desktop and mobile

This file is the design source of truth for frontend implementation.

## Visual Direction

- Design language: Google Material-inspired dashboard (modern, neutral, utility-first).
- Tone: reliable, productive, calm.
- Contrast: readable text contrast on all surfaces.
- Density: compact but breathable row and card spacing.

## Color System

Use semantic tokens in CSS variables:

- `--md-sys-color-primary`: `#0b57d0`
- `--md-sys-color-on-primary`: `#ffffff`
- `--md-sys-color-primary-container`: `#d3e3fd`
- `--md-sys-color-on-primary-container`: `#041e49`
- `--md-sys-color-surface`: `#f8f9fa`
- `--md-sys-color-surface-container`: `#ffffff`
- `--md-sys-color-surface-container-high`: `#eef2ff`
- `--md-sys-color-outline`: `#c9cdd5`
- `--md-sys-color-outline-variant`: `#dfe3eb`
- `--md-sys-color-on-surface`: `#1f1f1f`
- `--md-sys-color-on-surface-variant`: `#5f6368`
- `--md-sys-color-success`: `#137333`
- `--md-sys-color-warning`: `#b06000`

## Typography

- Primary font stack: `"Roboto", "Noto Sans SC", "Segoe UI", sans-serif`
- Page title: 24px, semi-bold
- Section titles: 15px, semi-bold
- Body/list rows: 13px
- Meta/help text: 12-13px

## Shape & Elevation

- Large radius: 18px (main panels)
- Medium radius: 12px (cards)
- Small radius: 10px (rows/inputs)
- Pills: 999px radius (buttons/chips)
- Elevation 1: subtle card separation
- Elevation 2: hover/emphasis surfaces

## Spacing

- Base spacing unit: 4px
- Common gaps:
  - 8px: row internals
  - 12px: card internals
  - 14-16px: major container padding

## Component Rules

### Header
- White-to-light surface gradient.
- Keep status/meta text muted.
- Toolbar wraps on small screens.

### Buttons
- Default: outlined pill button.
- Primary: filled blue (`primary`) with white text.
- Icon buttons: circular/pill with consistent 30px touch target.
- Hover/press states should be visible but subtle.

### Inputs
- Pill-shaped inputs for add/edit actions.
- Clear focus ring for keyboard users.
- Maintain minimum 13px text size.

### Cards & Lists
- Card = surface container + soft border + low elevation.
- Rows should maintain strong scanability and avoid visual noise.
- IDs use chip style with primary container background.

### Status Colors
- Pending: warning
- Promoted/Done: success
- Recovered rows: warm highlight background

## Motion

- Transitions: 120-180ms for hover/focus/press.
- Use only meaningful micro-interactions.
- Respect reduced-motion preference (`prefers-reduced-motion: reduce`).

## Responsive Behavior

- Desktop: 2-column layout with right-side stacked cards.
- Tablet/mobile: collapse to 1 column.
- Toolbar buttons become 2-column, then 1-column at very small widths.
- Preserve readable text wrapping for long todo/note content.

## Accessibility

- Keep visible focus styles on interactive controls.
- Maintain sufficient contrast between text and surfaces.
- Prefer semantic HTML and clear button labels.

## Implementation Mapping

- Design tokens are implemented in `frontend/index.html` inside `:root`.
- Component styles (cards, rows, buttons, inputs, focus, motion) are implemented in the same file.

## References

- Google Blog (Mar 18, 2026): Stitch introduces `DESIGN.md` for import/export design rules.
- Material Design 3 principles for color, shape, hierarchy, and state clarity.
