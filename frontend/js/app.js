const API_BASE =
  window.location.protocol === "file:"
    ? "http://127.0.0.1:8000/api"
    : `${window.location.origin}/api`;

const STORAGE_KEYS = {
  token: "fps_auth_token",
  faculty: "fps_faculty"
};

const currentPage = document.body.dataset.page;
const store = window.appStore;

function setToken(token) {
  localStorage.setItem(STORAGE_KEYS.token, token);
}

function getToken() {
  return localStorage.getItem(STORAGE_KEYS.token) || "";
}

function clearAuth() {
  localStorage.removeItem(STORAGE_KEYS.token);
  localStorage.removeItem(STORAGE_KEYS.faculty);
  store.dispatch({ type: "RESET_APP" });
}

function setFaculty(faculty) {
  localStorage.setItem(STORAGE_KEYS.faculty, JSON.stringify(faculty));
  store.dispatch({ type: "SET_FACULTY", payload: faculty });
}

function getFaculty() {
  const raw = localStorage.getItem(STORAGE_KEYS.faculty);
  return raw ? JSON.parse(raw) : null;
}

function withAuthHeaders(extra = {}) {
  const headers = { "Content-Type": "application/json", ...extra };
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function apiRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (_) {
    throw new Error("Unable to reach backend. Start server at http://127.0.0.1:8000");
  }

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || "Request failed");
  }
  return body;
}

function toSafeInt(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : fallback;
}

function formatPreview(content = "", maxLength = 110) {
  if (content.length <= maxLength) {
    return content;
  }
  return `${content.slice(0, maxLength)}...`;
}

function formatIndexing(indexing = []) {
  if (!Array.isArray(indexing) || indexing.length === 0) {
    return "None";
  }
  return indexing.join(", ");
}

function getTypeLabel(publication) {
  if (publication.type === "Conference") {
    if (publication.conferenceScope === "International Conference") {
      return "International Conference";
    }
    if (publication.conferenceScope === "National Conference") {
      return "National Conference";
    }
    return "Conference";
  }
  return publication.type || "Unknown";
}

function getPublicationYear(submissionDate) {
  if (!submissionDate || String(submissionDate).length < 4) {
    return "";
  }
  return String(submissionDate).slice(0, 4);
}

