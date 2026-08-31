# Print Sheet POS — Project Instructions

## 1. What this is

A standalone desktop application (not a hosted web app) for managing print
orders that get composited onto A4 print sheets from a library of PSD
product templates. It runs from a flash drive, works offline, and should
run on macOS first, with Windows portability kept in mind for later.

Read this whole file before writing any code. Where something is marked
**ASSUMPTION**, confirm it with the user before building around it — don't
silently lock in a guess.

---

## 2. Tech stack (decided)

- **Language:** Python (backend/business logic)
- **UI shell:** `pywebview` — renders an HTML/CSS/JS frontend inside a
  native desktop window. No server, no browser tab, no network calls.
- **Frontend:** plain HTML/CSS/JS (or Vue 3 if preferred later) rendered
  inside the pywebview window
- **PSD parsing:** `psd-tools`
- **Image compositing/resizing:** `Pillow`
- **PDF generation:** `reportlab` (preferred for print-accurate DPI control)
  or Pillow's PDF export
- **Packaging:** PyInstaller (or `briefcase`) → produces a portable macOS
  `.app` bundle that runs directly off the flash drive, no install step
- **Explicitly NOT using:** Laravel/PHP, live Photoshop scripting/automation
  (the "Photoshop: Connected" badge in the mockup is a UI label only — all
  compositing is done in Python/Pillow, not real Photoshop)

Windows portability note: the same codebase should work on Windows via
pywebview + WebView2, but packaging must be rebuilt on a Windows machine
when that's needed. Don't add Mac-only shortcuts to the code.

---

## 3. Master print templates (already inspected, exact values below)

There is a single master layout PSD (e.g. `A4-PATCH-TEMPLATE-NO_MIRROR.psd`)
read from the flash drive. It contains two groups, each with pre-positioned
Smart Object placeholder layers:

**Canvas:** 2480 x 3508 px (A4 @ 300 DPI)

**Group `RECTANGLES`** — 8 slots, 2 columns x 4 rows, each slot 975 x 675 px:

| Layer name | x | y | w | h |
|---|---|---|---|---|
| 1-image-template | 164.0 | 167.0 | 975 | 675 |
| 2-image-template | 1337.0 | 166.5 | 975 | 675 |
| 3-image-template | 163.5 | 1006.0 | 975 | 675 |
| 4-image-template | 1336.5 | 1006.0 | 975 | 675 |
| 5-image-template | 163.5 | 1845.5 | 975 | 675 |
| 6-image-template | 1336.5 | 1845.5 | 975 | 675 |
| 7-image-template | 163.5 | 2684.6 | 975 | 675 |
| 8-image-template | 1336.5 | 2685.2 | 975 | 675 |

**Group `ROUNDS`** — 6 slots, 2 columns x 3 rows, each slot 975 x 975 px:

| Layer name | x | y | w | h |
|---|---|---|---|---|
| 1-image-template-circular | 161.5 | 168.5 | 975 | 975 |
| 2-image-template-circular | 1334.5 | 168.5 | 975 | 975 |
| 3-image-template-circular | 161.5 | 1274.5 | 975 | 975 |
| 4-image-template-circular | 1334.5 | 1274.5 | 975 | 975 |
| 5-image-template-circular | 161.5 | 2380.5 | 975 | 975 |
| 6-image-template-circular | 1334.5 | 2381.5 | 975 | 975 |

Notes:
- **Confirmed real path and file to use:**
  `/Volumes/MP-JLS/MP Templates/PATCH/A4-PATCH-TEMPLATE-NO MIRROR.psd`
  (note: space, not underscore — differs slightly from this doc's example
  filename above). The same folder also contains
  `A4-PATCH-TEMPLATE-r01.psd`, which is a different file — **decision:**
  not used; the compositing engine reads `...NO MIRROR.psd` specifically.
- Circular source PSDs are already pre-shaped/cropped to fit 975x975 —
  **no masking/clipping needed** when compositing them.
