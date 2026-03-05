/**
 * File operations: upload (drag-drop), create, rename, delete.
 */
(function () {
    // --- Sidebar tree rendering ---
    function escapeHtmlStr(text) {
        var div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function renderTreeHTML(tree, currentPath) {
        var keys = Object.keys(tree).sort();
        var html = '<ul class="file-tree">';
        keys.forEach(function (name) {
            var node = tree[name];
            if (typeof node === "object" && node !== null) {
                html += '<li class="directory">';
                html += '<span class="folder-toggle" onclick="this.parentElement.classList.toggle(\'collapsed\')">';
                html += '<span class="icon folder-icon"></span>';
                html += '<span class="name">' + escapeHtmlStr(name) + '</span>';
                html += '</span>';
                html += renderTreeHTML(node, currentPath);
                html += '</li>';
            } else {
                var isActive = node === currentPath ? " active" : "";
                html += '<li class="file' + isActive + '" data-path="' + escapeHtmlStr(node) + '">';
                html += '<span class="icon file-icon"></span>';
                html += '<a href="/view/' + encodeURI(node) + '">' + escapeHtmlStr(name) + '</a>';
                html += '<span class="file-actions">';
                html += '<button class="file-action-btn" data-action="rename" data-path="' + escapeHtmlStr(node) + '" title="Rename">&#x270F;</button>';
                html += '<button class="file-action-btn" data-action="delete" data-path="' + escapeHtmlStr(node) + '" title="Delete">&#x2716;</button>';
                html += '</span>';
                html += '</li>';
            }
        });
        html += '</ul>';
        return html;
    }

    function refreshSidebar() {
        fetch("/api/files")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var sidebarTree = document.getElementById("sidebar-tree");
                if (!sidebarTree) return;
                // Detect current filepath from the active file or URL
                var currentPath = "";
                var match = window.location.pathname.match(/^\/view\/(.+)/);
                if (match) currentPath = decodeURI(match[1]);
                var html = '<div class="sidebar-section"><h3>Files</h3>';
                if (data.tree && Object.keys(data.tree).length > 0) {
                    html += renderTreeHTML(data.tree, currentPath);
                } else {
                    html += '<p class="empty-message">No markdown files found.</p>';
                }
                html += '</div>';
                sidebarTree.innerHTML = html;
            });
    }

    // Expose globally for editor.js
    window.refreshSidebar = refreshSidebar;

    // --- Toast notifications ---
    window.showToast = function (message, type) {
        type = type || "info";
        var container = document.getElementById("toast-container");
        var toast = document.createElement("div");
        toast.className = "toast toast-" + type;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(function () {
            toast.classList.add("toast-fade");
            setTimeout(function () { toast.remove(); }, 300);
        }, 3000);
    };

    // --- Modal helpers ---
    function openModal(id) {
        document.getElementById(id).style.display = "flex";
    }

    function closeModal(id) {
        document.getElementById(id).style.display = "none";
    }

    // Close modal buttons
    document.querySelectorAll("[data-modal]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            closeModal(btn.getAttribute("data-modal"));
        });
    });

    // Close on overlay click
    document.querySelectorAll(".modal-overlay").forEach(function (overlay) {
        overlay.addEventListener("click", function (e) {
            if (e.target === overlay) {
                overlay.style.display = "none";
            }
        });
    });

    // --- New file ---
    var newFileBtn = document.getElementById("new-file-btn");
    if (newFileBtn) {
        newFileBtn.addEventListener("click", function () {
            document.getElementById("new-file-path").value = "";
            document.getElementById("new-file-content").value = "";
            openModal("new-file-modal");
            document.getElementById("new-file-path").focus();
        });
    }

    var createBtn = document.getElementById("create-file-btn");
    if (createBtn) {
        createBtn.addEventListener("click", function () {
            var path = document.getElementById("new-file-path").value.trim();
            var content = document.getElementById("new-file-content").value;
            if (!path) {
                showToast("Please enter a file path", "error");
                return;
            }
            fetch("/api/create", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path: path, content: content }),
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        closeModal("new-file-modal");
                        showToast("Created " + data.path, "success");
                        window.location.href = "/view/" + encodeURI(data.path);
                    } else {
                        showToast(data.error || "Failed to create file", "error");
                    }
                })
                .catch(function () {
                    showToast("Network error", "error");
                });
        });
    }

    // --- Rename ---
    var _renamePath = "";

    document.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-action='rename']");
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        _renamePath = btn.getAttribute("data-path");
        document.getElementById("rename-old-path").value = _renamePath;
        document.getElementById("rename-new-path").value = _renamePath;
        openModal("rename-modal");
        var input = document.getElementById("rename-new-path");
        input.focus();
        input.select();
    });

    var renameConfirmBtn = document.getElementById("rename-confirm-btn");
    if (renameConfirmBtn) {
        renameConfirmBtn.addEventListener("click", function () {
            var newPath = document.getElementById("rename-new-path").value.trim();
            if (!newPath) {
                showToast("Please enter a new path", "error");
                return;
            }
            fetch("/api/rename", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ old_path: _renamePath, new_path: newPath }),
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        closeModal("rename-modal");
                        showToast("Renamed to " + data.new_path, "success");
                        window.location.href = "/view/" + encodeURI(data.new_path);
                    } else {
                        showToast(data.error || "Failed to rename", "error");
                    }
                })
                .catch(function () {
                    showToast("Network error", "error");
                });
        });
    }

    // --- Delete ---
    var _deletePath = "";

    document.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-action='delete']");
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        _deletePath = btn.getAttribute("data-path");
        document.getElementById("delete-file-name").textContent = _deletePath;
        openModal("delete-modal");
    });

    var deleteConfirmBtn = document.getElementById("delete-confirm-btn");
    if (deleteConfirmBtn) {
        deleteConfirmBtn.addEventListener("click", function () {
            fetch("/api/delete", {
                method: "DELETE",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ paths: [_deletePath], confirm: true }),
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success && data.deleted.length > 0) {
                        closeModal("delete-modal");
                        showToast("Deleted " + _deletePath, "success");
                        window.location.href = "/";
                    } else {
                        var errMsg = data.errors && data.errors.length > 0
                            ? data.errors[0].error
                            : (data.error || "Failed to delete");
                        showToast(errMsg, "error");
                    }
                })
                .catch(function () {
                    showToast("Network error", "error");
                });
        });
    }

    // --- Drag-and-drop upload ---
    var dragCounter = 0;
    var overlay = document.getElementById("upload-overlay");

    document.addEventListener("dragenter", function (e) {
        e.preventDefault();
        dragCounter++;
        if (dragCounter === 1) {
            overlay.style.display = "flex";
        }
    });

    document.addEventListener("dragleave", function (e) {
        e.preventDefault();
        dragCounter--;
        if (dragCounter === 0) {
            overlay.style.display = "none";
        }
    });

    document.addEventListener("dragover", function (e) {
        e.preventDefault();
    });

    document.addEventListener("drop", function (e) {
        e.preventDefault();
        dragCounter = 0;
        overlay.style.display = "none";

        var files = e.dataTransfer.files;
        if (!files || files.length === 0) return;

        var formData = new FormData();
        var count = 0;
        for (var i = 0; i < files.length; i++) {
            if (files[i].name.toLowerCase().endsWith(".md")) {
                formData.append("files", files[i]);
                count++;
            }
        }
        if (count === 0) {
            showToast("Only .md files can be uploaded", "error");
            return;
        }

        fetch("/api/upload", { method: "POST", body: formData })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.uploaded && data.uploaded.length > 0) {
                    showToast("Uploaded " + data.uploaded.length + " file(s)", "success");
                    refreshSidebar();
                }
                if (data.errors && data.errors.length > 0) {
                    data.errors.forEach(function (err) {
                        showToast(err.name + ": " + err.error, "error");
                    });
                }
            })
            .catch(function () {
                showToast("Upload failed", "error");
            });
    });

    // --- Shared SSE connection (used by live-reload.js too) ---
    function connectSSE() {
        var evtSource = new EventSource("/events");
        window._sharedSSE = evtSource;

        evtSource.onmessage = function (event) {
            var data = JSON.parse(event.data);

            if (data.type === "tree_changed") {
                refreshSidebar();
                return;
            }

            // Delegate to live-reload handler if registered
            if (window._onSSEMessage) {
                window._onSSEMessage(data);
            }
        };

        evtSource.onerror = function () {
            evtSource.close();
            window._sharedSSE = null;
            setTimeout(connectSSE, 3000);
        };
    }

    connectSSE();
})();
