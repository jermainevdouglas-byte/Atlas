(() => {
  function showToast(title, message) {
    const toast = document.getElementById("atlasToast");
    if (!toast) return;

    const titleNode = toast.querySelector(".toast-title");
    const msgNode = toast.querySelector(".toast-msg");
    if (titleNode) titleNode.textContent = title;
    if (msgNode) msgNode.textContent = message;

    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2500);
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const auth = window.AtlasBahamasAuth;
    if (!auth) return;

    await auth.ensureSeedUsers();

    const root = document.querySelector("[data-dashboard-root]");
    if (!root) return;

    const expectedRole = root.getAttribute("data-role") || "";
    const gate = auth.requireRole(expectedRole);

    if (!gate.ok) {
      const role = auth.normalizeRole(expectedRole);
      const loginHref = `AtlasBahamasLogin.html?role=${encodeURIComponent(role)}&next=${encodeURIComponent(window.location.pathname.split("/").pop())}`;
      root.innerHTML = `
        <div class="card unauthorized">
          <h2>Authentication required</h2>
          <p class="muted">Please sign in with a ${role || "valid"} account to access this dashboard.</p>
          <div><a class="primary-btn" href="${loginHref}">Go to Login</a></div>
        </div>
      `;
      return;
    }

    const session = gate.session;
    const welcome = document.querySelector("[data-welcome-name]");
    if (welcome) welcome.textContent = session.fullName;

    const actions = document.querySelectorAll("[data-dashboard-action]");
    actions.forEach((button) => {
      button.addEventListener("click", () => {
        const title = button.getAttribute("data-title") || "Action logged";
        const message = button.getAttribute("data-message") || "This workflow is active and ready for backend integration.";
        showToast(title, message);
      });
    });
  });
})();
