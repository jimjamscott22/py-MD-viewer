/**
 * Sidebar search, tree controls, and file metadata.
 */
(function () {
    var searchInput = document.getElementById("search-input");
    var sidebarTree = document.getElementById("sidebar-tree");
    var searchResults = document.getElementById("search-results");
    var expandBtn = document.getElementById("expand-all-btn");
    var collapseBtn = document.getElementById("collapse-all-btn");
    var debounceTimer = null;

    // --- Search ---
    if (searchInput) {
        searchInput.addEventListener("input", function () {
            clearTimeout(debounceTimer);
            var query = searchInput.value.trim();
            if (!query) {
                sidebarTree.style.display = "";
                searchResults.style.display = "none";
                searchResults.innerHTML = "";
                return;
            }
            debounceTimer = setTimeout(function () {
                fetch("/api/search?q=" + encodeURIComponent(query))
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        sidebarTree.style.display = "none";
                        searchResults.style.display = "";
                        if (data.results.length === 0) {
                            searchResults.innerHTML = '<p class="empty-message">No results found.</p>';
                            return;
                        }
                        var html = '<ul class="file-tree">';
                        data.results.forEach(function (f) {
                            var size = formatSize(f.size);
                            var modified = formatDate(f.modified);
                            html += '<li class="file">';
                            html += '<span class="icon file-icon"></span>';
                            html += '<a href="/view/' + encodeURI(f.path) + '">' + escapeHtml(f.name) + '</a>';
                            html += '<span class="file-meta" title="' + size + ' &middot; ' + modified + '">' + size + '</span>';
                            html += '</li>';
                        });
                        html += '</ul>';
                        searchResults.innerHTML = html;
                    });
            }, 300);
        });

        // Clear search on Escape
        searchInput.addEventListener("keydown", function (e) {
            if (e.key === "Escape") {
                searchInput.value = "";
                searchInput.dispatchEvent(new Event("input"));
                searchInput.blur();
            }
        });
    }

    // --- Tree controls ---
    if (expandBtn) {
        expandBtn.addEventListener("click", function () {
            document.querySelectorAll(".file-tree .directory").forEach(function (d) {
                d.classList.remove("collapsed");
            });
        });
    }
    if (collapseBtn) {
        collapseBtn.addEventListener("click", function () {
            document.querySelectorAll(".file-tree .directory").forEach(function (d) {
                d.classList.add("collapsed");
            });
        });
    }

    // --- Helpers ---
    function formatSize(bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }

    function formatDate(iso) {
        var d = new Date(iso);
        return d.toLocaleDateString() + " " + d.toLocaleTimeString();
    }

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }
})();
