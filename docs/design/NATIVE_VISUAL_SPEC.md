# Chemistry Studio native visual specification

## Identity

The brand is a molecular C: one open, substantial bond path with two terminal atoms and a smaller atom across the opening. It joins the app’s initial with molecular connectivity. The open center remains the dominant shape at small sizes; no flask, text, formula, predicted property, or success badge is part of the mark.

The palette uses a navy base (`#10283D`–`#234562`), a pale blue bond (`#DFEEFF`–`#B1D0FF`), and mint terminal atoms (`#72D8C3`, `#8CE5D1`). Keep the core geometry and colors consistent in light and dark interfaces. The navy tile provides its own contrast on both surfaces.

`apps/studio-web/public/brand/chemistry-studio.svg` is the canonical 1024 × 1024 precomposed master for the local app bundle. The tile occupies 864 × 864 px, inset 80 px. Its rounded silhouette and transparent exterior suit a legacy ICNS export. This is not an Icon Composer layer: a future Icon Composer package should use an opaque, unmasked background layer and separate foreground geometry so the system can apply masking and material effects.

`BrandMark` mirrors the master’s 64-unit geometry. API: `size?: number | string` (default 32), `className?: string`, `label?: string`. Supply a label when the mark stands alone. Omit the label beside “Chemistry Studio” to avoid repeating the accessible name. Keep the aspect ratio square. Do not add another background tile, border, spinner, or independent color filter around it.

## Illustration system

Every `ChemistryArt` illustration uses the same 240 × 160 composition, surface-colored panels, blue/teal accents, rounded bonds, and a soft, low-contrast background. It remains decorative (`aria-hidden`, nonfocusable). Its meaning must also appear in the adjacent heading or action label.

| Kind | Subject | Intended context |
| --- | --- | --- |
| `molecule` | Dimensional atom-and-bond cluster with a quiet orbit guide | Begin a molecular calculation |
| `research` | Molecular source card and magnifier | Research and examine evidence |
| `improve` | Formulation controls beside a connected structure | Adjust a formulation; no promise of improvement |
| `match` | Two source structures and a comparison link | Compare reference and candidate |
| `sources` | Layered records and an interlocking reference link | Read or attach sources; no verified-evidence checkmark |
| `experiment` | A manually operated flask, pipette, sample rack and stand | Plan or record a physical experiment |

These are generic illustrations. Never substitute them for a molecule drawing derived from a saved calculation, a measured chart, a specimen photograph, an evidence badge, or an execution status.

## Motion contract

No SVG contains a timer, SMIL animation, or JavaScript animation. Root CSS controls motion through these hooks: `.cs-art__subject`, `.cs-art__back`, `.cs-art__backdrop`, `.cs-art__orbit`, `.cs-art__detail`, `.cs-art__spark`, `.cs-brand-logo__bonds`, `.cs-brand-logo__atom`. Each illustration also exposes `.cs-chemistry-art--<kind>` and `data-art`.

Use a brief entrance or a small focus/hover response where it supports an action. Avoid persistent floating, rotating molecules, repeated bubbling, or motion in the sidebar. A loading indicator may use separate controlled motion while the real operation is pending; preserve the written loading status. Under `prefers-reduced-motion: reduce`, all decorative art remains static and visible. No task may wait for an animation to finish.

## Review criteria

- Inspect the icon at 16, 32, 64, 256, and 1024 px on light and dark surfaces. The open C and terminal atom must remain separate; no stroke or atom may clip.
- Inspect all six illustrations at their actual card sizes on desktop and 390 px mobile. No art may push the text or primary action outside the viewport.
- Check that decorative SVGs add no spoken labels or focus stops and a standalone branded image has a useful accessible name.
- With reduced motion enabled, verify static visible art and usable actions; do not infer reduced-motion support solely from the presence of a media query.

## Sources applied

[Apple Human Interface Guidelines: App icons](https://developer.apple.com/design/human-interface-guidelines/app-icons) informed the simple central metaphor, limited large shapes, consistent identity, vector master, and small-size review. Its current layer guidance also explains the distinction between this precomposed ICNS asset and future unmasked Icon Composer layers.

[Apple Human Interface Guidelines: Motion](https://developer.apple.com/design/human-interface-guidelines/motion) informed brief, purposeful responses that never delay interaction and the decision to avoid habitual decorative motion.

[Apple Reduced Motion evaluation criteria](https://developer.apple.com/help/app-store-connect/manage-app-accessibility/reduced-motion-evaluation-criteria/) informed the static decorative alternative and explicit review of spinning, scaling, parallax, and ongoing motion. These are design requirements, not a claim of platform certification.

## Native launch and interaction implementation

The titlebar reserves40px for macOS window controls and a draggable title strip.
A navy launch surface pairs the brand illustration with real startup phases:
Workspace, Research library, Prepare and Open Studio. A phase is marked complete
only after the native runtime advances beyond it. There is no artificial
percentage or minimum animation wait. Errors stop polling, keep diagnostics in
a disclosure, and offer an explicit retry. The workspace opens as soon as the
native service reports ready and verifies its same-origin interface.

The launch mark draws once over850ms, with a brief terminal-atom appearance.
Content enters over320ms with an8px translation; creation sheets enter over260ms.
Cards move at most3px on hover, and active buttons compress slightly. Illustrations
stay still during ordinary work; only a real pending operation runs the molecular
loader. Reduced Motion removes animation and transitions while retaining all
status labels, artwork and controls. No action waits for a transition.
