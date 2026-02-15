/**
 * Split-pane markdown editor with CodeMirror 6 and live preview.
 */
var _cmView = null;
var _filePath = "";
var _lastModified = "";
var _isDirty = false;

function initEditor(filepath) {
    _filePath = filepath;

    var toggleBtn = document.getElementById("edit-toggle-btn");
    var viewContainer = document.getElementById("view-container");
    var editorContainer = document.getElementById("editor-container");
    var saveBtn = document.getElementById("save-btn");
    var statusEl = document.getElementById("editor-status");

    if (!toggleBtn) return;

    toggleBtn.addEventListener("click", function () {
        var isEditing = editorContainer.style.display !== "none";
        if (isEditing) {
            // Switch to view mode
            exitEditMode();
        } else {
            // Switch to edit mode
            enterEditMode();
        }
    });

    function enterEditMode() {
        window._editorActive = true;
        viewContainer.style.display = "none";
        editorContainer.style.display = "";
        toggleBtn.textContent = "View";
        toggleBtn.classList.add("active");

        // Load content
        fetch("/api/content/" + encodeURI(_filePath))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                _lastModified = data.modified;
                loadCodeMirror(data.content);
            })
            .catch(function () {
                if (window.showToast) window.showToast("Failed to load file content", "error");
            });
    }

    function exitEditMode() {
        if (_isDirty) {
            if (!confirm("You have unsaved changes. Discard them?")) return;
        }
        window._editorActive = false;
        editorContainer.style.display = "none";
        viewContainer.style.display = "";
        toggleBtn.textContent = "Edit";
        toggleBtn.classList.remove("active");
        _isDirty = false;
        // Reload to get fresh rendered content
        location.reload();
    }

    // Save
    if (saveBtn) {
        saveBtn.addEventListener("click", doSave);
    }

    // Ctrl+S
    document.addEventListener("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === "s") {
            if (window._editorActive) {
                e.preventDefault();
                doSave();
            }
        }
    });

    function doSave() {
        if (!_cmView) return;
        var content = _cmView.state.doc.toString();
        statusEl.textContent = "Saving...";

        fetch("/api/save", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                path: _filePath,
                content: content,
                last_modified: _lastModified,
            }),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    _lastModified = data.modified;
                    _isDirty = false;
                    statusEl.textContent = "Saved";
                    saveBtn.classList.remove("unsaved");
                    if (window.showToast) window.showToast("Saved", "success");
                } else if (data.error === "conflict") {
                    statusEl.textContent = "Conflict!";
                    if (window.showToast) {
                        window.showToast("File was modified externally. Your version is still in the editor.", "error");
                    }
                    // Update last_modified so next save will work
                    _lastModified = data.server_modified;
                } else {
                    statusEl.textContent = "Error";
                    if (window.showToast) window.showToast(data.error || "Save failed", "error");
                }
            })
            .catch(function () {
                statusEl.textContent = "Error";
                if (window.showToast) window.showToast("Network error", "error");
            });
    }

    // Live preview debounce
    var previewTimer = null;
    function requestPreview() {
        clearTimeout(previewTimer);
        previewTimer = setTimeout(function () {
            if (!_cmView) return;
            var content = _cmView.state.doc.toString();
            fetch("/api/preview", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content: content }),
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var preview = document.getElementById("live-preview");
                    if (preview) preview.innerHTML = data.html;
                });
        }, 500);
    }

    // Load CodeMirror 6 dynamically from CDN
    function loadCodeMirror(content) {
        var editorPane = document.getElementById("editor-pane");
        editorPane.innerHTML = "";

        // Use dynamic import for ES module CDN
        var script = document.createElement("script");
        script.type = "module";
        script.textContent = "\n\
import {EditorView, basicSetup} from 'https://cdn.jsdelivr.net/npm/codemirror@6.65.7/+esm';\n\
import {markdown} from 'https://cdn.jsdelivr.net/npm/@codemirror/lang-markdown@6.3.1/+esm';\n\
import {EditorState} from 'https://cdn.jsdelivr.net/npm/@codemirror/state@6.5.2/+esm';\n\
\n\
var updateListener = EditorView.updateListener.of(function(update) {\n\
    if (update.docChanged) {\n\
        window._editorDirty();\n\
        window._editorPreview();\n\
    }\n\
});\n\
\n\
var state = EditorState.create({\n\
    doc: " + JSON.stringify(content) + ",\n\
    extensions: [\n\
        basicSetup,\n\
        markdown(),\n\
        updateListener,\n\
        EditorView.lineWrapping,\n\
        EditorView.theme({\n\
            '&': { height: '100%' },\n\
            '.cm-scroller': { overflow: 'auto' },\n\
            '.cm-content': { fontFamily: 'SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace', fontSize: '14px' },\n\
        }),\n\
    ],\n\
});\n\
\n\
var view = new EditorView({ state: state, parent: document.getElementById('editor-pane') });\n\
window._cmView = view;\n\
// Trigger initial preview\n\
window._editorPreview();\n\
";
        document.body.appendChild(script);
    }

    // Expose callbacks for the ES module
    window._editorDirty = function () {
        _isDirty = true;
        if (statusEl) statusEl.textContent = "Unsaved changes";
        if (saveBtn) saveBtn.classList.add("unsaved");
    };

    window._editorPreview = requestPreview;

    // Expose _cmView setter
    Object.defineProperty(window, "_cmView", {
        set: function (v) { _cmView = v; },
        get: function () { return _cmView; },
        configurable: true,
    });

    // Split divider drag
    initSplitDivider();
}

function initSplitDivider() {
    var divider = document.getElementById("split-divider");
    if (!divider) return;

    var splitPane = divider.parentElement;
    var isDragging = false;

    divider.addEventListener("mousedown", function (e) {
        isDragging = true;
        e.preventDefault();
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
    });

    document.addEventListener("mousemove", function (e) {
        if (!isDragging) return;
        var rect = splitPane.getBoundingClientRect();
        var offset = e.clientX - rect.left;
        var pct = (offset / rect.width) * 100;
        pct = Math.max(20, Math.min(80, pct));
        splitPane.style.gridTemplateColumns = pct + "% 4px " + (100 - pct) + "%";
    });

    document.addEventListener("mouseup", function () {
        if (isDragging) {
            isDragging = false;
            document.body.style.cursor = "";
            document.body.style.userSelect = "";
        }
    });
}
