(() => {
  function showToast(title, message) {
    const toast = document.getElementById("atlasToast");
    if (!toast) return;

    const titleNode = toast.querySelector(".toast-title");
    const msgNode = toast.querySelector(".toast-msg");
    if (titleNode) titleNode.textContent = title;
    if (msgNode) msgNode.textContent = message;

    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2400);
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const auth = window.AtlasBahamasAuth;
    if (!auth) return;

    await auth.ensureSeedUsers();
    let session = await auth.getSession();

    window.addEventListener("atlas-auth-changed", async () => {
      session = await auth.getSession(true);
    });

    const buttons = document.querySelectorAll("[data-listing-action]");

    buttons.forEach((button) => {
      button.addEventListener("click", async () => {
        const listingName = button.getAttribute("data-listing-name") || "Listing";
        if (!session) {
          window.location.href = "AtlasBahamasLogin.html?next=AtlasBahamasListings.html";
          return;
        }

        showToast("Request queued", `${listingName} request sent under ${session.fullName}.`);
      });
    });
  });
})();
