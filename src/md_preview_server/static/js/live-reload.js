/**
 * Live reload via shared Server-Sent Events connection.
 * Hooks into the SSE created by file-operations.js.
 * Supports event types: file_modified, tree_changed.
 * In edit mode, shows notification instead of auto-reloading.
 */
function initLiveReload(currentFile) {
    var normalizedCurrent = currentFile.replace(/\\/g, "/");

    // Register handler on the shared SSE connection from file-operations.js
    window._onSSEMessage = function (data) {
        var changedFile = (data.file || "").replace(/\\/g, "/");

        // If in edit mode, don't auto-reload — notify instead
        if (window._editorActive && changedFile === normalizedCurrent) {
            if (window.showToast) {
                window.showToast("File changed on disk. Save your work or reload.", "info");
            }
            return;
        }

        if (data.type === "file_modified" && changedFile === normalizedCurrent) {
            location.reload();
        }
    };
}
