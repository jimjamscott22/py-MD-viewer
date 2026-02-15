/**
 * Live reload via Server-Sent Events.
 * Supports event types: file_modified, tree_changed.
 * In edit mode, shows notification instead of auto-reloading.
 */
function initLiveReload(currentFile) {
    var normalizedCurrent = currentFile.replace(/\\/g, "/");
    var evtSource = new EventSource("/events");

    evtSource.onmessage = function (event) {
        var data = JSON.parse(event.data);
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

    evtSource.onerror = function () {
        console.log("SSE connection lost, reconnecting in 3s...");
        evtSource.close();
        setTimeout(function () {
            initLiveReload(currentFile);
        }, 3000);
    };
}
