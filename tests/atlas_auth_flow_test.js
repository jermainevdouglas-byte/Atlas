const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");
const { webcrypto } = require("crypto");

function makeStorage() {
  const map = new Map();
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k)
  };
}

async function run() {
  const file = path.join(process.cwd(), "AtlasBahamasAuth.js");
  const code = fs.readFileSync(file, "utf8");

  const localStorage = makeStorage();
  const events = [];

  class CustomEvent {
    constructor(type) {
      this.type = type;
    }
  }

  const sandbox = {
    console,
    TextEncoder,
    URLSearchParams,
    crypto: webcrypto,
    localStorage,
    CustomEvent,
    dispatchEvent: (evt) => events.push(evt.type),
    location: { search: "" }
  };

  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;

  vm.runInNewContext(code, sandbox, { filename: "AtlasBahamasAuth.js" });

  const auth = sandbox.AtlasBahamasAuth;
  assert.ok(auth, "AtlasBahamasAuth should be exported");

  const seeded = await auth.ensureSeedUsers();
  assert.strictEqual(seeded.length, 2, "should seed two demo users");

  let login = await auth.loginUser({
    identifier: "tenantdemo",
    password: "AtlasTenant!2026",
    role: "tenant"
  });
  assert.strictEqual(login.ok, true, "tenant login should succeed");
  assert.strictEqual(login.session.role, "tenant");

  login = await auth.loginUser({
    identifier: "tenantdemo",
    password: "AtlasTenant!2026",
    role: "landlord"
  });
  assert.strictEqual(login.ok, false, "role mismatch should fail");

  const register = await auth.registerUser({
    fullName: "Casey Landlord",
    email: "casey.landlord@example.com",
    username: "caseyl",
    role: "landlord",
    password: "CaseyLandlord!2026",
    passwordConfirm: "CaseyLandlord!2026"
  });
  assert.strictEqual(register.ok, true, "registration should succeed");
  assert.strictEqual(register.session.role, "landlord");

  const duplicate = await auth.registerUser({
    fullName: "Duplicate User",
    email: "casey.landlord@example.com",
    username: "dupuser",
    role: "landlord",
    password: "Duplicate!2026",
    passwordConfirm: "Duplicate!2026"
  });
  assert.strictEqual(duplicate.ok, false, "duplicate email should fail");

  const gateOk = auth.requireRole("landlord");
  assert.strictEqual(gateOk.ok, true, "landlord gate should pass after landlord login");

  const gateNo = auth.requireRole("tenant");
  assert.strictEqual(gateNo.ok, false, "tenant gate should fail after landlord login");

  auth.logout();
  assert.strictEqual(auth.getSession(), null, "session should be cleared on logout");

  assert.ok(events.includes("atlas-auth-changed"), "auth event should be emitted");

  console.log("AUTH_FLOW_TEST_PASS");
}

run().catch((err) => {
  console.error("AUTH_FLOW_TEST_FAIL", err && err.stack ? err.stack : err);
  process.exit(1);
});
