(() => {
  function setNotice(el, kind, html) {
    if (!el) return;
    const cls = kind === "error" ? "notice err" : kind === "ok" ? "notice ok" : "notice";
    el.innerHTML = `<div class="${cls}">${html}</div>`;
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const auth = window.AtlasBahamasAuth;
    if (!auth) return;

    await auth.ensureSeedUsers();

    const form = document.getElementById("atlasLoginForm");
    const notice = document.getElementById("atlasLoginMessage");
    const roleInput = document.getElementById("atlas-login-role");
    const hint = document.getElementById("atlasLoginHint");

    if (!form || !notice || !roleInput || !hint) return;

    const params = auth.parseQuery(window.location.search);
    if (params.role) roleInput.value = params.role;

    if (params.role === "landlord") {
      hint.textContent = "Landlord door selected. Use your landlord account credentials to continue.";
    } else if (params.role === "tenant") {
      hint.textContent = "Tenant door selected. Use your tenant account credentials to continue.";
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const submit = form.querySelector("button[type='submit']");
      if (submit) submit.disabled = true;

      const result = await auth.loginUser({
        identifier: form.identifier.value,
        password: form.password.value,
        role: roleInput.value
      });

      if (!result.ok) {
        setNotice(notice, "error", `<b>Login failed:</b> ${result.error}`);
        if (submit) submit.disabled = false;
        return;
      }

      const target = params.next || auth.roleHome(result.session.role);
      setNotice(notice, "ok", `<b>Welcome back.</b> Redirecting to your dashboard...`);
      window.setTimeout(() => {
        window.location.href = target;
      }, 380);
    });
  });
})();
