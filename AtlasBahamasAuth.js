(() => {
  const root = typeof window !== "undefined" ? window : globalThis;

  let sessionCache = null;
  let sessionLoaded = false;
  let csrfTokenCache = "";

  function normalizeRole(role) {
    const value = String(role || "").trim().toLowerCase();
    if (value === "tenant") return "tenant";
    if (value === "landlord" || value === "property_manager" || value === "manager") return "landlord";
    return "";
  }

  function roleHome(role) {
    return normalizeRole(role) === "landlord"
      ? "AtlasBahamasLandlordDashboard.html"
      : "AtlasBahamasTenantDashboard.html";
  }

  function safeNextPath(next) {
    const value = String(next || "").trim();
    if (!value) return "";

    const allowed = new Set([
      "AtlasBahamasTenantDashboard.html",
      "AtlasBahamasLandlordDashboard.html",
      "AtlasBahamasListings.html",
      "AtlasBahamasContact.html",
      "AtlasBahamasAbout.html"
    ]);

    if (allowed.has(value)) return value;
    return "";
  }

  function parseQuery(search) {
    const src = typeof search === "string" ? search : (root.location ? root.location.search : "");
    const params = new URLSearchParams(src || "");
    return {
      role: normalizeRole(params.get("role")),
      next: safeNextPath(params.get("next"))
    };
  }

  function passwordPolicyErrors(password) {
    const value = String(password || "");
    const errors = [];
    if (value.length < 10) errors.push("minimum 10 characters");
    if (!/[A-Z]/.test(value)) errors.push("at least one uppercase letter");
    if (!/[a-z]/.test(value)) errors.push("at least one lowercase letter");
    if (!/[0-9]/.test(value)) errors.push("at least one number");
    if (!/[^A-Za-z0-9]/.test(value)) errors.push("at least one symbol");
    return errors;
  }

  function dispatchAuthChange() {
    try {
      if (typeof root.dispatchEvent === "function" && typeof root.CustomEvent === "function") {
        root.dispatchEvent(new root.CustomEvent("atlas-auth-changed"));
      }
    } catch {
      // No-op on event dispatch issues in non-browser contexts.
    }
  }

  function isWriteMethod(method) {
    return ["POST", "PUT", "PATCH", "DELETE"].includes(String(method || "").toUpperCase());
  }

  function isCsrfExempt(path) {
    const value = String(path || "").toLowerCase();
    return value === "/api/login" || value === "/api/register";
  }

  function updateCsrfToken(token) {
    csrfTokenCache = typeof token === "string" ? token : "";
    return csrfTokenCache;
  }

  async function apiRequest(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const body = options.body;
    const headers = {
      Accept: "application/json",
      ...(options.headers || {})
    };

    if (isWriteMethod(method) && !isCsrfExempt(path)) {
      if (!csrfTokenCache) {
        await getSession(true);
      }
      if (csrfTokenCache) {
        headers["X-CSRF-Token"] = csrfTokenCache;
      }
    }

    const fetchOptions = {
      method,
      credentials: "same-origin",
      headers
    };

    if (body !== undefined) {
      fetchOptions.body = JSON.stringify(body);
      fetchOptions.headers["Content-Type"] = "application/json";
    }

    let response;
    try {
      response = await root.fetch(path, fetchOptions);
    } catch {
      return {
        ok: false,
        status: 0,
        error: "Cannot reach Atlas API. Start the backend server and refresh."
      };
    }

    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }

    if (!response.ok || payload.ok === false) {
      const err = String(payload.error || "");
      if (
        response.status === 400 &&
        err.toLowerCase().includes("csrf") &&
        !options._retried &&
        !isCsrfExempt(path)
      ) {
        await getSession(true);
        return apiRequest(path, { ...options, _retried: true });
      }
      return {
        ok: false,
        status: response.status,
        error: payload.error || `Request failed (${response.status})`,
        data: payload
      };
    }

    if (payload && payload.csrfToken) {
      updateCsrfToken(payload.csrfToken);
    }

    return { ok: true, status: response.status, data: payload };
  }

  function cacheSession(session) {
    sessionCache = session && typeof session === "object" ? session : null;
    sessionLoaded = true;
    return sessionCache;
  }

  async function getSession(force = false) {
    if (sessionLoaded && !force) return sessionCache;
    const result = await apiRequest("/api/session");
    if (!result.ok) {
      sessionLoaded = false;
      sessionCache = null;
      return null;
    }

    if (result.data && result.data.csrfToken) {
      updateCsrfToken(result.data.csrfToken);
    }

    if (result.data && result.data.authenticated && result.data.session) {
      cacheSession(result.data.session);
    } else {
      cacheSession(null);
    }
    return sessionCache;
  }

  function setSession(session) {
    const next = cacheSession(session);
    dispatchAuthChange();
    return next;
  }

  function clearSession() {
    cacheSession(null);
    dispatchAuthChange();
  }

  function getCsrfToken() {
    return csrfTokenCache;
  }

  async function ensureSeedUsers() {
    // Demo seeds are server-managed at startup.
    await getSession(true);
    return [];
  }

  async function registerUser(payload) {
    const data = payload || {};
    const policy = passwordPolicyErrors(data.password || "");
    if (policy.length > 0) {
      return { ok: false, error: `Password must include: ${policy.join(", ")}.` };
    }

    const result = await apiRequest("/api/register", {
      method: "POST",
      body: {
        fullName: data.fullName,
        email: data.email,
        username: data.username,
        role: normalizeRole(data.role),
        password: data.password,
        passwordConfirm: data.passwordConfirm
      }
    });

    if (!result.ok) {
      return { ok: false, error: result.error };
    }

    if (result.data && result.data.csrfToken) {
      updateCsrfToken(result.data.csrfToken);
    }
    const session = setSession(result.data.session || null);
    return { ok: true, session, user: result.data.user || null };
  }

  async function loginUser(payload) {
    const data = payload || {};
    const result = await apiRequest("/api/login", {
      method: "POST",
      body: {
        identifier: data.identifier,
        password: data.password,
        role: normalizeRole(data.role)
      }
    });

    if (!result.ok) {
      return { ok: false, error: result.error };
    }

    if (result.data && result.data.csrfToken) {
      updateCsrfToken(result.data.csrfToken);
    }
    const session = setSession(result.data.session || null);
    return { ok: true, session, user: result.data.user || null };
  }

  async function logout() {
    await apiRequest("/api/logout", { method: "POST", body: {} });
    clearSession();
    await getSession(true);
    return { ok: true };
  }

  async function requireRole(role) {
    const session = await getSession();
    if (!session) return { ok: false, reason: "unauthenticated", session: null };
    const expected = normalizeRole(role);
    if (!expected) return { ok: true, reason: "ok", session };
    if (normalizeRole(session.role) !== expected) {
      return { ok: false, reason: "forbidden", session };
    }
    return { ok: true, reason: "ok", session };
  }

  async function saveContactSubmission(payload) {
    const data = payload || {};
    const result = await apiRequest("/api/contact", {
      method: "POST",
      body: {
        name: data.name,
        email: data.email,
        message: data.message
      }
    });
    if (!result.ok) {
      return { ok: false, error: result.error };
    }
    return { ok: true, message: result.data.message || "Message sent." };
  }

  async function fetchListings() {
    const result = await apiRequest("/api/listings");
    if (!result.ok) return { ok: false, error: result.error, listings: [] };
    return { ok: true, listings: Array.isArray(result.data.listings) ? result.data.listings : [] };
  }

  async function fetchDashboard(role) {
    const normalized = normalizeRole(role);
    const path = normalized === "landlord" ? "/api/dashboard/landlord" : "/api/dashboard/tenant";
    const result = await apiRequest(path);
    if (!result.ok) return { ok: false, error: result.error };
    return { ok: true, data: result.data };
  }

  async function submitRentPayment(payload) {
    const data = payload || {};
    const result = await apiRequest("/api/workflow/payment", {
      method: "POST",
      body: {
        amount: data.amount,
        paymentMonth: data.paymentMonth,
        note: data.note || ""
      }
    });
    if (!result.ok) return { ok: false, error: result.error };
    return { ok: true, payment: result.data.payment };
  }

  async function fetchPayments() {
    const result = await apiRequest("/api/workflow/payments");
    if (!result.ok) return { ok: false, error: result.error, payments: [] };
    return { ok: true, payments: Array.isArray(result.data.payments) ? result.data.payments : [] };
  }

  async function reviewPayment(paymentId, status, note = "") {
    const id = Number(paymentId || 0);
    if (!Number.isFinite(id) || id <= 0) {
      return { ok: false, error: "Invalid payment id." };
    }
    const result = await apiRequest(`/api/workflow/payment/${id}/status`, {
      method: "POST",
      body: { status, note }
    });
    if (!result.ok) return { ok: false, error: result.error };
    return { ok: true, payment: result.data.payment };
  }

  async function createMaintenanceRequest(payload) {
    const data = payload || {};
    const result = await apiRequest("/api/workflow/maintenance", {
      method: "POST",
      body: {
        subject: data.subject,
        details: data.details,
        severity: data.severity || "medium"
      }
    });
    if (!result.ok) return { ok: false, error: result.error };
    return { ok: true, request: result.data.request };
  }

  async function fetchMaintenanceRequests() {
    const result = await apiRequest("/api/workflow/maintenance");
    if (!result.ok) return { ok: false, error: result.error, requests: [] };
    return { ok: true, requests: Array.isArray(result.data.requests) ? result.data.requests : [] };
  }

  async function updateMaintenanceStatus(requestId, status) {
    const id = Number(requestId || 0);
    if (!Number.isFinite(id) || id <= 0) {
      return { ok: false, error: "Invalid maintenance request id." };
    }
    const result = await apiRequest(`/api/workflow/maintenance/${id}/status`, {
      method: "POST",
      body: { status }
    });
    if (!result.ok) return { ok: false, error: result.error };
    return { ok: true, request: result.data.request };
  }

  root.AtlasBahamasAuth = {
    normalizeRole,
    roleHome,
    safeNextPath,
    parseQuery,
    passwordPolicyErrors,
    getSession,
    getCsrfToken,
    setSession,
    clearSession,
    ensureSeedUsers,
    registerUser,
    loginUser,
    logout,
    requireRole,
    saveContactSubmission,
    fetchListings,
    fetchDashboard,
    submitRentPayment,
    fetchPayments,
    reviewPayment,
    createMaintenanceRequest,
    fetchMaintenanceRequests,
    updateMaintenanceStatus
  };
})();
