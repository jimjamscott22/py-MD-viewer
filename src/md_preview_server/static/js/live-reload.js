/**
 * Live reload via Server-Sent Events.
 * Only reloads when the currently viewed file changes.
 */
function initLiveReload(currentFile) {
    var normalizedCurrent = currentFile.replace(/\\/g, "/");
    var evtSource = new EventSource("/events");

    evtSource.onmessage = function (event) {
        var data = JSON.parse(event.data);
        var changedFile = data.file.replace(/\\/g, "/");
        if (changedFile === normalizedCurrent) {
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
