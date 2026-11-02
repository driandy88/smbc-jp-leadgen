// Score and Field are the original static design pages. Their nav rail posts to the app shell.
document.addEventListener("click", function (e) {
  var b = e.target.closest && e.target.closest("button");
  if (!b) return;
  var to = null;
  if (/sign out/i.test(b.getAttribute("aria-label") || "")) to = "login";
  var m = (b.textContent || "").replace(/\s+/g, " ").trim().match(/^0[1-3] (Scout|Score|Field)$/);
  if (m) to = m[1].toLowerCase();
  if (!to) return;
  e.preventDefault();
  e.stopPropagation();
  window.parent.postMessage({ type: "hexline-nav", to: to }, window.location.origin);
}, true);
