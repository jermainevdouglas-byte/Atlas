(() => {
  document.addEventListener("DOMContentLoaded", () => {
    const links = document.querySelectorAll("[data-role-door]");
    if (!links.length) return;

    links.forEach((link) => {
      link.addEventListener("click", (event) => {
        const href = link.getAttribute("href");
        if (!href) return;

        event.preventDefault();
        link.classList.add("opening");
        document.body.classList.add("door-open");

        window.setTimeout(() => {
          window.location.href = href;
        }, 180);
      });
    });
  });
})();
