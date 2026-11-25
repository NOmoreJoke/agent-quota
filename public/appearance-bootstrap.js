// Synchronous, same-origin bootstrap: apply fixed appearance and motion preferences before first paint.
(() => {
  let theme = "light";
  let motion = "on";
  try {
    const saved = window.localStorage.getItem("agent-quota.appearance.v1");
    if (saved === "light" || saved === "dark") theme = saved;
    const savedMotion = window.localStorage.getItem("agent-quota.motion.v1");
    if (savedMotion === "on" || savedMotion === "off") motion = savedMotion;
  } catch { /* Unavailable preference storage falls back to defaults. */ }
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.motion = motion;
  document.documentElement.classList.toggle("floating-surface", new URLSearchParams(window.location.search).get("surface") === "floating");
})();