- These coordinates were extracted from the `Trnf` transform descriptor
  inside each Smart Object layer's `SoLE`/`SoLd` tagged block (not the
  layer's outer `bbox`, which reads as zero for these particular layers).
  Use the same extraction approach for any other master templates added
  later — see the extraction snippet in Appendix A.
- Slot count sets the per-sheet item cap: **8 for rectangular, 6 for
  circular.** If the user's order exceeds the cap for the selected
  template, **show an error** — do not auto-split across multiple sheets
  (multi-sheet auto-generation is explicitly out of scope for v1).

---

## 4. Product library

- On first run / on demand ("Rescan Library"), scan a root directory
  (located on the flash drive or an external path the user selects) for
  SKU folders.
- **CONFIRMED (inspected real library at `/Volumes/MP-JLS/MNP Patch Master
  List`, 799 product folders):**
  - Folder naming: `MP-P-<number> - <NAME>`. Dash spacing is inconsistent
    (some folders have no spaces around the dash, at least one has a
    trailing space in the folder name) — the SKU-extraction logic must be
    lenient about this, not regex-strict.
  - Rectangular source: `<SKU folder>/3x2-images/1-image-template.psd`.
  - Circular source: usually
    `<SKU folder>/3x2-images/1-image-template-circular.psd`, but some
    folders (e.g. `MP-P-760 - BTS LOGO 3 CIRCULAR`) put it directly at the
    SKU folder root instead, with no `3x2-images` subfolder. The scanner
    must check both locations.
  - No SKU folder has both a rectangular and a circular source — each
    product is one shape or the other. This means product shape doesn't
    need to be separately tracked/guessed; it falls out of which file
    exists. The operator knows which products are round vs. rectangular
    and adds them to the matching order accordingly — the app does not
    need to enforce or auto-detect shape compatibility beyond template
    slot geometry.
  - Real source PSDs' **canvas** is always sized to the exact slot
    dimensions (975x675 for rect, 975x975 for circular) — verified by
    sampling dozens of files. But the actual **content** within that
    canvas often doesn't fill it: many files carry a baked-in
    transparent margin of varying size (not a fixed constant — differs
    per file, e.g. 24px on one product, 21px on another), while a few
    are genuinely full-bleed already. Left uncorrected, this shows as an
    unwanted white gap between the patch and its slot boundary (and the
    stroke — see below). See "Decision — trim and fit" below.
  - ~11% of folders (85/799) don't have the expected file. Most of those
    are legitimately circular-only products (fine). But ~40 use an older,
    different structure entirely (`PATCH-PHOTO-TEMPLATE-CUSTOM
    CUTOUT.psd` + a `.ai` file, no `1-image-template*.psd` at all — e.g.
    `MP-P-449 - CAPTAIN AMERICA`, the `MP-P-607`–`621` range). A few
    others are just empty/broken folders (e.g. `MP-P-161`, `MP-P-514`).
  - **Decision:** folders matching neither the rect nor circular
    `1-image-template*.psd` pattern are **skipped silently** from the
    catalog — they don't appear in the product grid. No in-app "broken
    products" report for v1.
  - Most product folders also contain a ready-made `Product Photo
    N.jpg` (either loose in the folder or inside a
    `PATCH-PHOTO-TEMPLATE-assets/` subfolder) — a marketing photo,
    separate from the compositing-source PSD.
- **Decision — thumbnails:** use the existing `Product Photo N.jpg` for
  the product-grid thumbnail when present (much cheaper than flattening a
  PSD). Fall back to flattening the source PSD into a low-res preview only
  when no `Product Photo` jpg exists in the folder.
