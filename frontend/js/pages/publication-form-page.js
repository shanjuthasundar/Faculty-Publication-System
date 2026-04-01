import { apiRequest, logout, validateSession, withAuthHeaders } from "../core/api.js";
import { bindLogout, fileToBase64, hideLoader, showLoader, showToast, updateClock } from "../core/ui.js";

export async function initPublicationFormPage() {
  const faculty = await validateSession();
  if (!faculty) {
    window.location.href = "login.html";
    return;
  }

  bindLogout(logout);
  updateClock();
  setInterval(updateClock, 60000);
  document.getElementById("facultyDisplayName").textContent = faculty.name;

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
    showLoader("Loading publication");
    try {
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
      document.getElementById("hIndex").value = Number(publication.hIndex ?? 0);
      document.getElementById("iIndex").value = Number(publication.iIndex ?? 0);
      document.getElementById("publisherName").value = publication.publisherName || "";
      document.getElementById("doi").value = publication.doi || "";

      Array.from(document.querySelectorAll("input[name='indexing']")).forEach((node) => {
        node.checked = Array.isArray(publication.indexing) ? publication.indexing.includes(node.value) : false;
      });

      if (publication.hasAttachment) {
        removeAttachmentWrap.classList.remove("d-none");
      }
      updateConferenceScopeState();
    } finally {
      hideLoader();
    }
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
      hIndex: Number(document.getElementById("hIndex").value || 0),
      iIndex: Number(document.getElementById("iIndex").value || 0),
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
      messageNode.textContent = "Please select conference scope.";
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

    if (Number.isNaN(payload.hIndex) || payload.hIndex < 0) {
      messageNode.textContent = "h-index must be a valid non-negative number.";
      messageNode.classList.add("text-danger");
      messageNode.classList.remove("d-none");
      return;
    }

    if (Number.isNaN(payload.iIndex) || payload.iIndex < 0) {
      messageNode.textContent = "i-index must be a valid non-negative number.";
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
    showLoader(isEditMode ? "Updating publication" : "Saving publication");

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
      showToast(isEditMode ? "Publication updated." : "Publication created.", "success");

      if (!isEditMode) {
        form.reset();
        updateConferenceScopeState();
      }
    } catch (error) {
      messageNode.textContent = error.message;
      messageNode.classList.add("text-danger");
      messageNode.classList.remove("d-none");
      showToast(error.message, "error");
    } finally {
      hideLoader();
      submitButton.disabled = false;
      submitButton.textContent = isEditMode ? "Update Publication" : "Save Publication";
    }
  });
}
