# Print Sheet POS

A standalone desktop app for managing patch print orders: browse a product
library of PSD templates, build an order, and composite it onto an A4
master print sheet — either as a print-ready PDF or as an editable
layered PSD. Runs offline from a flash drive, no server, no network calls.

See [PROJECT_INSTRUCTIONS.md](PROJECT_INSTRUCTIONS.md) for the full design
history and decisions behind each feature below.

## Tech stack

- **UI shell:** [pywebview](https://pywebview.flowrl.com/) — a native
  desktop window rendering the plain HTML/CSS/JS frontend in `frontend/`
- **PSD parsing:** [psd-tools](https://psd-tools.readthedocs.io/)
- **Layered PSD writing:** [pytoshop](https://pytoshop.readthedocs.io/)
- **Image compositing:** [Pillow](https://pillow.readthedocs.io/)
- **PDF generation:** [reportlab](https://www.reportlab.com/)
- **Catalog storage:** SQLite (stdlib)
- **Packaging:** [PyInstaller](https://pyinstaller.org/) → a portable
  macOS `.app`

## Features

### Product library

- **Rescan Library** scans a root folder (e.g. `MNP Patch Master List` on
  the flash drive) for `MP-P-<number> - <NAME>` product folders and
  indexes them into a local SQLite catalog (`patch_pos_data/catalog.db`,
  stored on the same drive so it travels with it).
- Each product folder is matched to its compositing source: rectangular
  at `3x2-images/1-image-template.psd`, circular at
  `3x2-images/1-image-template-circular.psd` (or, for a few folders,
  directly at the SKU root). Folders matching neither pattern are
  skipped from the catalog silently.
- **Search/filter/pagination** over the catalog by SKU or name
  (case-insensitive partial match), automatically filtered to the
  order's active template shape once one is picked.
- **Thumbnails:** uses an existing `Product Photo N.jpg` when present;
  otherwise flattens the source PSD into a small preview, cached on disk
  after the first render.
- **Library Info** panel: total products, total size on disk, last scan
  timestamp. **Storage** panel: free/used/total space on the library's
  drive.

### Current Order (cart)

- Pick a template shape (**Rectangular**, 8 slots, or **Circular**, 6
  slots) — locked while the order has items, since a product is always
  one shape or the other.
- Add products with a quantity; quantity drives slot count directly (a
  line with quantity 3 fills 3 slots), summed across all lines.
- **Print Sheet Preview** shows the sheet's numbered slots filling in as
  items are added, with a running `used / cap` counter.
- Exceeding the template's slot cap is rejected with a clear error —
  there's no multi-sheet auto-splitting; one order is one sheet.

### Print sheet generation

Both export paths composite the order's product PSDs onto the master
template's exact slot positions (extracted from the template's Smart
Object transform data), in order:

- Each source PSD is trimmed to its actual artwork (ignoring any
  transparent margin baked into the file) and fit to a **patch box**
  inside its slot — 930×628px inside the 975×675px rectangular slot,
  933px diameter inside the 975×975px circular slot — confirmed against
  the shop's real-world size guides, so printed patches match their
  intended finished size rather than the raw Smart Object placeholder.
- A 5px black inside stroke is drawn around each filled patch box as a
  cut/registration guide. Empty slots stay blank.

**Generate Print Sheet** flattens the result and exports a single,
print-accurate PDF (sized in points from the canvas's 300 DPI). A native
save dialog opens fresh every time — no remembered output folder.

**Export Editable PSD…** is the manual-editing alternative: the same
composite, written as a *layered* `.psd` instead of a flattened PDF —
one independently movable/resizable layer per patch (named
`1-image-template`, etc.), a `Guides` layer with the registration
stroke, and a white `Background` layer. Use it when an order needs a
manual touch-up (nudge, resize, retouch) in Photoshop before printing.
Both actions clear the order on success.

### Error handling

Every state-changing action is wrapped so a failure never crashes the
UI — it's logged to `patch_pos_data/app.log` (alongside the catalog) and
shown as a plain-language in-app banner instead.

### Command-line tool

`python -m patch_pos.cli` runs the compositing engine standalone (master
template + shape + ordered list of source PSDs → PDF), without the
pywebview shell — useful for testing the engine in isolation.

## Getting started

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 main.py
```

For development (tests, packaging):

```bash
.venv/bin/pip install -r requirements-dev.txt
```

## Testing

```bash
.venv/bin/python3 -m pytest tests/unit tests/integration -q   # fast, no browser
.venv/bin/python3 -m pytest tests/e2e -q                      # drives the real frontend in Chrome
.venv/bin/python3 -m pytest tests -q                           # everything
```

- **Unit tests** cover pure functions (slot extraction, trim-and-fit,
  quantity/cap logic) against fixture/mocked PSD data.
- **Integration tests** run the full compositing → PDF/PSD pipeline
  against small checked-in fixture files (never the real flash drive or
  library).
- **E2E tests** (Playwright) drive the actual `frontend/` HTML/JS in a
  real browser against the real `Api` backend, covering the rectangular,
  circular, over-cap, and editable-PSD-export flows end to end.

## Packaging

```bash
.venv/bin/pyinstaller build.spec --noconfirm
```

Produces `dist/PrintSheetPOS.app`, a portable, unsigned macOS app that
runs directly off a flash drive (right-click → Open on first launch on
a new Mac, since it isn't notarized).

## Project structure

```
patch_pos/
  app.py           pywebview shell + Api bridge exposed to the frontend
  library.py       flash-drive folder scanning
  catalog.py       SQLite catalog index
  order.py         in-memory Current Order (cart) state
  slots.py         master template slot-layout extraction (Smart Object Trnf data)
  compositor.py    trim-and-fit + composite onto the master template's A4 canvas
  psd_export.py    layered, editable PSD export
  pdf_export.py    flattened, print-accurate PDF export
  thumbnails.py    product-grid thumbnails
  logging_setup.py error/crash log file
  cli.py           standalone CLI for the compositing engine
frontend/          plain HTML/CSS/JS UI rendered inside the pywebview window
tests/
  unit/            pure-function tests
  integration/     full-pipeline tests against fixture files
  e2e/             Playwright tests driving the real frontend
  fixtures/        small stand-in PSD templates/sources (not the real library)
```