- **Decision — trim and fit (supersedes an earlier "reject on mismatch"
  decision):** confirmed against real generated output that source PSDs'
  baked-in margins (see above) must not be left in — every filled slot
  should be edge-to-edge with no gap. The compositor crops each flattened
  source to its actual content bounding box (via alpha, so a solid
  black-background patch is never mistaken for "empty" — only a fully
  transparent source is) and stretches that trimmed content to exactly
  fill the slot. A handful of rect sources have a very slightly
  non-symmetric margin, so the stretch isn't always perfectly
  aspect-preserving, but the distortion is negligible for these
  logo/text patches — full-bleed with no gap took priority. There is
  still no in-app "edit source" / "open in editor" feature; a genuinely
  broken source (fully blank/transparent) is a hard error, fixed
  out-of-band directly in Photoshop on the flash drive.
- Build a local catalog/index (see storage below) recording at minimum:
  SKU/product code, display name, source PSD path, and a thumbnail image
  path (per the decision above).
- Support: search by product code/name (partial match), category filter,
  sort order, pagination — matching the mockup's "New Order" product grid.
- "Library Info" panel: total products, total size on disk, last scan
  timestamp.
- "Storage" panel: free/used space on the storage device the library
  lives on.

---

## 5. Order / cart workflow

This replaces the earlier "select up to 8 files directly" flow with an
order-based flow, matching the mockup's "Current Order" panel:

1. User browses/searches the product library and adds products to the
   **Current Order** (quantity per product, like a cart).
2. Order shows: product thumbnail, code, quantity (+/-), total items.
   - **Decision — pricing dropped from v1.** There is no pricing model
     yet (no cost per template/POS defined). Unit price / line total /
     order total are removed from the order UI for now. The order tracks
     product + quantity only. Pricing can be added later once a real
     pricing model exists.
   - **Decision — quantity drives slot count.** A line quantity of N
     means that product's image is composited into N separate slots on
     the sheet (not just a cost multiplier). Total slots used = sum of
     all line quantities, checked against the template's cap. This also
     means an order is inherently capped at one sheet's worth of slots
     (8 or 6) — see point 5.
3. **Decision — template scope: per-order.** Each order has its own
   selected template (rectangular or circular), not a global app-wide
   setting. Since products are shape-specific (see §4), the operator
   picks products matching the order's chosen template.
4. **Print Sheet Preview** panel shows the current sheet's slots filled in
   order as items are added (matching mockup: numbered slots, empty slots
   shown with a "+" placeholder, "Used: X / Y slots" counter).
5. If total items (summed quantity) in the order exceed the selected
   template's slot count, **show an error** (do not auto-generate
   additional sheets in v1). Because quantity drives slot count and
   over-cap is a hard error, an order and a sheet are effectively the
   same thing in v1 — there's no concept of one order spanning multiple
   sheets.
6. **Generate Print Sheet** button: flattens each selected product's PSD
   and composites it onto the master template's A4 canvas at its slot's
   exact position (source PSDs are already sized to match slot dimensions
   in practice — see §4). Exports a single PDF.
7. **Decision — output folder: blank save dialog every time.** This
   confirms the earlier decision over the mockup's persistent "Output
   Folder" field — no default output folder is remembered. Every
   "Generate Print Sheet" click opens a native save-file dialog with no
   pre-filled path. The mockup's "Output Folder" field is dropped from
   the UI for v1 (not built as a persistent/settable field).

---

## 6. Other panels from the mockup (lower priority — build after core flow works)

- **Orders / History:** list of past generated orders/print sheets.
- **Reports:** any aggregate reporting — scope not yet defined, treat as
  stub/placeholder until specified.
- **Templates:** management view for the master layout PSDs (rectangular/
  circular) — likely where a user could add more layout templates in the
  future. Not required for v1 beyond reading the two known templates.
- **Settings:** app-level config (paths, defaults). Scope not yet defined.
- Machine name / "Photoshop: Connected" status badges are cosmetic only
  for v1 — no real Photoshop integration, no multi-machine sync logic
  unless separately specified.

**Decision — error/crash surfacing:** this is a packaged desktop app with
no visible terminal/console for the end user. Errors write to a log file
(alongside the catalog DB on the flash drive, see §8) for later
debugging, AND show a plain-language in-app error banner/message so the
operator isn't left staring at a frozen or silently-failed UI.

