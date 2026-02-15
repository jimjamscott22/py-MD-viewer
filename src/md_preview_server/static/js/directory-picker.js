/**
 * Directory picker: browse and switch base directory.
 */
(function () {
    var dirPickerBtn = document.getElementById("dir-picker-btn");
    var dirPathInput = document.getElementById("dir-path-input");
    var dirGoBtn = document.getElementById("dir-go-btn");
    var dirList = document.getElementById("dir-list");
    var dirCurrentPath = document.getElementById("dir-current-path");
    var dirInfo = document.getElementById("dir-info");
    var dirApplyBtn = document.getElementById("dir-apply-btn");
    var currentBrowsePath = "";

    if (!dirPickerBtn) return;

    dirPickerBtn.addEventListener("click", function () {
        document.getElementById("dir-picker-modal").style.display = "flex";
        // Load current base directory
        fetch("/api/files")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                browseDirectory(data.base_dir);
            });
    });

    dirGoBtn.addEventListener("click", function () {
        var path = dirPathInput.value.trim();
        if (path) browseDirectory(path);
    });

    dirPathInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            dirGoBtn.click();
        }
    });

    dirApplyBtn.addEventListener("click", function () {
        if (!currentBrowsePath) return;
        fetch("/api/set-base-directory", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: currentBrowsePath }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    document.getElementById("dir-picker-modal").style.display = "none";
                    window.showToast("Switched to " + data.base_dir + " (" + data.file_count + " files)", "success");
                    window.location.href = "/";
                } else {
                    window.showToast(data.error || "Failed to switch directory", "error");
                }
            })
            .catch(function () {
                window.showToast("Network error", "error");
            });
    });

    function browseDirectory(path) {
        fetch("/api/directories?path=" + encodeURIComponent(path))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.current) {
                    window.showToast(data.error || "Cannot browse this directory", "error");
                    return;
                }
                currentBrowsePath = data.current;
                dirPathInput.value = data.current;
                dirCurrentPath.textContent = data.current;
                dirInfo.textContent = data.md_count + " markdown file(s) in this directory";

                var html = "";
                if (data.parent) {
                    html += '<li class="dir-item dir-parent" data-path="' + escapeAttr(data.parent) + '">';
                    html += '<span class="dir-item-icon">..</span>';
                    html += '<span class="dir-item-name">Parent directory</span>';
                    html += '</li>';
                }
                data.directories.forEach(function (d) {
                    html += '<li class="dir-item" data-path="' + escapeAttr(d.path) + '">';
                    html += '<span class="dir-item-icon">&#x1F4C1;</span>';
                    html += '<span class="dir-item-name">' + escapeHtml(d.name) + '</span>';
                    html += '</li>';
                });
                if (!data.parent && data.directories.length === 0) {
                    html = '<li class="dir-item-empty">No subdirectories</li>';
                }
                dirList.innerHTML = html;
            })
            .catch(function () {
                window.showToast("Failed to browse directory", "error");
            });
    }

    // Click handler for directory items (delegated)
    dirList.addEventListener("click", function (e) {
        var item = e.target.closest(".dir-item");
        if (!item) return;
        var path = item.getAttribute("data-path");
        if (path) browseDirectory(path);
    });

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function escapeAttr(text) {
        return text.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
})();
