// Sends a first visit of the picker to the reader's own language.
// Only on the picker page, only once a session (so "back" to the picker
// stays on the picker), and the links on the page work without it.
(function () {
  var have = ["en", "pl", "ru", "es"];
  try {
    if (sessionStorage.getItem("primitive-wiki-picked")) return;
    sessionStorage.setItem("primitive-wiki-picked", "1");
  } catch (e) { /* storage blocked: still redirect once */ }
  var langs = navigator.languages || [navigator.language || "en"];
  for (var i = 0; i < langs.length; i++) {
    var code = String(langs[i] || "").slice(0, 2).toLowerCase();
    if (have.indexOf(code) >= 0) {
      location.replace(code + "/");
      return;
    }
  }
})();