---

## 7. Explicit non-goals for v1

- No real payment processing or POS financial features
- No live Photoshop automation/scripting
- No automatic multi-sheet splitting (show an error instead)
- No network/server component — everything runs locally in one process

---

## 8. Suggested build order

1. ~~Confirm the two open items flagged above~~ — resolved, see §4 and
   §5.7.
2. Core PSD compositing engine: given a list of up to N source PSDs (in
   order) + a chosen master template (rect/circular), produce the final
   A4 PDF. Build and test this in isolation first (CLI/script), since it's
   the highest-risk technical piece.
3. Product library scan + local catalog storage. **Decision:** a
   persistent local index (SQLite) is still built even though there's no
   pricing/POS yet — it exists purely to make search/filter/pagination
   fast over 799+ product folders without rescanning the flash drive on
   every keystroke; it does not require a price field. **Decision:** the
   index file lives on the flash drive itself (e.g.
   `/Volumes/MP-JLS/patch_pos_data/catalog.db`), not on the host machine,
   so the catalog travels with the drive across machines and any machine
   that plugs it in sees the same up-to-date index without rescanning.
   Order history (§6) reuses the same storage location.
4. pywebview shell + basic window, wire up native folder-select and
   save-file dialogs.
5. Frontend: product grid (search/filter/pagination) → Current Order cart
   → Print Sheet Preview → Generate button → save dialog.
6. Packaging: PyInstaller build to a portable macOS `.app`, test running
   directly from a flash drive on a clean machine. **Decision:** left
   unsigned/not notarized for v1 (no Apple Developer account assumed) —
   users will need to right-click > Open (or approve in System Settings)
   the first time on each new Mac. Revisit if distributed beyond the
   user's own machines.

---

## 9. Testing requirements (strict — non-negotiable)

Every phase in Section 8 must ship with tests before it's considered done.
Do not move to the next phase with failing or missing tests for the
current one.

