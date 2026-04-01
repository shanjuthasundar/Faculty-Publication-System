import { store } from "../store.js";

const API_BASE =
  window.location.protocol === "file:"
    ? "http://127.0.0.1:8000/api"
    : `${window.location.origin}/api`;

const STORAGE_KEYS = {
  token: "fps_auth_token",
  faculty: "fps_faculty"
};

export function setToken(token) {
  localStorage.setItem(STORAGE_KEYS.token, token);
}

export function getToken() {
  return localStorage.getItem(STORAGE_KEYS.token) || "";
}

export function clearAuth() {
  localStorage.removeItem(STORAGE_KEYS.token);
  localStorage.removeItem(STORAGE_KEYS.faculty);
  store.dispatch({ type: "RESET_APP" });
}

export function setFaculty(faculty) {
  localStorage.setItem(STORAGE_KEYS.faculty, JSON.stringify(faculty));
  store.dispatch({ type: "SET_FACULTY", payload: faculty });
}

export function getFaculty() {
  const raw = localStorage.getItem(STORAGE_KEYS.faculty);
  return raw ? JSON.parse(raw) : null;
}

export function withAuthHeaders(extra = {}) {
  const headers = { "Content-Type": "application/json", ...extra };
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

export async function apiRequest(path, options = {}) {
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

export async function validateSession() {
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

export async function logout() {
  try {
    await apiRequest("/auth/logout", {
      method: "POST",
      headers: withAuthHeaders()
    });
  } catch (_) {
    // Ignore logout errors and clear the local session.
  }

  clearAuth();
  window.location.href = "login.html";
}
