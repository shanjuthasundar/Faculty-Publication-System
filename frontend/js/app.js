const API_BASE =
  window.location.protocol === "file:"
    ? "http://127.0.0.1:8000/api"
    : `${window.location.origin}/api`;
const STORAGE_KEYS = {
  token: "fps_auth_token",
  faculty: "fps_faculty"
};

const currentPage = document.body.dataset.page;

function setToken(token) {
  localStorage.setItem(STORAGE_KEYS.token, token);
}

function getToken() {
  return localStorage.getItem(STORAGE_KEYS.token) || "";
}

function clearAuth() {
  localStorage.removeItem(STORAGE_KEYS.token);
  localStorage.removeItem(STORAGE_KEYS.faculty);
}

function setFaculty(faculty) {
  localStorage.setItem(STORAGE_KEYS.faculty, JSON.stringify(faculty));
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
    const message = body.error || "Request failed";
    throw new Error(message);
  }
  return body;
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
    if (publication.conferenceScope === "International") {
      return "International Conference";
    }
    if (publication.conferenceScope === "National") {
      return "National Conference";
    }
    return "Conference";
  }
  return publication.type || "Unknown";
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = String(reader.result || "");
      const base64 = raw.includes(",") ? raw.split(",")[1] : raw;
      resolve(base64);
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
  const now = new Date();
  node.textContent = now.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

