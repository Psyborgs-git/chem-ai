# Focused Mac research workspace

The workspace prioritizes the next useful action over a catalogue of features.
This pass changes the live application, its navigation, shared styling and chat.

## Navigation and task entry

- Five primary destinations remain visible: Home, Projects, Notebooks, Research
  library and Local learning. Less frequent destinations remain under More tools;
  an active secondary destination reveals its group.
- Home exposes direct paths to ask the agent, find papers, start a notebook,
  train a model and explore a molecule. These open the relevant existing flow;
  navigation never starts inference, downloads or training.
- Command-K finds destinations and owned projects, tasks, notes, sources and
  memories. Choosing a result opens that exact record.
- The local-learning wizard offers common tasks directly. Run size and time
  limit are visible first; specialist parameters remain in Advanced settings.
  The final readiness and scientific approval checks remain authoritative.

## Controls and appearance

- Spacing follows an 8-pixel grid: 8, 16, 24, 32, 40 and 48 pixels. Desktop
  page gutters use 32 pixels and narrow pages use 16. Sections use 24–32,
  primary card insets use 24 (16 on narrow screens), and form/list spacing uses
  8–16. Borders, icon geometry and typography retain their intrinsic sizes.
- SF-first system typography, neutral light/dark content surfaces, quiet
  separators and restrained blue replace the navy cards and tinted navigation.
- Translucency belongs to navigation chrome. Content stays opaque; increased
  contrast and reduced transparency use opaque fallbacks.
- Repeated and toolbar actions use recognizable icons, accessible names and
  tooltips. A primary decision can retain its short text label.
- Native content and agent panels share the existing 40-pixel titlebar inset.

## Chat and motion

The transcript uses official shadcn Message Scroller, Message and Bubble
components. The composer uses Input Group, and tool activity uses Trace.
Existing authenticated app APIs, history, drafts and provider consent remain the
data source. No scripted model or demonstration transport is used.

Motion marks panel entry/exit, route changes, tab/disclosure changes, message
arrival, button presses and actual pending work. It stays brief, does not block
input, and never leaves essential content invisible. Reduced motion removes
spatial and repetitive effects. New message scrolling respects a person reading
earlier content.

## Primary references

- [Apple: Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars)
- [Apple: Layout](https://developer.apple.com/design/human-interface-guidelines/layout)
- [Apple: Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars)
- [Apple: Motion](https://developer.apple.com/design/human-interface-guidelines/motion)
- [Apple: Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility)
- [shadcn: AI Chat](https://ui.shadcn.com/docs/ai-elements/base/chat)
- [NN/g: Progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/)
