import { apiRequest, logout, validateSession, withAuthHeaders } from "../core/api.js";
import {
  bindLogout,
  formatIndexing,
  formatPreview,
  getPublicationYear,
  getTypeLabel,
  hideLoader,
  renderPagination,
  showLoader,
  showToast,
  updateClock
} from "../core/ui.js";
import { store } from "../store.js";

function renderPublicationRows(publications) {
  const tableBody = document.getElementById("publicationTableBody");
  const emptyState = document.getElementById("emptyState");
  if (!tableBody || !emptyState) {
    return;
  }

  tableBody.innerHTML = "";
  if (!publications.length) {
    emptyState.classList.remove("d-none");
    return;
  }

  emptyState.classList.add("d-none");
  publications.forEach((item) => {
    const fileToken = encodeURIComponent(item.fileName || `publication-${item.id}`);
    const attachmentAction = item.hasAttachment
      ? `<button class="btn btn-sm btn-outline-primary rounded-pill me-1" data-download-id="${item.id}" data-file-name="${fileToken}">Front Page</button>`
      : `<span class="small text-muted me-1">No file</span>`;

    const row = document.createElement("tr");
    row.innerHTML = `
      <td>
        <div class="fw-semibold">${item.title}</div>
        <div class="small text-muted">${item.authors}</div>
        <div class="small text-muted mt-1">${formatPreview(item.content || "")}</div>
      </td>
      <td><span class="pill">${getTypeLabel(item)}</span></td>
      <td>${item.type === "Conference" ? item.conferenceScope || "-" : "N/A"}</td>
      <td>${formatIndexing(item.indexing)}</td>
      <td>
        <div>${item.venue}</div>
        <div class="small text-muted">${item.publisherName || "Publisher not specified"}</div>
      </td>
      <td>${item.submissionDate || item.publishedDate || "-"}</td>
      <td>${item.impactFactor ?? item.citationCount ?? 0}</td>
      <td>${item.doi || "-"}</td>
      <td>
        ${attachmentAction}
        <a class="btn btn-sm btn-outline-secondary rounded-pill me-1" href="new-report.html?edit=${item.id}">Edit</a>
        <button class="btn btn-sm btn-outline-danger rounded-pill" data-id="${item.id}">Delete</button>
      </td>
    `;
    tableBody.appendChild(row);
  });
}