### 9.1 Unit tests
- Cover every pure function independently: slot-coordinate extraction,
  trim-and-fit behavior (off-size/margined sources stretched to fill the
  slot, a fully transparent source is still a hard error — see §4),
  filename/sequence labeling (`1-image-template.pdf` ... up to the
  template's slot cap), SKU partial-match search logic, quantity-to-slot
  expansion (a line quantity of N occupies N slots — see §5), and the
  8-slot/6-slot cap check against summed quantity (including the "reject
  and error" path when exceeded).
- Each unit test covers one behavior. Include edge cases explicitly:
  empty selection, exactly at the cap, one over the cap, empty search
  query, search with zero matches, malformed/corrupt PSD input, a
  product folder missing its expected subfolder/file.
- Mock the filesystem and PSD library calls in unit tests — they should
  not depend on the real flash drive, real template PSDs, or real product
  library being present. Use small fixture PSDs or mocked `psd-tools`
  objects instead.
- Run on every change to the function under test. No merging/continuing
  with a red unit test suite.

### 9.2 Feature (integration) tests
- Test each feature as a whole slice, with real fixture files (a small
  real PSD template with known slot coordinates, checked into a
  `tests/fixtures/` folder — not the production template, a minimal
  stand-in with the same structure):
  - Library scan → catalog produced matches expected product list
  - Search/filter/pagination returns expected results against the fixture
    catalog
  - Add-to-order / quantity change / remove updates order state and
    totals correctly
  - Template selection (rect vs circular) correctly swaps the active slot
    map and cap
  - Generate Print Sheet against a fixture order produces a PDF with the
    expected number of pages, page size, and images in the expected
    positions (verify by re-opening the generated PDF/image and checking
    pixel regions or embedded image count — not just "a file was created")
  - Exceeding the slot cap surfaces the error path, does not generate a
    partial/corrupt PDF
- These run against the local filesystem in a temp directory created and
  torn down per test run — never against the user's real flash drive,
  real product library, or real output folder.

### 9.3 End-to-end (E2E) tests
- **Decision:** use Playwright driving the frontend HTML/JS/CSS directly
  in a headless browser, with the Python backend calls mocked/stubbed
  through the same bridge interface pywebview exposes to the frontend —
  rather than automating the actual native pywebview window, which is
  more brittle to drive. Cover the full real workflow: launch app → scan
  library → search → add products to order → pick template → generate
  print sheet → confirm save dialog invoked with a correct file → confirm
  output PDF exists and is valid.
- At minimum one E2E test for the rectangular flow and one for the
  circular flow, plus one for the over-cap error flow.
- E2E tests must run against a packaged or near-packaged build at least
  once before any release/handoff milestone, not only against the raw
  dev environment — packaging (PyInstaller) has broken working code
  before and must be caught before the user is handed a build.

### 9.4 What "done" means
A feature is not complete until: unit tests pass, its integration test
passes, and (for user-facing flows) the relevant E2E path passes. Report
test results explicitly when marking work as done — do not report a
feature as finished based on manual eyeballing alone.

---

## 10. Change safety rules (strict — non-negotiable)

The application must never be left in a broken or worse state by a change,
including changes made by Claude itself during future sessions.

- **Never make a change that isn't scoped to what was asked.** Do not
  refactor, rename, delete, or "clean up" unrelated code, files, or
  features while implementing something else. If a wider refactor seems
  genuinely necessary, stop and explain why before doing it — don't do it
  unprompted.
- **Full test suite must pass before and after every change.** Run the
  full unit + feature test suite before starting a change (to confirm the
  baseline is green) and again after (to confirm nothing regressed). If
  the baseline is already red, fix or flag that first — don't build on
  top of a known-broken state.
- **Never delete anything on the flash drive, full stop** — not just the
  master template PSDs, product library source files, or generated
  output, but anything else living on it (the drive also holds unrelated
  personal/client content outside this app's scope). No code change, test
  run, debugging session, or cleanup task may delete or overwrite a file
  on the flash drive as a side effect. Tests must only ever touch fixture
  copies in a temp/test directory, never the real drive. The only writes
  the app itself makes to the drive are the catalog index/order-history
  DB and generated PDF output the user explicitly saves — never a
  deletion.
- **Destructive operations require an explicit, isolated confirmation
  step** — anything that deletes files, overwrites the catalog/database,
  or wipes app state must be a distinct, clearly-labeled action, never a
  silent side effect of an unrelated feature or bug fix.
- **No breaking changes to already-working core flows** (library scan,
  search, order/cart, print sheet generation, save) without explicit
  sign-off. If a change requires altering one of these, call it out
  clearly as a breaking change before making it, not after.
- **Use version control discipline:** commit working, tested states in
  small increments. Never leave the working tree in a state where the app
  doesn't run. If an experiment fails, roll back rather than leaving
  half-applied changes in place.
- **When modifying existing code, prefer the smallest correct change**
  over a rewrite, unless a rewrite was specifically requested. A large,
  hard-to-review diff is itself a risk to treat carefully.

---

## Appendix A — PSD slot coordinate extraction (Python)

```python
from psd_tools import PSDImage
from psd_tools.constants import Tag

def get_transform(layer):
    block = layer.tagged_blocks.get(Tag.SMART_OBJECT_LAYER_DATA2)
    if block is None:
        block = layer.tagged_blocks.get(Tag.SMART_OBJECT_LAYER_DATA1)
    d = block.data.data
    trnf = [float(v) for v in d[b'Trnf']]
    xs, ys = trnf[0::2], trnf[1::2]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)  # x, y, w, h

psd = PSDImage.open('A4-PATCH-TEMPLATE-NO_MIRROR.psd')
for group_name in ['RECTANGLES', 'ROUNDS']:
    group = [l for l in psd if l.name == group_name][0]
    for layer in group:
        print(layer.name, get_transform(layer))
```
