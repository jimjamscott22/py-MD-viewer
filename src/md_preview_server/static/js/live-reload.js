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

        if (data.type !== "file_modified") return;

        var editor = window.mdEditor;
        if (editor && editor.isActive()) {
            var activePath = (editor.getActivePath() || "").replace(/\\/g, "/");
            if (changedFile === activePath) {
                editor.handleFileModified(changedFile, data.revision || null);
            }
            // Never reload the page underneath an active editing session.
            return;
        }

        if (changedFile === normalizedCurrent) {
            location.reload();
        }
    };
}
