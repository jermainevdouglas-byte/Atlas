(() => {
  const root = typeof window !== "undefined" ? window : globalThis;
  const USERS_KEY = "atlasbahamas_users_v1";
  const SESSION_KEY = "atlasbahamas_session_v1";
  const CONTACT_KEY = "atlasbahamas_contact_submissions_v1";

  function getStorage(customStorage) {
    if (customStorage) return customStorage;
    if (root.localStorage) return root.localStorage;

    const mem = {};
    return {
      getItem: (k) => (Object.prototype.hasOwnProperty.call(mem, k) ? mem[k] : null),
      setItem: (k, v) => {
        mem[k] = String(v);
      },
      removeItem: (k) => {
        delete mem[k];
      }
    };
  }

  function readJson(storage, key, fallback) {
    try {
      const raw = storage.getItem(key);
      if (!raw) return fallback;
      return JSON.parse(raw);
    } catch {
      return fallback;
    }
  }

  function writeJson(storage, key, value) {
    storage.setItem(key, JSON.stringify(value));
  }

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

  function randomSalt(bytes = 16) {
    const n = Math.max(8, Number(bytes) || 16);
    const arr = new Uint8Array(n);

    if (root.crypto && typeof root.crypto.getRandomValues === "function") {
      root.crypto.getRandomValues(arr);
    } else {
      for (let i = 0; i < arr.length; i += 1) {
        arr[i] = Math.floor(Math.random() * 256);
      }
    }

    return Array.from(arr, (v) => v.toString(16).padStart(2, "0")).join("");
  }

  async function hashText(text) {
    const value = String(text || "");

    if (root.crypto && root.crypto.subtle && typeof root.crypto.subtle.digest === "function") {
      const encoded = new TextEncoder().encode(value);
      const digest = await root.crypto.subtle.digest("SHA-256", encoded);
      return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
    }

    let hash = 2166136261;
    for (let i = 0; i < value.length; i += 1) {
      hash ^= value.charCodeAt(i);
      hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
    }
    return (hash >>> 0).toString(16).padStart(8, "0");
  }

  async function hashPassword(password, salt) {
    return hashText(`${salt}::${String(password || "")}`);
  }

  function dispatchAuthChange() {
    try {
      if (typeof root.dispatchEvent === "function" && typeof root.CustomEvent === "function") {
        root.dispatchEvent(new root.CustomEvent("atlas-auth-changed"));
      }
    } catch {
      // Ignore event dispatch errors for non-browser contexts.
    }
  }

  function getUsers(options = {}) {
    const storage = getStorage(options.storage);
    const list = readJson(storage, USERS_KEY, []);
    return Array.isArray(list) ? list : [];
  }

  function saveUsers(users, options = {}) {
    const storage = getStorage(options.storage);
    writeJson(storage, USERS_KEY, Array.isArray(users) ? users : []);
  }

  function getSession(options = {}) {
    const storage = getStorage(options.storage);
    const session = readJson(storage, SESSION_KEY, null);
    if (!session || typeof session !== "object") return null;
    if (!session.role || !session.username) return null;
    return session;
  }

  function setSession(session, options = {}) {
    const storage = getStorage(options.storage);
    writeJson(storage, SESSION_KEY, session);
    dispatchAuthChange();
    return session;
  }

  function logout(options = {}) {
    const storage = getStorage(options.storage);
    storage.removeItem(SESSION_KEY);
    dispatchAuthChange();
  }

  async function ensureSeedUsers(options = {}) {
    const users = getUsers(options);
    if (users.length > 0) return users;

    const seeds = [
      {
        id: "seed-tenant",
        fullName: "Atlas Tenant Demo",
        email: "tenant@atlasbahamas.demo",
        username: "tenantdemo",
        role: "tenant",
        salt: randomSalt(16),
        createdAt: new Date().toISOString(),
        seeded: true
      },
      {
        id: "seed-landlord",
        fullName: "Atlas Landlord Demo",
        email: "landlord@atlasbahamas.demo",
        username: "landlorddemo",
        role: "landlord",
        salt: randomSalt(16),
        createdAt: new Date().toISOString(),
        seeded: true
      }
    ];

    seeds[0].passwordHash = await hashPassword("AtlasTenant!2026", seeds[0].salt);
    seeds[1].passwordHash = await hashPassword("AtlasLandlord!2026", seeds[1].salt);

    saveUsers(seeds, options);
    return seeds;
  }

  async function registerUser(payload, options = {}) {
    const data = payload || {};
    const fullName = String(data.fullName || "").trim();
    const email = String(data.email || "").trim().toLowerCase();
    const username = String(data.username || "").trim().toLowerCase();
    const password = String(data.password || "");
    const passwordConfirm = String(data.passwordConfirm || "");
    const role = normalizeRole(data.role);

    if (!fullName || !email || !username || !password || !passwordConfirm || !role) {
      return { ok: false, error: "All registration fields are required." };
    }

    if (password !== passwordConfirm) {
      return { ok: false, error: "Passwords must match." };
    }

    const policyErrors = passwordPolicyErrors(password);
    if (policyErrors.length > 0) {
      return { ok: false, error: `Password must include: ${policyErrors.join(", ")}.` };
    }

    const users = getUsers(options);
    const duplicate = users.find(
      (u) => String(u.username || "").toLowerCase() === username || String(u.email || "").toLowerCase() === email
    );
    if (duplicate) {
      return { ok: false, error: "Username or email already exists." };
    }

    const salt = randomSalt(16);
    const passwordHash = await hashPassword(password, salt);

    const nextUser = {
      id: `usr-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`,
      fullName,
      email,
      username,
      role,
      salt,
      passwordHash,
      createdAt: new Date().toISOString(),
      seeded: false
    };

    users.push(nextUser);
    saveUsers(users, options);

    const session = {
      userId: nextUser.id,
      fullName: nextUser.fullName,
      username: nextUser.username,
      role: nextUser.role,
      loginAt: new Date().toISOString()
    };
    setSession(session, options);

    return { ok: true, user: nextUser, session };
  }

  async function loginUser(payload, options = {}) {
    const data = payload || {};
    const identifier = String(data.identifier || "").trim().toLowerCase();
    const password = String(data.password || "");
    const expectedRole = normalizeRole(data.role);

    if (!identifier || !password) {
      return { ok: false, error: "Username/email and password are required." };
    }

    await ensureSeedUsers(options);
    const users = getUsers(options);
    const user = users.find((u) => {
      const email = String(u.email || "").toLowerCase();
      const username = String(u.username || "").toLowerCase();
      return email === identifier || username === identifier;
    });

    if (!user) {
      return { ok: false, error: "Invalid credentials." };
    }

    if (expectedRole && normalizeRole(user.role) !== expectedRole) {
      return { ok: false, error: "Selected role does not match this account." };
    }

    const computedHash = await hashPassword(password, user.salt);
    if (computedHash !== user.passwordHash) {
      return { ok: false, error: "Invalid credentials." };
    }

    const session = {
      userId: user.id,
      fullName: user.fullName,
      username: user.username,
      role: normalizeRole(user.role),
      loginAt: new Date().toISOString()
    };

    setSession(session, options);
    return { ok: true, session, user };
  }

  function requireRole(role, options = {}) {
    const session = getSession(options);
    if (!session) return { ok: false, reason: "unauthenticated", session: null };

    const expected = normalizeRole(role);
    if (!expected) return { ok: true, reason: "ok", session };

    if (normalizeRole(session.role) !== expected) {
      return { ok: false, reason: "forbidden", session };
    }

    return { ok: true, reason: "ok", session };
  }

  function saveContactSubmission(payload, options = {}) {
    const storage = getStorage(options.storage);
    const current = readJson(storage, CONTACT_KEY, []);
    const entries = Array.isArray(current) ? current : [];

    entries.push({
      id: `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      name: String(payload.name || "").trim(),
      email: String(payload.email || "").trim(),
      message: String(payload.message || "").trim(),
      createdAt: new Date().toISOString()
    });

    writeJson(storage, CONTACT_KEY, entries);
    return entries[entries.length - 1];
  }

  root.AtlasBahamasAuth = {
    USERS_KEY,
    SESSION_KEY,
    CONTACT_KEY,
    normalizeRole,
    roleHome,
    safeNextPath,
    parseQuery,
    passwordPolicyErrors,
    hashPassword,
    ensureSeedUsers,
    getUsers,
    saveUsers,
    getSession,
    setSession,
    logout,
    registerUser,
    loginUser,
    requireRole,
    saveContactSubmission
  };
})();
