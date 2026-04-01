export function toSafeNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function formatIndexing(indexing = []) {
  if (!Array.isArray(indexing) || indexing.length === 0) {
    return "None";
  }
  return indexing.join(", ");
}

export function formatPreview(content = "", maxLength = 110) {
  if (content.length <= maxLength) {
    return content;
  }
  return `${content.slice(0, maxLength)}...`;
}

export function getTypeLabel(publication) {
  if (publication.type === "Conference") {
    return publication.conferenceScope || "Conference";
  }
  return publication.type || "Unknown";
}

export function getPublicationYear(dateValue) {
  if (!dateValue || String(dateValue).length < 4) {
    return "";
  }
  return String(dateValue).slice(0, 4);
}

export function updateClock() {
  const node = document.getElementById("liveDate");
  if (!node) {
    return;
  }
  node.textContent = new Date().toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || "");
      resolve(raw.includes(",") ? raw.split(",")[1] : raw);
    };
    reader.onerror = () => reject(new Error("Failed to read selected file."));
    reader.readAsDataURL(file);
  });
}

function ensureFeedbackShell() {
  if (!document.getElementById("globalLoader")) {
    const loader = document.createElement("div");
    loader.id = "globalLoader";
    loader.className = "global-loader d-none";
    loader.innerHTML = "<div class='loader-orb'></div><span>Loading</span>";
    document.body.appendChild(loader);
  }

  if (!document.getElementById("toastStack")) {
    const stack = document.createElement("div");
    stack.id = "toastStack";
    stack.className = "toast-stack";
    document.body.appendChild(stack);
  }
}

export function showLoader(message = "Loading") {
  ensureFeedbackShell();
  const loader = document.getElementById("globalLoader");
  if (loader) {
    loader.querySelector("span").textContent = message;
    loader.classList.remove("d-none");
  }
}

export function hideLoader() {
  const loader = document.getElementById("globalLoader");
  if (loader) {
    loader.classList.add("d-none");
  }
}

export function showToast(message, type = "info") {
  ensureFeedbackShell();
  const stack = document.getElementById("toastStack");
  if (!stack) {
    return;
  }

  const toast = document.createElement("div");
  toast.className = `toast-item toast-${type}`;
  toast.textContent = message;
  stack.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("toast-exit");
    setTimeout(() => toast.remove(), 280);
  }, 2600);
}

export function bindLogout(logoutHandler) {
  const logoutLink = document.getElementById("logoutLink");
  if (!logoutLink) {
    return;
  }

  logoutLink.addEventListener("click", (event) => {
    event.preventDefault();
    logoutHandler();
  });
}

export function renderPagination(meta, onPageChange) {
  const mount = document.getElementById("paginationBar");
  if (!mount) {
    return;
  }

  mount.innerHTML = "";
  if (!meta || meta.totalPages <= 1) {
    return;
  }

  const prev = document.createElement("button");
  prev.className = "btn btn-outline-secondary btn-sm";
  prev.textContent = "Previous";
  prev.disabled = meta.page <= 1;
  prev.addEventListener("click", () => onPageChange(meta.page - 1));

  const next = document.createElement("button");
  next.className = "btn btn-outline-secondary btn-sm";
  next.textContent = "Next";
  next.disabled = meta.page >= meta.totalPages;
  next.addEventListener("click", () => onPageChange(meta.page + 1));

  const info = document.createElement("span");
  info.className = "pagination-info";
  info.textContent = `Page ${meta.page} of ${meta.totalPages} • ${meta.total} records`;

  mount.append(prev, info, next);
}
