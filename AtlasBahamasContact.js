(() => {
  function setNotice(el, kind, html) {
    if (!el) return;
    const cls = kind === "error" ? "notice err" : kind === "ok" ? "notice ok" : "notice";
    el.innerHTML = `<div class="${cls}">${html}</div>`;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const auth = window.AtlasBahamasAuth;
    const form = document.getElementById("atlasContactForm");
    const notice = document.getElementById("atlasContactMessage");

    if (!auth || !form || !notice) return;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const payload = {
        name: form.name.value,
        email: form.email.value,
        message: form.message.value
      };

      if (!payload.name.trim() || !payload.email.trim() || !payload.message.trim()) {
        setNotice(notice, "error", "<b>Message not sent:</b> All contact fields are required.");
        return;
      }

      const result = await auth.saveContactSubmission(payload);
      if (!result.ok) {
        setNotice(notice, "error", `<b>Message not sent:</b> ${result.error}`);
        return;
      }

      form.reset();
      setNotice(notice, "ok", "<b>Message sent.</b> Your note was saved for follow-up.");
    });
  });
})();