async function setupLogin() {
  const form = document.getElementById("loginForm");
  const errorNode = document.getElementById("loginError");
  const submitButton = document.getElementById("loginButton");
  const createAccountBtn = document.getElementById("createAccountBtn");
  const forgotPasswordBtn = document.getElementById("forgotPasswordBtn");
  const recoverWrap = document.getElementById("recoverWrap");
  const recoverInput = document.getElementById("recoverPassword");
  const authTitle = document.getElementById("authTitle");
  const authSubtitle = document.getElementById("authSubtitle");
  let createMode = false;

  function setCreateMode(enabled) {
    createMode = enabled;
    if (createMode) {
      authTitle.textContent = "Create Author Account";
      authSubtitle.textContent = "Provide author name, email, and password to create a new account.";
      submitButton.textContent = "Create Account";
      recoverWrap.classList.add("d-none");
      recoverInput.checked = false;
      createAccountBtn.textContent = "Back to sign in";
      return;
    }

    authTitle.textContent = "Author Sign In";
    authSubtitle.textContent = "Use your author account. New email IDs can be created from this page.";
    submitButton.textContent = "Access Dashboard";
    createAccountBtn.textContent = "Don't have an account? Create new one";
  }

  createAccountBtn.addEventListener("click", () => {
    setCreateMode(!createMode);
    errorNode.classList.add("d-none");
  });

  forgotPasswordBtn.addEventListener("click", () => {
    setCreateMode(false);
    recoverWrap.classList.remove("d-none");
    recoverInput.checked = true;
    authSubtitle.textContent = "Password reset enabled. Enter author name, email, and a new password.";
    errorNode.classList.add("d-none");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorNode.classList.add("d-none");

    const payload = {
      name: document.getElementById("authorName").value.trim(),
      email: document.getElementById("authorEmail").value.trim(),
      password: document.getElementById("authorPassword").value.trim(),
      recover: recoverInput.checked
    };

    if (!payload.email || !payload.password) {
      errorNode.textContent = "Email and password are required.";
      errorNode.classList.remove("d-none");
      return;
    }

    if ((createMode || payload.recover) && !payload.name) {
      errorNode.textContent = "Author name is required.";
      errorNode.classList.remove("d-none");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = createMode ? "Creating..." : "Signing in...";

    try {
      const data = await apiRequest("/auth/login", {
        method: "POST",
        headers: withAuthHeaders(),
        body: JSON.stringify(payload)
      });
      setToken(data.token);
      setFaculty(data.faculty);
      window.location.href = "dashboard.html";
    } catch (error) {
      errorNode.textContent = error.message;
      errorNode.classList.remove("d-none");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = createMode ? "Create Account" : "Access Dashboard";
    }
  });
}

async function validateSession() {
  const token = getToken();
  if (!token) {
    return null;
  }
  try {
    const data = await apiRequest("/auth/me", {
      headers: withAuthHeaders()
    });
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
    // Ignore logout failures and clear client auth anyway.
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
  tableBody.innerHTML = "";

  if (!publications.length) {
    emptyState.classList.remove("d-none");
    return;
  }

  emptyState.classList.add("d-none");
  publications.forEach((item) => {
    const fileToken = encodeURIComponent(item.fileName || `publication-${item.id}`);
    const attachmentAction = item.hasAttachment
      ? `<button class="btn btn-sm btn-outline-primary rounded-pill me-1" data-download-id="${item.id}" data-file-name="${fileToken}">File</button>`
      : `<span class="small text-muted me-1">No file</span>`;

    const row = document.createElement("tr");
    const typeLabel = getTypeLabel(item);
    const scope = item.type === "Conference" ? (item.conferenceScope || "-") : "N/A";
    row.innerHTML = `
      <td>
        <div class="fw-semibold">${item.title}</div>
        <div class="small text-muted">${item.authors}</div>
        <div class="small text-muted mt-1">${formatPreview(item.content || "")}</div>
      </td>
      <td><span class="pill">${typeLabel}</span></td>
      <td>${scope}</td>
      <td>${formatIndexing(item.indexing)}</td>
      <td>${item.venue}</td>
      <td>${item.publishedDate}</td>
      <td>${item.doi || "-"}</td>
      <td>
        ${attachmentAction}
        <button class="btn btn-sm btn-outline-danger rounded-pill" data-id="${item.id}">Delete</button>
      </td>
    `;
    tableBody.appendChild(row);
  });
}

async function downloadAttachment(publicationId, fileName = `publication-${publicationId}`) {
  const response = await fetch(`${API_BASE}/publications/${publicationId}/file`, {
    headers: withAuthHeaders()
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || "Unable to download file.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function loadDashboardData(query = "", typeFilter = "All") {
  const [statsData, publicationsData] = await Promise.all([
    apiRequest("/publications/stats", { headers: withAuthHeaders() }),
    apiRequest(`/publications?q=${encodeURIComponent(query)}`, { headers: withAuthHeaders() })
  ]);

  const filteredPublications =
    typeFilter === "All"
      ? publicationsData.publications
      : publicationsData.publications.filter((item) => getTypeLabel(item) === typeFilter);

  document.getElementById("totalPublications").textContent = statsData.stats.total;
  document.getElementById("journalCount").textContent = statsData.stats.journals;
  document.getElementById("conferenceCount").textContent = statsData.stats.conferences;
  renderPublicationRows(filteredPublications);
}

async function setupDashboard() {
  const faculty = getFaculty();
  if (faculty) {
    document.getElementById("facultyDisplayName").textContent = faculty.name;
  }

  const typeFilter = document.getElementById("typeFilter");
  await loadDashboardData("", typeFilter.value);

  const searchInput = document.getElementById("searchInput");
  let debounceTimer = null;

  function refreshDashboardView() {
    loadDashboardData(searchInput.value.trim(), typeFilter.value).catch((error) => {
      alert(error.message);
    });
  }

  searchInput.addEventListener("input", () => {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    debounceTimer = setTimeout(() => {
      refreshDashboardView();
    }, 220);
  });
  typeFilter.addEventListener("change", refreshDashboardView);

  const tableBody = document.getElementById("publicationTableBody");
  tableBody.addEventListener("click", async (event) => {
    const downloadButton = event.target.closest("button[data-download-id]");
    if (downloadButton) {
      try {
        const publicationId = downloadButton.dataset.downloadId;
        const fileName = decodeURIComponent(downloadButton.dataset.fileName || `publication-${publicationId}`);
        await downloadAttachment(publicationId, fileName);
      } catch (error) {
        alert(error.message);
      }
      return;
    }

    const button = event.target.closest("button[data-id]");
    if (!button) {
      return;
    }

    const publicationId = button.dataset.id;
    button.disabled = true;
    try {
      await apiRequest(`/publications/${publicationId}`, {
        method: "DELETE",
        headers: withAuthHeaders()
      });
      await loadDashboardData(searchInput.value.trim(), typeFilter.value);
    } catch (error) {
      alert(error.message);
    } finally {
      button.disabled = false;
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
      publishedDate: document.getElementById("publishedDate").value,
      content: document.getElementById("content").value.trim(),
      doi: document.getElementById("doi").value.trim()
    };

    if (!payload.title || !payload.authors || !payload.venue || !payload.type || !payload.publishedDate || !payload.content) {
      messageNode.textContent = "Please complete all required fields.";
      messageNode.classList.add("text-danger");
      messageNode.classList.remove("d-none");
      return;
    }

    if (payload.type === "Conference" && !payload.conferenceScope) {
      messageNode.textContent = "Please select conference scope (National/International).";
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
    submitButton.textContent = "Saving...";

    try {
      if (selectedFile) {
        payload.attachment = {
          name: selectedFile.name,
          type: selectedFile.type || "application/octet-stream",
          data: await fileToBase64(selectedFile)
        };
      }

      await apiRequest("/publications", {
        method: "POST",
        headers: withAuthHeaders(),
        body: JSON.stringify(payload)
      });
      form.reset();
      messageNode.textContent = "Publication saved to database.";
      messageNode.classList.add("text-success");
      messageNode.classList.remove("d-none");
    } catch (error) {
      messageNode.textContent = error.message;
      messageNode.classList.add("text-danger");
      messageNode.classList.remove("d-none");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Save Publication";
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

  if (currentPage === "dashboard") {
    const faculty = await initProtectedPage();
    if (!faculty) {
      return;
    }
    document.getElementById("facultyDisplayName").textContent = faculty.name;
    await setupDashboard();
    return;
  }

  if (currentPage === "new-publication") {
    const faculty = await initProtectedPage();
    if (!faculty) {
      return;
    }
    document.getElementById("facultyDisplayName").textContent = faculty.name;
    await setupPublicationForm();
  }
}

init().catch((error) => {
  alert(error.message || "Unexpected app error");
});
