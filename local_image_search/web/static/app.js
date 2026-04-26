const state = {
  selectedFolder: null,
  folders: [],
  images: [],
  queryImage: null,
  queryFile: null,
  crop: null,
  dragStart: null,
};

const els = {
  activeCount: document.querySelector("#active-count"),
  folderCount: document.querySelector("#folder-count"),
  errorCount: document.querySelector("#error-count"),
  folders: document.querySelector("#folders"),
  images: document.querySelector("#images"),
  currentFolder: document.querySelector("#current-folder"),
  imageCount: document.querySelector("#image-count"),
  refreshButton: document.querySelector("#refresh-button"),
  dialog: document.querySelector("#preview-dialog"),
  previewImage: document.querySelector("#preview-image"),
  previewMeta: document.querySelector("#preview-meta"),
  closePreview: document.querySelector("#close-preview"),
  queryFile: document.querySelector("#query-file"),
  queryCanvas: document.querySelector("#query-canvas"),
  searchButton: document.querySelector("#search-button"),
  searchStatus: document.querySelector("#search-status"),
};

const queryCtx = els.queryCanvas.getContext("2d");

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function basename(path) {
  return path.split("/").filter(Boolean).pop() || path;
}

function renderStats(stats) {
  els.activeCount.textContent = stats.active || 0;
  els.folderCount.textContent = stats.folders || 0;
  els.errorCount.textContent = stats.error || 0;
}

function renderFolders() {
  els.folders.innerHTML = "";

  if (state.folders.length === 0) {
    els.folders.innerHTML = '<div class="empty">No indexed folders found.</div>';
    return;
  }

  for (const folder of state.folders) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "folder-button";
    if (folder.folder === state.selectedFolder) {
      button.classList.add("active");
    }
    button.innerHTML = `
      <img src="/api/images/${folder.representative_id}/thumbnail" alt="" loading="lazy" />
      <span>
        <span class="folder-name">${basename(folder.folder)}</span>
        <span class="folder-count">${folder.image_count} images</span>
      </span>
    `;
    button.addEventListener("click", () => selectFolder(folder.folder));
    els.folders.appendChild(button);
  }
}

function renderImages() {
  els.images.innerHTML = "";
  els.currentFolder.textContent = state.selectedFolder ? basename(state.selectedFolder) : "Select a folder";
  els.imageCount.textContent = `${state.images.length} images`;

  if (!state.selectedFolder) {
    els.images.innerHTML = '<div class="empty">Choose a folder to inspect thumbnails.</div>';
    return;
  }

  if (state.images.length === 0) {
    els.images.innerHTML = '<div class="empty">No active images in this folder.</div>';
    return;
  }

  for (const image of state.images) {
    const figure = document.createElement("figure");
    figure.className = "image-card";
    figure.innerHTML = `
      <button type="button" title="${image.filename}">
        <img src="/api/images/${image.id}/thumbnail" alt="" loading="lazy" />
      </button>
      <figcaption>${image.filename}</figcaption>
    `;
    figure.querySelector("button").addEventListener("click", () => previewImage(image));
    els.images.appendChild(figure);
  }
}

function renderSearchGroups(groups) {
  els.currentFolder.textContent = "Search results";
  const total = groups.reduce((sum, group) => sum + group.images.length, 0);
  els.imageCount.textContent = `${groups.length} folders, ${total} matches`;
  els.images.innerHTML = "";

  if (groups.length === 0) {
    els.images.innerHTML = '<div class="empty">No vector matches found. Re-run indexing to build vectors.</div>';
    return;
  }

  for (const group of groups) {
    for (const image of group.images) {
      const figure = document.createElement("figure");
      figure.className = "image-card";
      figure.innerHTML = `
        <button type="button" title="${image.filename}">
          <img src="/api/images/${image.id}/thumbnail" alt="" loading="lazy" />
        </button>
        <figcaption><span class="score">${image.score.toFixed(3)}</span> ${basename(group.folder)} / ${image.filename}</figcaption>
      `;
      figure.querySelector("button").addEventListener("click", () => previewImage(image));
      els.images.appendChild(figure);
    }
  }
}

function previewImage(image) {
  els.previewImage.src = `/api/images/${image.id}/thumbnail`;
  els.previewMeta.textContent = `${image.filename} - ${image.width}x${image.height} - ${image.path}`;
  els.dialog.showModal();
}

async function selectFolder(folder) {
  state.selectedFolder = folder;
  renderFolders();
  const params = new URLSearchParams({ folder, limit: "500" });
  const data = await getJson(`/api/images?${params.toString()}`);
  state.images = data.items;
  renderImages();
}

