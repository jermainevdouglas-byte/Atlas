(() => {
  function currentPage() {
    const rawPath = window.location.pathname || "";
    const parts = rawPath.split("/").filter(Boolean);
    const file = parts.length ? parts[parts.length - 1] : "AtlasBahamasHome.html";
    return file || "AtlasBahamasHome.html";
  }

  function isActive(page, targets) {
    return targets.includes(page) ? " active" : "";
  }

  function mountHeader() {
    const nodes = document.querySelectorAll("[data-atlas-header]");
    if (!nodes.length) return;

    const auth = window.AtlasBahamasAuth;
    const page = currentPage();
    const session = auth ? auth.getSession() : null;

    const roleLabel = session ? (session.role === "landlord" ? "Landlord" : "Tenant") : "Guest";
    const dashboardHref = session && auth ? auth.roleHome(session.role) : "AtlasBahamasLogin.html";

    const template = `
      <nav class="nav container" aria-label="Primary">
        <div class="nav-left">
          <a class="pill${isActive(page, ["AtlasBahamasLogin.html"])}" href="AtlasBahamasLogin.html">Login</a>
          <a class="pill${isActive(page, ["AtlasBahamasAbout.html"])}" href="AtlasBahamasAbout.html">About</a>
          <a class="pill${isActive(page, ["AtlasBahamasContact.html"])}" href="AtlasBahamasContact.html">Contact Us</a>
        </div>

        <a class="brand${isActive(page, ["AtlasBahamasHome.html", "index.html"])}" href="AtlasBahamasHome.html" aria-label="Go to Atlas home">Atlas</a>

        <div class="nav-right">
          <a class="pill${isActive(page, ["AtlasBahamasRegister.html"])}" href="AtlasBahamasRegister.html">Register</a>
          <a class="pill${isActive(page, ["AtlasBahamasListings.html"])}" href="AtlasBahamasListings.html">Listings</a>
          <a class="pill${isActive(page, ["AtlasBahamasTenantDashboard.html", "AtlasBahamasLandlordDashboard.html"])}" href="${dashboardHref}">Dashboard</a>
          ${session ? '<button class="pill" type="button" data-atlas-logout>Logout</button>' : ""}
          <span class="pill" aria-label="Current role">${roleLabel}</span>
        </div>
      </nav>
    `;

    nodes.forEach((node) => {
      node.innerHTML = template;
    });

    const logoutButtons = document.querySelectorAll("[data-atlas-logout]");
    logoutButtons.forEach((button) => {
      button.addEventListener("click", () => {
        if (auth) auth.logout();
        window.location.href = "AtlasBahamasHome.html";
      });
    });
  }

  document.addEventListener("DOMContentLoaded", mountHeader);
  window.addEventListener("atlas-auth-changed", mountHeader);
})();
