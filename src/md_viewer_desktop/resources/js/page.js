// Runs inside every rendered document page (mdview://doc/...).
// Renders Mermaid and KaTeX from the vendored copies and lets the Qt side
// switch themes without a reload via window.mdviewSetTheme(name).
// window.mdviewRendering is true while Mermaid is drawing (print waits on it);
// mdviewHeadings()/mdviewScrollTo(id) back the Contents panel.
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
        window.mdviewRendering = true;
        Promise.resolve(window.mermaid.run({ nodes: nodes })).then(done, done);
        function done() { window.mdviewRendering = false; }
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

    window.mdviewHeadings = function () {
        if (!container) return [];
        var nodes = container.querySelectorAll("h1, h2, h3, h4, h5, h6");
        return Array.prototype.filter.call(nodes, function (node) {
            return node.id;
        }).map(function (node) {
            return [Number(node.tagName.charAt(1)), node.id, node.textContent.trim()];
        });
    };

    window.mdviewScrollTo = function (id) {
        var node = document.getElementById(id);
        if (node) node.scrollIntoView({ block: "start" });
    };

    window.mdviewRendering = false;
    renderMath();
    renderMermaid();
})();