async function load() {
  els.folders.innerHTML = '<div class="empty">Loading folders...</div>';
  els.images.innerHTML = '<div class="empty">Loading images...</div>';

  const [stats, folders] = await Promise.all([
    getJson("/api/stats"),
    getJson("/api/folders?limit=500"),
  ]);
  renderStats(stats);
  state.folders = folders.items;
  state.selectedFolder = state.folders[0]?.folder || null;
  renderFolders();

  if (state.selectedFolder) {
    await selectFolder(state.selectedFolder);
  } else {
    state.images = [];
    renderImages();
  }
}

function drawQueryCanvas() {
  queryCtx.clearRect(0, 0, els.queryCanvas.width, els.queryCanvas.height);
  if (!state.queryImage) {
    return;
  }

  queryCtx.drawImage(state.queryImage, 0, 0, els.queryCanvas.width, els.queryCanvas.height);
  if (state.crop) {
    queryCtx.fillStyle = "rgba(15, 118, 110, 0.18)";
    queryCtx.strokeStyle = "#0f766e";
    queryCtx.lineWidth = 2;
    queryCtx.fillRect(state.crop.x, state.crop.y, state.crop.width, state.crop.height);
    queryCtx.strokeRect(state.crop.x, state.crop.y, state.crop.width, state.crop.height);
  }
}

function canvasPoint(event) {
  const rect = els.queryCanvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * els.queryCanvas.width,
    y: ((event.clientY - rect.top) / rect.height) * els.queryCanvas.height,
  };
}

function normalizeCrop(start, end) {
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  return {
    x,
    y,
    width: Math.max(1, Math.abs(end.x - start.x)),
    height: Math.max(1, Math.abs(end.y - start.y)),
  };
}

function cropForOriginalImage() {
  const scaleX = state.queryImage.naturalWidth / els.queryCanvas.width;
  const scaleY = state.queryImage.naturalHeight / els.queryCanvas.height;
  return {
    x: state.crop.x * scaleX,
    y: state.crop.y * scaleY,
    width: state.crop.width * scaleX,
    height: state.crop.height * scaleY,
  };
}

async function runSearch() {
  if (!state.queryFile || !state.crop) {
    return;
  }

  els.searchStatus.textContent = "Searching...";
  els.searchButton.disabled = true;
  const crop = cropForOriginalImage();
  const form = new FormData();
  form.append("file", state.queryFile);
  form.append("x", crop.x);
  form.append("y", crop.y);
  form.append("width", crop.width);
  form.append("height", crop.height);
  form.append("limit", "80");

  try {
    const response = await fetch("/api/search", { method: "POST", body: form });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const data = await response.json();
    els.searchStatus.textContent = `Model ${data.model}, ${data.groups.length} folder groups`;
    renderSearchGroups(data.groups);
  } catch (error) {
    els.searchStatus.textContent = `Search failed: ${error.message}`;
  } finally {
    els.searchButton.disabled = false;
  }
}

els.refreshButton.addEventListener("click", load);
els.searchButton.addEventListener("click", runSearch);
els.queryFile.addEventListener("change", () => {
  const file = els.queryFile.files[0];
  if (!file) {
    return;
  }
  state.queryFile = file;
  const image = new Image();
  image.onload = () => {
    state.queryImage = image;
    state.crop = {
      x: els.queryCanvas.width * 0.2,
      y: els.queryCanvas.height * 0.2,
      width: els.queryCanvas.width * 0.6,
      height: els.queryCanvas.height * 0.6,
    };
    els.searchButton.disabled = false;
    els.searchStatus.textContent = "Drag a rectangle, then search.";
    drawQueryCanvas();
  };
  image.src = URL.createObjectURL(file);
});
els.queryCanvas.addEventListener("pointerdown", (event) => {
  if (!state.queryImage) {
    return;
  }
  state.dragStart = canvasPoint(event);
  state.crop = { x: state.dragStart.x, y: state.dragStart.y, width: 1, height: 1 };
  els.queryCanvas.setPointerCapture(event.pointerId);
  drawQueryCanvas();
});
els.queryCanvas.addEventListener("pointermove", (event) => {
  if (!state.dragStart) {
    return;
  }
  state.crop = normalizeCrop(state.dragStart, canvasPoint(event));
  drawQueryCanvas();
});
els.queryCanvas.addEventListener("pointerup", (event) => {
  if (!state.dragStart) {
    return;
  }
  state.crop = normalizeCrop(state.dragStart, canvasPoint(event));
  state.dragStart = null;
  drawQueryCanvas();
});
els.closePreview.addEventListener("click", () => els.dialog.close());
els.dialog.addEventListener("click", (event) => {
  if (event.target === els.dialog) {
    els.dialog.close();
  }
});

load().catch((error) => {
  els.folders.innerHTML = `<div class="empty">Failed to load: ${error.message}</div>`;
  els.images.innerHTML = "";
});
