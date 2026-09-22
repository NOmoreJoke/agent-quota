// Synchronous, same-origin bootstrap: apply the fixed appearance preference before first paint.
(() => {
  let theme = "light";
  try {
    const saved = window.localStorage.getItem("agent-quota.appearance.v1");
    if (saved === "light" || saved === "dark") theme = saved;
  } catch { /* Unavailable preference storage falls back to light. */ }
  document.documentElement.dataset.theme = theme;
  document.documentElement.classList.toggle("floating-surface", new URLSearchParams(window.location.search).get("surface") === "floating");
})();
