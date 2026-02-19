(() => {
  const doorLink = document.querySelector(".door-link");
  if (!doorLink) return;

  const targetSelector = doorLink.getAttribute("href");
  const target = targetSelector?.startsWith("#") ? document.querySelector(targetSelector) : null;

  doorLink.addEventListener("click", (event) => {
    if (!target) return;
    event.preventDefault();

    document.body.classList.add("door-open");
    window.setTimeout(() => {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 180);
  });

  const resetDoorState = () => {
    if (window.scrollY <= window.innerHeight * 0.25) {
      document.body.classList.remove("door-open");
    }
  };

  window.addEventListener("scroll", resetDoorState, { passive: true });
})();