function fileToBase64(file) {
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

function updateClock() {
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

async function validateSession() {
  const token = getToken();
  if (!token) {
    return null;
  }

  try {
    const data = await apiRequest("/auth/me", { headers: withAuthHeaders() });
    setFaculty(data.faculty);
    return data.faculty;
  } catch (_) {
    clearAuth();
    return null;
  }
}

async function logout() {
  try {
    await apiRequest("/auth/logout", {
      method: "POST",
      headers: withAuthHeaders()
    });
  } catch (_) {
    // Ignore logout API errors.
  }
  clearAuth();
  window.location.href = "login.html";
}

function bindLogout() {
  const logoutLink = document.getElementById("logoutLink");
  if (!logoutLink) {
    return;
  }

  logoutLink.addEventListener("click", (event) => {
    event.preventDefault();
    logout();
  });
}

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
  const response = await fetch(`${API_BASE}/publications/${publicationId}/file`, {
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
    alert("No publication records to export.");
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
    .map((row) => row.map((value) => `"${String(value).replace(/"/g, '""')}"`).join(","))
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
  const years = Array.from(
    new Set(publications.map((item) => getPublicationYear(item.submissionDate || item.publishedDate)).filter(Boolean))
  ).sort(
    (a, b) => Number(b) - Number(a)
  );

  yearFilter.innerHTML = `<option value="All">All Years</option>${years
    .map((year) => `<option value="${year}">${year}</option>`)
    .join("")}`;

  if (years.includes(selected)) {
    yearFilter.value = selected;
  }
}

async function fetchDashboardData(
  query = "",
  typeFilter = "All",
  yearFilter = "All",
  scopeFilter = "All",
  indexingFilter = "All"
) {
  const params = new URLSearchParams();
  if (query) {
    params.set("q", query);
  }
  if (yearFilter !== "All") {
    params.set("year", yearFilter);
  }
  if (scopeFilter !== "All") {
    params.set("scope", scopeFilter);
  }
  if (indexingFilter !== "All") {
    params.set("indexing", indexingFilter);
  }
  if (["Journal", "Conference", "Article", "Books", "Chapter"].includes(typeFilter)) {
    params.set("type", typeFilter);
  }

  const publicationPath = params.toString() ? `/publications?${params.toString()}` : "/publications";

  const [statsData, publicationsData] = await Promise.all([
    apiRequest("/publications/stats", { headers: withAuthHeaders() }),
    apiRequest(publicationPath, { headers: withAuthHeaders() })
  ]);

  let publications = publicationsData.publications || [];
  if (typeFilter === "International Conference" || typeFilter === "National Conference") {
    publications = publications.filter((item) => getTypeLabel(item) === typeFilter);
  }

  store.dispatch({ type: "SET_STATS", payload: statsData.stats || {} });
  store.dispatch({ type: "SET_PUBLICATIONS", payload: publications });
  return publications;
}

async function setupLogin() {
  const form = document.getElementById("loginForm");
  const errorNode = document.getElementById("loginError");
  const submitButton = document.getElementById("loginButton");
  const createAccountBtn = document.getElementById("createAccountBtn");
  const authTitle = document.getElementById("authTitle");
  const authSubtitle = document.getElementById("authSubtitle");
  const allowedDomain = "@bitsathy.ac.in";

  let createMode = false;

  function setCreateMode(enabled) {
    createMode = enabled;

    if (enabled) {
      authTitle.textContent = "Create Author Account";
      authSubtitle.textContent = `Use only institutional emails (${allowedDomain}).`;
      submitButton.textContent = "Create Account";
      createAccountBtn.textContent = "Back to sign in";
      return;
    }

    authTitle.textContent = "Author Sign In";
    authSubtitle.textContent = `Use only institutional emails (${allowedDomain}).`;
    submitButton.textContent = "Access Dashboard";
    createAccountBtn.textContent = "Don't have an account? Create new one";
  }

  createAccountBtn.addEventListener("click", () => {
    setCreateMode(!createMode);
    errorNode.classList.add("d-none");
  });

  function getEmailInput() {
    return document.getElementById("authorEmail").value.trim().toLowerCase();
  }

  function isInstitutionEmail(email) {
    return email.endsWith(allowedDomain);
  }


  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorNode.classList.add("d-none");

    const payload = {
      name: document.getElementById("authorName").value.trim(),
      email: document.getElementById("authorEmail").value.trim(),
      password: document.getElementById("authorPassword").value.trim()
    };

    if (!payload.email || !payload.password) {
      errorNode.textContent = "Email and password are required.";
      errorNode.classList.remove("d-none");
      return;
    }

    if (!isInstitutionEmail(payload.email.toLowerCase())) {
      errorNode.textContent = `Only ${allowedDomain} email addresses are allowed.`;
      errorNode.classList.remove("d-none");
      return;
    }

    if (createMode && !payload.name) {
      errorNode.textContent = "Author name is required.";
      errorNode.classList.remove("d-none");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = createMode ? "Creating..." : "Signing in...";

    try {
      const endpoint = createMode ? "/auth/register" : "/auth/login";
      const data = await apiRequest(endpoint, {
        method: "POST",
        headers: withAuthHeaders(),
        body: JSON.stringify(payload)
      });
      setToken(data.token);
      setFaculty(data.faculty);
      window.location.href = "dashboard.html";
    } catch (error) {
      if (!createMode && payload.name && String(error.message || "").toLowerCase().includes("invalid credentials")) {
        try {
          const registerData = await apiRequest("/auth/register", {
            method: "POST",
            headers: withAuthHeaders(),
            body: JSON.stringify(payload)
          });
          setToken(registerData.token);
          setFaculty(registerData.faculty);
          window.location.href = "dashboard.html";
          return;
        } catch (registerError) {
          if (String(registerError.message || "").toLowerCase().includes("already exists")) {
            errorNode.textContent = "Account exists with a different password. Please contact administrator for reset.";
          } else {
            errorNode.textContent = registerError.message;
          }
          errorNode.classList.remove("d-none");
          return;
        }
      }
      errorNode.textContent = error.message;
      errorNode.classList.remove("d-none");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = createMode ? "Create Account" : "Access Dashboard";
    }
  });
}

async function setupDashboard() {
  const typeFilter = document.getElementById("typeFilter");
  const yearFilter = document.getElementById("yearFilter");
  const scopeFilter = document.getElementById("scopeFilter");
  const indexingFilter = document.getElementById("indexingFilter");
  const searchInput = document.getElementById("searchInput");
  const exportBtn = document.getElementById("exportCsvBtn");
  const tableBody = document.getElementById("publicationTableBody");

  const initialData = await apiRequest("/publications", { headers: withAuthHeaders() });
  populateYearFilter(initialData.publications || []);

  const applyDashboardState = async () => {
    const publications = await fetchDashboardData(
      searchInput.value.trim(),
      typeFilter.value,
      yearFilter.value,
      scopeFilter.value,
      indexingFilter.value
    );

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
  };

  await applyDashboardState();

  let debounceTimer = null;
  searchInput.addEventListener("input", () => {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    debounceTimer = setTimeout(() => {
      applyDashboardState().catch((error) => alert(error.message));
    }, 220);
  });

  typeFilter.addEventListener("change", () => applyDashboardState().catch((error) => alert(error.message)));
  yearFilter.addEventListener("change", () => applyDashboardState().catch((error) => alert(error.message)));
  scopeFilter.addEventListener("change", () => applyDashboardState().catch((error) => alert(error.message)));
  indexingFilter.addEventListener("change", () => applyDashboardState().catch((error) => alert(error.message)));

  exportBtn.addEventListener("click", () => {
    exportPublicationsCsv(store.getState().publications || []);
  });

  tableBody.addEventListener("click", async (event) => {
    const downloadButton = event.target.closest("button[data-download-id]");
    if (downloadButton) {
      try {
        const publicationId = downloadButton.dataset.downloadId;
        const fileName = decodeURIComponent(downloadButton.dataset.fileName || `publication-${publicationId}`);
        await viewAttachmentFrontPage(publicationId, fileName);
      } catch (error) {
        alert(error.message);
      }
      return;
    }

    const deleteButton = event.target.closest("button[data-id]");
    if (!deleteButton) {
      return;
    }

    const publicationId = deleteButton.dataset.id;
    deleteButton.disabled = true;
    try {
      await apiRequest(`/publications/${publicationId}`, {
        method: "DELETE",
        headers: withAuthHeaders()
      });
      await applyDashboardState();
    } catch (error) {
      alert(error.message);
    } finally {
      deleteButton.disabled = false;
    }
  });
}

async function setupPublicationForm() {
  const form = document.getElementById("publicationForm");
  const messageNode = document.getElementById("formMessage");
  const submitButton = document.getElementById("savePublicationButton");
  const attachmentInput = document.getElementById("attachment");
  const typeInput = document.getElementById("type");
  const conferenceScopeInput = document.getElementById("conferenceScope");
  const removeAttachmentWrap = document.getElementById("removeAttachmentWrap");
  const removeAttachmentInput = document.getElementById("removeAttachment");
  const pageTitle = document.getElementById("formPageTitle");
  const modeLabel = document.getElementById("formModeLabel");

  const query = new URLSearchParams(window.location.search);
  const editId = query.get("edit");
  const isEditMode = Boolean(editId);

  function updateConferenceScopeState() {
    const isConference = typeInput.value === "Conference";
    conferenceScopeInput.disabled = !isConference;
    conferenceScopeInput.required = isConference;
    if (!isConference) {
      conferenceScopeInput.value = "";
    }
  }

  updateConferenceScopeState();
  typeInput.addEventListener("change", updateConferenceScopeState);

  if (isEditMode) {
    pageTitle.textContent = "Edit Publication Entry";
    modeLabel.textContent = "Update Record";
    submitButton.textContent = "Update Publication";

    const { publication } = await apiRequest(`/publications/${editId}`, {
      headers: withAuthHeaders()
    });

    document.getElementById("title").value = publication.title || "";
    document.getElementById("authors").value = publication.authors || "";
    document.getElementById("venue").value = publication.venue || "";
    document.getElementById("type").value = publication.type || "";
    document.getElementById("conferenceScope").value = publication.conferenceScope === "N/A" ? "" : publication.conferenceScope;
    document.getElementById("submissionDate").value = publication.submissionDate || publication.publishedDate || "";
    document.getElementById("content").value = publication.content || "";
    document.getElementById("impactFactor").value = Number(publication.impactFactor ?? publication.citationCount ?? 0);
    document.getElementById("publisherName").value = publication.publisherName || "";
    document.getElementById("doi").value = publication.doi || "";

    Array.from(document.querySelectorAll("input[name='indexing']")).forEach((node) => {
      node.checked = Array.isArray(publication.indexing) ? publication.indexing.includes(node.value) : false;
    });

    if (publication.hasAttachment) {
      removeAttachmentWrap.classList.remove("d-none");
    }

    updateConferenceScopeState();
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageNode.classList.add("d-none");
    messageNode.classList.remove("text-danger", "text-success");

    const payload = {
      title: document.getElementById("title").value.trim(),
      authors: document.getElementById("authors").value.trim(),
      venue: document.getElementById("venue").value.trim(),
      type: document.getElementById("type").value,
      conferenceScope: document.getElementById("conferenceScope").value,
      indexing: Array.from(document.querySelectorAll("input[name='indexing']:checked")).map((node) => node.value),
      submissionDate: document.getElementById("submissionDate").value,
      content: document.getElementById("content").value.trim(),
      impactFactor: Number(document.getElementById("impactFactor").value || 0),
      publisherName: document.getElementById("publisherName").value.trim(),
      doi: document.getElementById("doi").value.trim()
    };

    if (!payload.title || !payload.authors || !payload.venue || !payload.type || !payload.submissionDate || !payload.content) {
      messageNode.textContent = "Please complete all required fields.";
      messageNode.classList.add("text-danger");
      messageNode.classList.remove("d-none");
      return;
    }

    if (payload.type === "Conference" && !payload.conferenceScope) {
      messageNode.textContent = "Please select conference scope (National Conference / International Conference).";
      messageNode.classList.add("text-danger");
      messageNode.classList.remove("d-none");
      return;
    }

    if (Number.isNaN(payload.impactFactor) || payload.impactFactor < 0) {
      messageNode.textContent = "Impact factor must be a valid non-negative number.";
      messageNode.classList.add("text-danger");
      messageNode.classList.remove("d-none");
      return;
    }

    const selectedFile = attachmentInput.files && attachmentInput.files[0] ? attachmentInput.files[0] : null;
    if (selectedFile && selectedFile.size > 10 * 1024 * 1024) {
      messageNode.textContent = "Selected file exceeds 10 MB.";
      messageNode.classList.add("text-danger");
      messageNode.classList.remove("d-none");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = isEditMode ? "Updating..." : "Saving...";

    try {
      if (selectedFile) {
        payload.attachment = {
          name: selectedFile.name,
          type: selectedFile.type || "application/octet-stream",
          data: await fileToBase64(selectedFile)
        };
      }

      if (isEditMode && removeAttachmentInput.checked) {
        payload.removeAttachment = true;
      }

      await apiRequest(isEditMode ? `/publications/${editId}` : "/publications", {
        method: isEditMode ? "PUT" : "POST",
        headers: withAuthHeaders(),
        body: JSON.stringify(payload)
      });

      messageNode.textContent = isEditMode ? "Publication updated successfully." : "Publication saved to database.";
      messageNode.classList.add("text-success");
      messageNode.classList.remove("d-none");

      if (!isEditMode) {
        form.reset();
        updateConferenceScopeState();
      }
    } catch (error) {
      messageNode.textContent = error.message;
      messageNode.classList.add("text-danger");
      messageNode.classList.remove("d-none");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = isEditMode ? "Update Publication" : "Save Publication";
    }
  });
}

async function initProtectedPage() {
  const faculty = await validateSession();
  if (!faculty) {
    window.location.href = "login.html";
    return null;
  }

  bindLogout();
  updateClock();
  setInterval(updateClock, 60000);
  return faculty;
}

async function init() {
  if (currentPage === "login") {
    const session = await validateSession();
    if (session) {
      window.location.href = "dashboard.html";
      return;
    }
    await setupLogin();
    return;
  }

  const faculty = await initProtectedPage();
  if (!faculty) {
    return;
  }

  const display = document.getElementById("facultyDisplayName");
  if (display) {
    display.textContent = faculty.name;
  }

  if (currentPage === "dashboard") {
    await setupDashboard();
    return;
  }

  if (currentPage === "new-publication") {
    await setupPublicationForm();
  }
}

init().catch((error) => {
  alert(error.message || "Unexpected app error");
});
