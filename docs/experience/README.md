# Interactive Field Guide

A standalone, dependency-free interactive tour of VinaStudio.

**Online:** <https://hubehero.github.io/VinaStudio/experience/>

GitHub repository pages show HTML source rather than executing it; the Pages URL
renders the actual interactive guide.

## Open it

From the repository root:

```bash
python -m http.server 8000
# http://127.0.0.1:8000/docs/experience/
```

Or open `docs/experience/index.html` directly. The page uses only local CSS and
JavaScript; it does not fetch fonts, models or remote data.

## What is inside

- **Hero**: animated ambient particle field, live status console, quick stats.
- **Pipeline**: four clickable stages from preparation to review.
- **Architecture**: four runtime layers with dependency details.
- **Preparation lab**: switch between ligand and receptor preparation steps.
- **Docking console**: scoring-function selection and a protocol builder. It
  produces a copyable summary; it never pretends to run a real docking job.
- **Job lifecycle**: a playable sequence for request → spawn → compute → stream
  → settle/cancel.
- **Catalog graph**: clickable molecules, files, Studies, collections and
  libraries.
- **Validation and boundaries**: actual 1IEP/open-set/PoseBusters numbers with
  scope caveats.
- **Command palette**: `Ctrl/Cmd+K` or `/` to jump to sections and documents.

## Design and accessibility

- Modern dark visual system with a restrained cyberpunk HUD accent.
- Cascading reading flow, expo-out motion, no autoplay that blocks reading.
- `prefers-reduced-motion` disables ambient motion.
- The **静默** control pauses the particle field and decorative animation.
- Semantic sections, visible focus states, keyboard-operable controls.
- Mobile layout at 390 px; reduced-motion layout is static but complete.
- The page is intentionally standalone; production docs should link here rather
  than copying the HTML into release notes.

## Source of truth

Content is a guided explanation, not a second specification. Behaviour is
defined by the code and by:

- [`../STRUCTURE.zh-CN.md`](../STRUCTURE.zh-CN.md)
- [`../ARCHITECTURE.zh-CN.md`](../ARCHITECTURE.zh-CN.md)
- [`../ACADEMIC_VALIDATION.zh-CN.md`](../ACADEMIC_VALIDATION.zh-CN.md)
- [`../MOLECULE_CATALOG.zh-CN.md`](../MOLECULE_CATALOG.zh-CN.md)

If a number or path changes, update this page and the source document together.
