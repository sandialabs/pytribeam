(function () {
  const key = "pytribeam-pdoc-theme";

  function systemTheme() {
    return window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function currentTheme() {
    return localStorage.getItem(key) || "auto";
  }

  function resolvedTheme() {
    const theme = currentTheme();
    return theme === "auto" ? systemTheme() : theme;
  }

  function applyTheme() {
    document.documentElement.setAttribute("data-theme", resolvedTheme());
  }

  function nextTheme() {
    const theme = currentTheme();

    if (theme === "auto") {
      localStorage.setItem(key, "light");
    } else if (theme === "light") {
      localStorage.setItem(key, "dark");
    } else {
      localStorage.setItem(key, "auto");
    }

    applyTheme();
    updateButton();
  }

  function updateButton() {
    const button = document.getElementById("pdoc-theme-toggle");
    if (!button) return;

    const theme = currentTheme();
    button.textContent = `Theme: ${theme}`;
    button.title = "Click to cycle theme: auto → light → dark";
  }

  function addButton() {
    const button = document.createElement("button");
    button.id = "pdoc-theme-toggle";
    button.type = "button";
    button.addEventListener("click", nextTheme);
    document.body.appendChild(button);
    updateButton();
  }

  applyTheme();

  document.addEventListener("DOMContentLoaded", function () {
    addButton();

    if (window.matchMedia) {
      window
        .matchMedia("(prefers-color-scheme: dark)")
        .addEventListener("change", function () {
          if (currentTheme() === "auto") {
            applyTheme();
          }
        });
    }
  });
})();