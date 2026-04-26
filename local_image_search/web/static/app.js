const state = {
  selectedFolder: null,
  folders: [],
  images: [],
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
};

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

els.refreshButton.addEventListener("click", load);
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
