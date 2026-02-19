const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

async function run() {
  const file = path.join(process.cwd(), "AtlasBahamasAuth.js");
  const code = fs.readFileSync(file, "utf8");

  const events = [];
  class CustomEvent {
    constructor(type) {
      this.type = type;
    }
  }

  const sandbox = {
    console,
    URLSearchParams,
    fetch: async () => ({ ok: true, status: 200, json: async () => ({ ok: true, authenticated: false, session: null }) }),
    CustomEvent,
    dispatchEvent: (evt) => events.push(evt.type),
    location: { search: "" }
  };

  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;

  vm.runInNewContext(code, sandbox, { filename: "AtlasBahamasAuth.js" });
  const auth = sandbox.AtlasBahamasAuth;

  assert.ok(auth, "AtlasBahamasAuth export should exist");
  assert.strictEqual(auth.normalizeRole("tenant"), "tenant");
  assert.strictEqual(auth.normalizeRole("manager"), "landlord");
  assert.strictEqual(auth.roleHome("tenant"), "AtlasBahamasTenantDashboard.html");
  assert.strictEqual(auth.roleHome("landlord"), "AtlasBahamasLandlordDashboard.html");

  const parsed = auth.parseQuery("?role=landlord&next=AtlasBahamasListings.html");
  assert.strictEqual(parsed.role, "landlord");
  assert.strictEqual(parsed.next, "AtlasBahamasListings.html");

  const badNext = auth.parseQuery("?next=../../secret.txt");
  assert.strictEqual(badNext.next, "");

  const pwErrors = auth.passwordPolicyErrors("short");
  assert.ok(Array.isArray(pwErrors) && pwErrors.length > 0, "weak password should report policy errors");

  const noSession = await auth.getSession(true);
  assert.strictEqual(noSession, null, "session should be null with mocked unauthenticated response");

  await auth.logout();
  assert.ok(events.includes("atlas-auth-changed"), "logout should emit auth change event");

  console.log("AUTH_FLOW_TEST_PASS");
}

run().catch((err) => {
  console.error("AUTH_FLOW_TEST_FAIL", err && err.stack ? err.stack : err);
  process.exit(1);
});
