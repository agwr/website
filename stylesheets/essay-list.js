(function () {
  const list = document.getElementById("post-links");
  if (!list) return;

  let resizeFrame;

  function updateTimeVisibility() {
    list.classList.remove("hide-times");

    const wraps = Array.from(list.children).some((item) => {
      const lineHeight = parseFloat(getComputedStyle(item).lineHeight);
      return item.getBoundingClientRect().height > lineHeight * 1.5;
    });

    list.classList.toggle("hide-times", wraps);
  }

  function scheduleUpdate() {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(updateTimeVisibility);
  }

  window.addEventListener("resize", scheduleUpdate);
  document.fonts?.ready.then(scheduleUpdate);
  scheduleUpdate();
})();
