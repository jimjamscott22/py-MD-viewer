/**
 * File operations: upload (drag-drop), create, rename, delete.
 */
(function () {
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
                    setTimeout(function () { location.reload(); }, 500);
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

    // --- SSE: listen for tree changes to refresh sidebar ---
    var sseForTree = new EventSource("/events");
    sseForTree.onmessage = function (event) {
        var data = JSON.parse(event.data);
        if (data.type === "tree_changed") {
            // Reload the whole page to refresh sidebar tree
            location.reload();
        }
    };
    sseForTree.onerror = function () {
        sseForTree.close();
        // Don't reconnect — the view-level live-reload handles that
    };
})();
