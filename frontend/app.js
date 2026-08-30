const PAGE_SIZE = 24;

const state = {
  query: "",
  page: 0,
  totalProducts: 0,
  order: { template_shape: null, lines: [], total_items: 0, cap: null, over_cap: false },
  thumbCache: new Map(),
};

function api() {
  return window.pywebview.api;
}

function formatBytes(bytes) {
  if (bytes == null) return "-";
  const gb = bytes / 1e9;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / 1e6).toFixed(0)} MB`;
}

function showError(message) {
  const el = document.getElementById("error-banner");
  el.textContent = message;
  el.hidden = false;
  document.getElementById("success-banner").hidden = true;
}

function showSuccess(message) {
  const el = document.getElementById("success-banner");
  el.textContent = message;
  el.hidden = false;
  document.getElementById("error-banner").hidden = true;
}

function clearBanners() {
  document.getElementById("error-banner").hidden = true;
  document.getElementById("success-banner").hidden = true;
}

async function getThumbnail(folderPath) {
  if (state.thumbCache.has(folderPath)) return state.thumbCache.get(folderPath);
  const result = await api().get_thumbnail(folderPath);
  const url = result.ok ? result.data_url : null;
  state.thumbCache.set(folderPath, url);
  return url;
}

// Fetches every not-yet-cached path in a single bridge round-trip instead
// of one call per card -- see Api.get_thumbnails' docstring for why this
// matters (this was the main source of the grid feeling slow to load).
async function prefetchThumbnails(folderPaths) {
  const uncached = folderPaths.filter((path) => !state.thumbCache.has(path));
  if (uncached.length === 0) return;
  const result = await api().get_thumbnails(uncached);
  if (!result.ok) return;
  for (const path of uncached) {
    state.thumbCache.set(path, result.thumbnails[path] ?? null);
  }
}

// -- library setup -----------------------------------------------------

async function selectLibraryFolder() {
  const path = await api().select_library_folder();
  if (!path) return;
  await rescanLibrary(path);
}

async function rescanLibrary(rootPath) {
  const result = await api().rescan_library(rootPath ?? null);
  if (!result.ok) {
    showError(result.error);
    return;
  }
  document.getElementById("no-library-view").hidden = true;
  document.getElementById("app-view").hidden = false;
  document.getElementById("rescan-btn").disabled = false;
  document.getElementById("library-summary").textContent = `${result.total_products} products in library`;
  clearBanners();
  await Promise.all([refreshLibraryInfo(), refreshStorage(), refreshOrder()]);
  await runSearch();
}

// -- library info / storage panels --------------------------------------

async function refreshLibraryInfo() {
  const info = await api().get_library_info();
  const body = document.getElementById("library-info-body");
  if (!info.ok) {
    body.textContent = info.error;
    return;
  }
  body.innerHTML = `
    <div>Total products: ${info.total_products}</div>
    <div>Total size: ${formatBytes(info.total_size_bytes)}</div>
    <div>Last scan: ${info.last_scan_at ? new Date(info.last_scan_at).toLocaleString() : "-"}</div>
  `;
}

async function refreshStorage() {
  const usage = await api().get_disk_usage();
  const body = document.getElementById("storage-body");
  if (!usage.ok) {
    body.textContent = usage.error;
    return;
  }
  body.innerHTML = `
    <div>Free: ${formatBytes(usage.free_bytes)}</div>
    <div>Used: ${formatBytes(usage.used_bytes)}</div>
    <div>Total: ${formatBytes(usage.total_bytes)}</div>
  `;
}

// -- template picker -----------------------------------------------------

function renderTemplatePicker() {
  const locked = state.order.lines.length > 0;
  document.querySelectorAll(".template-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.shape === state.order.template_shape);
    btn.disabled = locked;
  });
  document.getElementById("template-locked-note").hidden = !locked;
}

async function pickTemplate(shape) {
  const result = await api().set_order_template(shape);
  if (!result.ok) {
    showError(result.error);
    return;
  }
  state.order = result;
  state.page = 0;
  renderTemplatePicker();
  renderOrder();
  renderPreview();
  await runSearch();
}

// -- product grid / search ------------------------------------------------

async function runSearch() {
  const result = await api().search_products(
    state.query,
    state.order.template_shape,
    "sku",
    PAGE_SIZE,
    state.page * PAGE_SIZE
  );
  if (!result.ok) {
    showError(result.error);
    return;
  }
  state.totalProducts = result.total;
  await renderProductGrid(result.products);
  renderPagination();
}

async function renderProductGrid(products) {
  await prefetchThumbnails(products.map((p) => p.folder_path));

  const grid = document.getElementById("product-grid");
  grid.innerHTML = "";
  const canAdd = state.order.template_shape !== null;

  for (const product of products) {
    const card = document.createElement("div");
    card.className = "product-card";

    const img = document.createElement("div");
    img.className = "thumb-placeholder";
    card.appendChild(img);
    getThumbnail(product.folder_path).then((url) => {
      if (url) {
        const imgEl = document.createElement("img");
        imgEl.src = url;
        card.replaceChild(imgEl, img);
      }
    });

    const body = document.createElement("div");
    body.className = "card-body";
    body.innerHTML = `<div class="code">${product.sku}</div><div class="name">${product.name}</div>`;

    const addBtn = document.createElement("button");
    addBtn.textContent = canAdd ? "Add" : "Pick a template first";
    addBtn.disabled = !canAdd;
    addBtn.addEventListener("click", () => addToOrder(product.folder_path));
    body.appendChild(addBtn);

    card.appendChild(body);
    grid.appendChild(card);
  }
}

function renderPagination() {
  const totalPages = Math.max(1, Math.ceil(state.totalProducts / PAGE_SIZE));
  const currentPage = state.page + 1;
  document.getElementById("page-info").textContent = `Page ${currentPage} of ${totalPages} (${state.totalProducts} products)`;
  document.getElementById("prev-page-btn").disabled = state.page <= 0;
  document.getElementById("next-page-btn").disabled = currentPage >= totalPages;
}

// -- current order ---------------------------------------------------------

async function addToOrder(folderPath) {
  const result = await api().add_to_order(folderPath, 1);
  if (!result.ok) {
    showError(result.error);
    return;
  }
  clearBanners();
  state.order = result;
  renderTemplatePicker();
  renderOrder();
  renderPreview();
}

async function setQuantity(folderPath, quantity) {
  const result = await api().set_order_quantity(folderPath, quantity);
  if (!result.ok) {
    showError(result.error);
    return;
  }
  state.order = result;
  renderTemplatePicker();
  renderOrder();
  renderPreview();
  if (state.order.lines.length === 0) await runSearch(); // grid Add buttons may need re-checking
}

async function removeLine(folderPath) {
  const result = await api().remove_from_order(folderPath);
  if (!result.ok) {
    showError(result.error);
    return;
  }
  state.order = result;
  renderTemplatePicker();
  renderOrder();
  renderPreview();
}

function renderOrder() {
  const container = document.getElementById("order-lines");
  container.innerHTML = "";
  for (const line of state.order.lines) {
    const row = document.createElement("div");
    row.className = "order-line";
    row.innerHTML = `
      <span class="name">${line.sku} - ${line.name}</span>
      <div class="qty-controls">
        <button data-action="dec">-</button>
        <span>${line.quantity}</span>
        <button data-action="inc">+</button>
      </div>
      <button class="remove-btn" data-action="remove">&times;</button>
    `;
    row.querySelector('[data-action="dec"]').addEventListener("click", () =>
      setQuantity(line.folder_path, line.quantity - 1)
    );
    row.querySelector('[data-action="inc"]').addEventListener("click", () =>
      setQuantity(line.folder_path, line.quantity + 1)
    );
    row.querySelector('[data-action="remove"]').addEventListener("click", () => removeLine(line.folder_path));
    container.appendChild(row);
  }

  const totalEl = document.getElementById("order-total");
  if (state.order.cap != null) {
    totalEl.textContent = `${state.order.total_items} / ${state.order.cap} slots`;
    totalEl.style.color = state.order.over_cap ? "#a11" : "";
  } else {
    totalEl.textContent = `${state.order.total_items} item(s) -- pick a template to see slot usage`;
  }

  const generateBtn = document.getElementById("generate-btn");
  generateBtn.disabled = state.order.total_items === 0 || state.order.over_cap;
}

function expandOrderToSlots() {
  const expanded = [];
  for (const line of state.order.lines) {
    for (let i = 0; i < line.quantity; i++) expanded.push(line);
  }
  return expanded;
}

async function renderPreview() {
  const grid = document.getElementById("slot-grid");
  grid.innerHTML = "";
  const usageEl = document.getElementById("slot-usage");

  if (state.order.cap == null) {
    usageEl.textContent = "Pick a template to see the print sheet preview.";
    return;
  }

  const expanded = expandOrderToSlots();
  usageEl.textContent = `Used: ${expanded.length} / ${state.order.cap} slots`;
  usageEl.style.color = state.order.over_cap ? "#a11" : "";

  await prefetchThumbnails(expanded.map((line) => line.folder_path));

  for (let i = 0; i < state.order.cap; i++) {
    const slot = document.createElement("div");
    slot.className = "slot";
    const numberEl = document.createElement("span");
    numberEl.className = "slot-number";
    numberEl.textContent = i + 1;
    slot.appendChild(numberEl);

    const line = expanded[i];
    if (line) {
      slot.classList.add("filled");
      getThumbnail(line.folder_path).then((url) => {
        if (url) slot.style.backgroundImage = `url(${url})`;
      });
    } else {
      const plus = document.createElement("span");
      plus.textContent = "+";
      slot.appendChild(plus);
    }
    grid.appendChild(slot);
  }
}

async function refreshOrder() {
  const result = await api().get_order();
  if (!result.ok) {
    showError(result.error);
    return;
  }
  state.order = result;
  renderTemplatePicker();
  renderOrder();
  renderPreview();
}

// -- generate ---------------------------------------------------------------

async function generatePrintSheet() {
  const btn = document.getElementById("generate-btn");
  btn.disabled = true;
  const result = await api().generate_print_sheet();
  if (!result.ok) {
    showError(result.error);
  } else if (result.cancelled) {
    // user cancelled the save dialog -- no banner, nothing changed
  } else {
    showSuccess(`Saved to ${result.path} (${result.slots_used}/${result.cap} slots used)`);
    await refreshOrder();
    await runSearch();
  }
  btn.disabled = state.order.total_items === 0 || state.order.over_cap;
}

// -- wiring -------------------------------------------------------------

function debounce(fn, delayMs) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delayMs);
  };
}

window.addEventListener("pywebviewready", () => {
  document.getElementById("select-library-btn").addEventListener("click", selectLibraryFolder);
  document.getElementById("rescan-btn").addEventListener("click", () => rescanLibrary());
  document.getElementById("rescan-btn").disabled = true;

  document.querySelectorAll(".template-btn").forEach((btn) => {
    btn.addEventListener("click", () => pickTemplate(btn.dataset.shape));
  });

  document.getElementById("search-input").addEventListener(
    "input",
    debounce((event) => {
      state.query = event.target.value;
      state.page = 0;
      runSearch();
    }, 250)
  );

  document.getElementById("prev-page-btn").addEventListener("click", () => {
    state.page = Math.max(0, state.page - 1);
    runSearch();
  });
  document.getElementById("next-page-btn").addEventListener("click", () => {
    state.page += 1;
    runSearch();
  });

  document.getElementById("generate-btn").addEventListener("click", generatePrintSheet);
});
