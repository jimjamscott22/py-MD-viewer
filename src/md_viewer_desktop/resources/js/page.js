// Runs inside every rendered document page (mdview://doc/...).
// Renders Mermaid and KaTeX from the vendored copies and lets the Qt side
// switch themes without a reload via window.mdviewSetTheme(name).
(function () {
    "use strict";

    var root = document.documentElement;
    var container = document.getElementById("view-container");

    function cssVar(name) {
        return getComputedStyle(root).getPropertyValue(name).trim();
    }

    function mermaidConfig() {
        var theme = root.getAttribute("data-theme") || "";
        if (theme === "light") return { startOnLoad: false, theme: "default" };
        if (theme === "jamielab") {
            return {
                startOnLoad: false,
                theme: "base",
                themeVariables: {
                    background: cssVar("--ground"),
                    primaryColor: cssVar("--panel"),
                    primaryTextColor: cssVar("--ink"),
                    primaryBorderColor: cssVar("--edge"),
                    lineColor: cssVar("--ink-muted"),
                    secondaryColor: cssVar("--panel"),
                    tertiaryColor: cssVar("--ground"),
                    fontFamily: '"IBM Plex Mono", ui-monospace, monospace'
                }
            };
        }
        return { startOnLoad: false, theme: "dark" };
    }

    function renderMermaid() {
        if (!window.mermaid || !container) return;
        var nodes = Array.prototype.slice.call(container.querySelectorAll(".mermaid"));
        if (!nodes.length) return;
        nodes.forEach(function (node) {
            if (node.dataset.source === undefined) {
                node.dataset.source = node.textContent;
            } else {
                node.removeAttribute("data-processed");
                node.textContent = node.dataset.source;
            }
        });
        window.mermaid.initialize(mermaidConfig());
        window.mermaid.run({ nodes: nodes });
    }

    function renderMath() {
        if (!window.renderMathInElement || !container) return;
        window.renderMathInElement(container, {
            delimiters: [
                { left: "\\[", right: "\\]", display: true },
                { left: "\\(", right: "\\)", display: false }
            ],
            throwOnError: false
        });
    }

    window.mdviewSetTheme = function (theme) {
        if (theme) {
            root.setAttribute("data-theme", theme);
        } else {
            root.removeAttribute("data-theme");
        }
        renderMermaid();
    };

    renderMath();
    renderMermaid();
})();