async function viewAttachmentFrontPage(publicationId, fileName = `publication-${publicationId}`) {
  const response = await fetch(`${window.location.origin}/api/publications/${publicationId}/file`, {
    headers: withAuthHeaders()
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || "Unable to download file.");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const isPdf = String(blob.type || "").toLowerCase().includes("pdf") || fileName.toLowerCase().endsWith(".pdf");
  if (isPdf) {
    window.open(`${url}#page=1`, "_blank", "noopener");
  } else {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }
  setTimeout(() => URL.revokeObjectURL(url), 12000);
}

function exportPublicationsCsv(publications) {
  if (!publications.length) {
    showToast("No publication records to export.", "warn");
    return;
  }

  const rows = [
    ["Title", "Authors", "Type", "Conference Scope", "Indexing", "Venue", "Publisher", "Submission Date", "Impact Factor", "DOI"],
    ...publications.map((item) => [
      item.title || "",
      item.authors || "",
      getTypeLabel(item),
      item.conferenceScope || "",
      formatIndexing(item.indexing),
      item.venue || "",
      item.publisherName || "",
      item.submissionDate || item.publishedDate || "",
      String(item.impactFactor ?? item.citationCount ?? 0),
      item.doi || ""
    ])
  ];

  const csvContent = rows
    .map((row) => row.map((value) => `"${String(value).replace(/"/g, "\"\"")}"`).join(","))
    .join("\n");

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `publications-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function populateYearFilter(publications) {
  const yearFilter = document.getElementById("yearFilter");
  if (!yearFilter) {
    return;
  }

  const selected = yearFilter.value || "All";
  const years = Array.from(new Set(publications.map((item) => getPublicationYear(item.submissionDate || item.publishedDate)).filter(Boolean))).sort(
    (a, b) => Number(b) - Number(a)
  );

  yearFilter.innerHTML = `<option value="All">All Years</option>${years.map((year) => `<option value="${year}">${year}</option>`).join("")}`;
  if (years.includes(selected)) {
    yearFilter.value = selected;
  }
}

async function fetchDashboardData(filters) {
  const params = new URLSearchParams();
  if (filters.query) {
    params.set("q", filters.query);
  }
  if (filters.year !== "All") {
    params.set("year", filters.year);
  }
  if (filters.scope !== "All") {
    params.set("scope", filters.scope);
  }
  if (filters.indexing !== "All") {
    params.set("indexing", filters.indexing);
  }
  if (["Journal", "Conference", "Article", "Books", "Chapter"].includes(filters.type)) {
    params.set("type", filters.type);
  }
  params.set("page", String(filters.page));
  params.set("page_size", "8");

  const publicationPath = `/publications?${params.toString()}`;
  const [statsData, publicationsData] = await Promise.all([
    apiRequest("/publications/stats", { headers: withAuthHeaders() }),
    apiRequest(publicationPath, { headers: withAuthHeaders() })
  ]);

  let publications = publicationsData.publications || [];
  if (filters.type === "International Conference" || filters.type === "National Conference") {
    publications = publications.filter((item) => getTypeLabel(item) === filters.type);
  }

  store.dispatch({ type: "SET_STATS", payload: statsData.stats || {} });
  store.dispatch({ type: "SET_PUBLICATIONS", payload: publications });
  store.dispatch({ type: "SET_PAGINATION", payload: publicationsData.pagination || store.getState().pagination });
  return publications;
}

export async function initDashboardPage() {
  const faculty = await validateSession();
  if (!faculty) {
    window.location.href = "login.html";
    return;
  }

  const filters = {
    query: "",
    type: "All",
    year: "All",
    scope: "All",
    indexing: "All",
    page: 1
  };

  document.getElementById("facultyDisplayName").textContent = faculty.name;
  bindLogout(logout);
  updateClock();
  setInterval(updateClock, 60000);

  const typeFilter = document.getElementById("typeFilter");
  const yearFilter = document.getElementById("yearFilter");
  const scopeFilter = document.getElementById("scopeFilter");
  const indexingFilter = document.getElementById("indexingFilter");
  const searchInput = document.getElementById("searchInput");
  const exportBtn = document.getElementById("exportCsvBtn");
  const tableBody = document.getElementById("publicationTableBody");

  showLoader("Loading dashboard");
  const initialData = await apiRequest("/publications?page=1&page_size=50", { headers: withAuthHeaders() });
  populateYearFilter(initialData.publications || []);

  async function applyDashboardState() {
    showLoader("Refreshing records");
    try {
      const publications = await fetchDashboardData(filters);
      const state = store.getState();
      document.getElementById("totalPublications").textContent = state.stats.total ?? 0;
      document.getElementById("journalCount").textContent = state.stats.journals ?? 0;
      document.getElementById("conferenceCount").textContent = state.stats.conferences ?? 0;
      document.getElementById("internationalConferenceCount").textContent = state.stats.internationalConferences ?? 0;
      document.getElementById("nationalConferenceCount").textContent = state.stats.nationalConferences ?? 0;
      document.getElementById("scopusCount").textContent = state.stats.scopusIndexed ?? 0;
      document.getElementById("sciCount").textContent = state.stats.sciIndexed ?? 0;
      document.getElementById("nonScopusCount").textContent = state.stats.nonScopusIndexed ?? 0;
      document.getElementById("nonSciCount").textContent = state.stats.nonSciIndexed ?? 0;
      renderPublicationRows(publications);
      renderPagination(state.pagination, (nextPage) => {
        filters.page = nextPage;
        applyDashboardState().catch((error) => showToast(error.message, "error"));
      });
    } finally {
      hideLoader();
    }
  }

  await applyDashboardState();

  let debounceTimer = null;
  searchInput.addEventListener("input", () => {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    debounceTimer = setTimeout(() => {
      filters.query = searchInput.value.trim();
      filters.page = 1;
      applyDashboardState().catch((error) => showToast(error.message, "error"));
    }, 220);
  });

  typeFilter.addEventListener("change", () => {
    filters.type = typeFilter.value;
    filters.page = 1;
    applyDashboardState().catch((error) => showToast(error.message, "error"));
  });
  yearFilter.addEventListener("change", () => {
    filters.year = yearFilter.value;
    filters.page = 1;
    applyDashboardState().catch((error) => showToast(error.message, "error"));
  });
  scopeFilter.addEventListener("change", () => {
    filters.scope = scopeFilter.value;
    filters.page = 1;
    applyDashboardState().catch((error) => showToast(error.message, "error"));
  });
  indexingFilter.addEventListener("change", () => {
    filters.indexing = indexingFilter.value;
    filters.page = 1;
    applyDashboardState().catch((error) => showToast(error.message, "error"));
  });

  exportBtn.addEventListener("click", () => exportPublicationsCsv(store.getState().publications || []));

  tableBody.addEventListener("click", async (event) => {
    const downloadButton = event.target.closest("button[data-download-id]");
    if (downloadButton) {
      try {
        await viewAttachmentFrontPage(downloadButton.dataset.downloadId, decodeURIComponent(downloadButton.dataset.fileName));
      } catch (error) {
        showToast(error.message, "error");
      }
      return;
    }

    const deleteButton = event.target.closest("button[data-id]");
    if (!deleteButton) {
      return;
    }

    deleteButton.disabled = true;
    showLoader("Deleting publication");
    try {
      await apiRequest(`/publications/${deleteButton.dataset.id}`, {
        method: "DELETE",
        headers: withAuthHeaders()
      });
      showToast("Publication deleted.", "success");
      await applyDashboardState();
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      hideLoader();
      deleteButton.disabled = false;
    }
  });
}
