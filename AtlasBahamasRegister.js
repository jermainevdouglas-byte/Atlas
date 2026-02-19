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

    const form = document.getElementById("atlasRegisterForm");
    const notice = document.getElementById("atlasRegisterMessage");
    const roleInput = document.getElementById("atlas-register-role");

    if (!form || !notice || !roleInput) return;

    const params = auth.parseQuery(window.location.search);
    if (params.role) roleInput.value = params.role;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submit = form.querySelector("button[type='submit']");
      if (submit) submit.disabled = true;

      const result = await auth.registerUser({
        fullName: form.full_name.value,
        email: form.email.value,
        username: form.username.value,
        role: form.role.value,
        password: form.password.value,
        passwordConfirm: form.password_confirm.value
      });

      if (!result.ok) {
        setNotice(notice, "error", `<b>Registration failed:</b> ${result.error}`);
        if (submit) submit.disabled = false;
        return;
      }

      setNotice(notice, "ok", "<b>Account created.</b> Redirecting to your dashboard...");
      window.setTimeout(() => {
        window.location.href = auth.roleHome(result.session.role);
      }, 420);
    });
  });
})();
