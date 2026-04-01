import { apiRequest, setFaculty, setToken, validateSession } from "../core/api.js";
import { hideLoader, showLoader, showToast } from "../core/ui.js";

export async function initLoginPage() {
  const session = await validateSession();
  if (session) {
    window.location.href = "dashboard.html";
    return;
  }

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
    authTitle.textContent = enabled ? "Create Author Account" : "Author Sign In";
    authSubtitle.textContent = `Use only institutional emails (${allowedDomain}).`;
    submitButton.textContent = enabled ? "Create Account" : "Access Dashboard";
    createAccountBtn.textContent = enabled ? "Back to sign in" : "Don't have an account? Create new one";
  }

  createAccountBtn.addEventListener("click", () => {
    setCreateMode(!createMode);
    errorNode.classList.add("d-none");
  });

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

    if (!payload.email.toLowerCase().endsWith(allowedDomain)) {
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
    showLoader(createMode ? "Creating account" : "Signing in");

    try {
      const endpoint = createMode ? "/auth/register" : "/auth/login";
      const data = await apiRequest(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      setToken(data.token);
      setFaculty(data.faculty);
      showToast(createMode ? "Account created successfully." : "Signed in successfully.", "success");
      window.location.href = "dashboard.html";
    } catch (error) {
      errorNode.textContent = error.message;
      errorNode.classList.remove("d-none");
    } finally {
      hideLoader();
      submitButton.disabled = false;
      submitButton.textContent = createMode ? "Create Account" : "Access Dashboard";
    }
  });
}
