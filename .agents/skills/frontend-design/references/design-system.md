# Design System Reference

## Purpose
A design system is the shared visual and interaction language of the product. Extend the current system; do not create a competing theme for an individual page.

## Discovery checklist
Before changing styles, inspect:
- Global tokens and CSS custom properties.
- Typography, font loading, Thai glyph rendering, and line-height.
- Existing buttons, inputs, dialogs, menus, navigation, status badges, and cards.
- Light/dark theme behavior, if implemented.
- Spacing, radius, border, elevation, focus, and semantic color conventions.
- Existing responsive breakpoints and layout constraints.
- Existing icon package and asset conventions.

Record what can be reused and what is genuinely missing. Avoid duplicating a component because its current API is inconvenient; improve or wrap it when in scope.

## Token categories
Use semantic tokens rather than hard-coded colors scattered across components:
- Surface: page, panel, elevated panel, canvas, node, overlay.
- Text: primary, secondary, muted, inverse, disabled.
- Border: default, subtle, strong, focus.
- Action: primary, secondary, danger, quiet.
- Status: neutral, info, success, warning, error, blocked, running.
- Workflow: node category, selected node, valid connection, invalid connection, edge label.
- Layout: spacing scale, radius scale, shadow/elevation, z-index layers.
- Motion: duration, easing, reduced-motion fallback.

Token names should describe purpose, not a particular hue. Ensure status remains distinguishable in grayscale and with common color-vision deficiencies.

## Typography and Thai content
- Choose fonts already available in the product unless a font change is justified.
- Test actual Thai copy, including long compound phrases, numbers, punctuation, and mixed Thai/English technical terms.
- Use comfortable line-height and avoid clipping marks above/below Thai characters.
- Do not use tiny text for essential instructions or node labels.
- Prefer concise action labels and short helper text. Put detailed explanation behind contextual help.
- Test browser zoom and narrow panels; do not assume Latin text metrics fit Thai.

## Layout and visual hierarchy
- Establish a clear primary task and one obvious primary action per context.
- Use whitespace and alignment to group related information instead of adding more borders and cards.
- Keep navigation, page title, job identity, workflow status, and primary actions consistently positioned.
- Reserve strong color and elevation for meaningful emphasis.
- Keep dense operational details (IDs, timestamps, raw errors) secondary but discoverable.

## Component states
For each reusable interactive component, specify:
- Default, hover, focus-visible, active, selected, disabled.
- Loading and asynchronous pending state.
- Success, warning, error, and blocked state where relevant.
- Empty state and validation feedback.
- Keyboard interaction and accessible name.

## Quality review
Review at minimum the target desktop viewport and one smaller viewport. Check Thai wrapping and overflow, long node names and values, focus visibility and contrast, popover/dialog/tooltips layering, scroll behavior, reduced-motion behavior, and consistency with the existing app rather than a standalone mockup.
