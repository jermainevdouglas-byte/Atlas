(() => {
  document.addEventListener("DOMContentLoaded", async () => {
    const auth = window.AtlasBahamasAuth;
    if (!auth) return;

    await auth.ensureSeedUsers();

    const session = auth.getSession();
    const continueWrap = document.querySelector("[data-session-continue]");

    if (session && continueWrap) {
      const home = auth.roleHome(session.role);
      continueWrap.innerHTML = `
        <a class="secondary-btn" href="${home}">Continue as ${session.fullName}</a>
      `;
    }
  });
})();
