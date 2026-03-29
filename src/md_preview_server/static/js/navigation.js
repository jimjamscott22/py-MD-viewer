/**
 * Sidebar navigation, search, theme controls, and view-page enhancements.
 */
(function () {
    var storageKey = "md-preview-theme";
    var root = document.documentElement;
    var searchInput = document.getElementById("search-input");
    var sidebarTree = document.getElementById("sidebar-tree");
    var searchResults = document.getElementById("search-results");
    var expandBtn = document.getElementById("expand-all-btn");
    var collapseBtn = document.getElementById("collapse-all-btn");
    var themeToggleBtn = document.getElementById("theme-toggle-btn");
    var debounceTimer = null;

    initTheme();
    initSearch();
    initTreeControls();
    initKeyboardShortcuts();
    initSidebarAutoClose();
    initDocumentTools();
    initExportButtons();

    function initTheme() {
        var savedTheme = localStorage.getItem(storageKey);
        var theme = savedTheme || "day";

        applyTheme(theme);

        if (!themeToggleBtn) {
            return;
        }

        themeToggleBtn.addEventListener("click", function () {
            var nextTheme = root.getAttribute("data-theme") === "night" ? "day" : "night";
            localStorage.setItem(storageKey, nextTheme);
            applyTheme(nextTheme);
        });
    }

    function applyTheme(theme) {
        var label = "☀️";
        if (theme === "night") {
            root.setAttribute("data-theme", "night");
            label = "🌙";
        } else {
            root.removeAttribute("data-theme");
            label = "☀️";
        }

        if (themeToggleBtn) {
            themeToggleBtn.innerHTML = label;
            themeToggleBtn.setAttribute("title", theme === "night" ? "Switch to Day Mode" : "Switch to Night Mode");
        }
    }

    function initSearch() {
        if (!searchInput) {
            return;
        }

        searchInput.addEventListener("input", function () {
            clearTimeout(debounceTimer);
            var query = searchInput.value.trim();
            if (!query) {
                resetSearch();
                return;
            }

            debounceTimer = setTimeout(function () {
                fetch("/api/search?q=" + encodeURIComponent(query))
                    .then(function (response) { return response.json(); })
                    .then(function (data) {
                        sidebarTree.style.display = "none";
                        searchResults.style.display = "";

                        if (!data.results || data.results.length === 0) {
                            searchResults.innerHTML = '<p class="empty-message">No results found.</p>';
                            return;
                        }

                        var html = '<ul class="file-tree">';
                        data.results.forEach(function (file) {
                            var size = formatSize(file.size);
                            var modified = formatDate(file.modified);
                            html += '<li class="file">';
                            html += '<span class="icon file-icon"></span>';
                            html += '<a href="/view/' + encodeURI(file.path) + '">' + escapeHtml(file.name) + '</a>';
                            html += '<span class="file-meta" title="' + size + ' | ' + modified + '">' + size + '</span>';
                            html += "</li>";
                        });
                        html += "</ul>";
                        searchResults.innerHTML = html;
                    });
            }, 220);
        });

        searchInput.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                searchInput.value = "";
                resetSearch();
                searchInput.blur();
            }
        });
    }

    function resetSearch() {
        if (!sidebarTree || !searchResults) {
            return;
        }

        sidebarTree.style.display = "";
        searchResults.style.display = "none";
        searchResults.innerHTML = "";
    }

    function initTreeControls() {
        if (expandBtn) {
            expandBtn.addEventListener("click", function () {
                document.querySelectorAll(".file-tree .directory").forEach(function (directory) {
                    directory.classList.remove("collapsed");
                });
            });
        }

        if (collapseBtn) {
            collapseBtn.addEventListener("click", function () {
                document.querySelectorAll(".file-tree .directory").forEach(function (directory) {
                    directory.classList.add("collapsed");
                });
            });
        }
    }

    function initKeyboardShortcuts() {
        document.addEventListener("keydown", function (event) {
            var target = event.target;
            var isTyping = target && (
                target.tagName === "INPUT" ||
                target.tagName === "TEXTAREA" ||
                target.isContentEditable
            );

            if (event.key === "/" && !isTyping && searchInput) {
                event.preventDefault();
                searchInput.focus();
                searchInput.select();
            }
        });
    }

    function initSidebarAutoClose() {
        document.addEventListener("click", function (event) {
            var link = event.target.closest(".file a");
            var sidebar = document.getElementById("sidebar");
            if (!link || !sidebar || window.innerWidth > 768) {
                return;
            }
            sidebar.classList.remove("open");
        });
    }

    function initDocumentTools() {
        var article = document.getElementById("view-container");
        if (!article) {
            return;
        }

        updateDocumentStats(article);
        buildOutline(article);
        initReadingProgress(article);
        initCopyPath();
    }

    function updateDocumentStats(article) {
        var text = article.textContent || "";
        var words = text.trim().split(/\s+/).filter(Boolean).length;
        var headings = article.querySelectorAll("h1, h2, h3, h4, h5, h6").length;
        var minutes = Math.max(1, Math.ceil(words / 220));

        setText("doc-word-count", words + " words");
        setText("doc-reading-time", minutes + " min read");
        setText("doc-heading-count", headings + " section" + (headings === 1 ? "" : "s"));
    }

    function buildOutline(article) {
        var outlineContainer = document.getElementById("doc-outline");
        if (!outlineContainer) {
            return;
        }

        var headings = Array.prototype.slice.call(article.querySelectorAll("h1, h2, h3, h4, h5, h6"));
        if (headings.length === 0) {
            outlineContainer.innerHTML = '<p class="empty-message">No headings found yet.</p>';
            return;
        }

        var usedIds = {};
        var list = document.createElement("ul");
        list.className = "doc-outline-list";

        headings.forEach(function (heading) {
            if (!heading.id) {
                heading.id = createSlug(heading.textContent || "section", usedIds);
            } else {
                usedIds[heading.id] = true;
            }

            var item = document.createElement("li");
            item.className = "doc-outline-item depth-" + heading.tagName.substring(1);

            var link = document.createElement("a");
            link.href = "#" + heading.id;
            link.textContent = heading.textContent.replace("#", "").trim();
            link.dataset.target = heading.id;

            item.appendChild(link);
            list.appendChild(item);
        });

        outlineContainer.innerHTML = "";
        outlineContainer.appendChild(list);
        highlightActiveOutlineLink(headings);
    }

    function highlightActiveOutlineLink(headings) {
        var outlineLinks = Array.prototype.slice.call(document.querySelectorAll(".doc-outline-item a"));
        if (outlineLinks.length === 0) {
            return;
        }

        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) {
                    return;
                }

                outlineLinks.forEach(function (link) {
                    link.classList.toggle("is-active", link.dataset.target === entry.target.id);
                });
            });
        }, {
            rootMargin: "0px 0px -70% 0px",
            threshold: 0.15,
        });

        headings.forEach(function (heading) {
            observer.observe(heading);
        });
    }

    function initReadingProgress(article) {
        var progressBar = document.getElementById("reading-progress");
        if (!progressBar) {
            return;
        }

        progressBar.classList.add("is-active");

        function update() {
            var rect = article.getBoundingClientRect();
            var total = Math.max(article.offsetHeight - window.innerHeight, 1);
            var progressed = Math.min(Math.max(-rect.top, 0), total);
            var ratio = progressed / total;
            progressBar.style.setProperty("--progress-scale", ratio.toFixed(4));
        }

        update();
        window.addEventListener("scroll", update, { passive: true });
        window.addEventListener("resize", update);
    }

    function initCopyPath() {
        var copyButton = document.getElementById("copy-path-btn");
        if (!copyButton) {
            return;
        }

        copyButton.addEventListener("click", function () {
            var path = copyButton.getAttribute("data-path") || "";
            if (!path) {
                return;
            }

            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(path)
                    .then(function () {
                        if (window.showToast) {
                            window.showToast("Copied " + path, "success");
                        }
                    })
                    .catch(function () {
                        fallbackCopy(path);
                    });
                return;
            }

            fallbackCopy(path);
        });
    }

    function fallbackCopy(text) {
        var temp = document.createElement("textarea");
        temp.value = text;
        document.body.appendChild(temp);
        temp.select();
        document.execCommand("copy");
        temp.remove();
        if (window.showToast) {
            window.showToast("Copied " + text, "success");
        }
    }

    function setText(id, value) {
        var element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    function createSlug(text, usedIds) {
        var base = text
            .toLowerCase()
            .replace(/[^a-z0-9\s-]/g, "")
            .trim()
            .replace(/\s+/g, "-") || "section";
        var slug = base;
        var counter = 2;

        while (usedIds[slug]) {
            slug = base + "-" + counter;
            counter += 1;
        }

        usedIds[slug] = true;
        return slug;
    }

    function formatSize(bytes) {
        if (bytes < 1024) {
            return bytes + " B";
        }
        if (bytes < 1024 * 1024) {
            return (bytes / 1024).toFixed(1) + " KB";
        }
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }

    function formatDate(iso) {
        var date = new Date(iso);
        return date.toLocaleDateString() + " " + date.toLocaleTimeString();
    }

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function initExportButtons() {
        var exportHtmlBtn = document.getElementById("export-html-btn");
        var exportPdfBtn = document.getElementById("export-pdf-btn");

        if (exportHtmlBtn) {
            exportHtmlBtn.addEventListener("click", function () {
                var path = exportHtmlBtn.getAttribute("data-path");
                if (!path) return;
                var a = document.createElement("a");
                a.href = "/api/export/html/" + encodeURI(path);
                a.download = "";
                document.body.appendChild(a);
                a.click();
                a.remove();
                if (window.showToast) {
                    window.showToast("Downloading HTML export", "success");
                }
            });
        }

        if (exportPdfBtn) {
            exportPdfBtn.addEventListener("click", function () {
                if (window.showToast) {
                    window.showToast("Opening print dialog", "success");
                }
                window.print();
            });
        }
    }
})();
