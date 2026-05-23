/**
 * Split-pane markdown editor with CodeMirror 6, live preview, tabs, auto-save, and more.
 */

// --- Module-level state ---
var _cmView = null;
var _filePath = "";
var _lastModified = "";
var _isDirty = false;
var _tabs = [];
var _activeTabId = null;
var _tabIdCounter = 0;
var _codeMirrorLoader = null;
var _vimLoader = null;

function loadCodeMirrorModules() {
    if (!_codeMirrorLoader) {
        _codeMirrorLoader = Promise.all([
            import("codemirror"),
            import("@codemirror/lang-markdown"),
            import("@codemirror/state")
        ]).then(function(modules) {
            return {
                EditorView: modules[0].EditorView,
                basicSetup: modules[0].basicSetup,
                markdown: modules[1].markdown,
                Compartment: modules[2].Compartment
            };
        });
    }
    return _codeMirrorLoader;
}

function loadVimModule() {
    if (!_vimLoader) {
        _vimLoader = import("@replit/codemirror-vim");
    }
    return _vimLoader;
}

function initEditor(filepath) {
    _filePath = filepath;

    var toggleBtn = document.getElementById("edit-toggle-btn");
    var viewContainer = document.getElementById("view-container");
    var docShell = document.getElementById("doc-shell");
    var readingProgress = document.getElementById("reading-progress");
    var editorContainer = document.getElementById("editor-container");
    var saveBtn = document.getElementById("save-btn");
    var statusEl = document.getElementById("editor-status");

    if (!toggleBtn) return;

    toggleBtn.addEventListener("click", function () {
        if (editorContainer.style.display !== "none") {
            exitEditMode();
        } else {
            enterEditMode();
        }
    });

    function enterEditMode() {
        window._editorActive = true;
        if (docShell) docShell.style.display = "none";
        else if (viewContainer) viewContainer.style.display = "none";
        if (readingProgress) readingProgress.style.display = "none";
        editorContainer.style.display = "";
        toggleBtn.textContent = "View";
        toggleBtn.classList.add("active");

        // Open the current file as a tab (or reactivate if already open)
        var existingTab = _tabs.find(function(t) { return t.filePath === _filePath; });
        if (existingTab) {
            _activateTab(existingTab.id);
        } else {
            _openInNewTab(_filePath);
        }
    }

    function exitEditMode() {
        if (_tabs.some(function(t) { return t.isDirty; })) {
            if (!confirm("You have unsaved changes. Discard them?")) return;
        }
        stopAutoSave();
        _autoSaveConflicts = 0;
        window._editorActive = false;

        // Destroy all tab editors
        _tabs.forEach(function(t) {
            if (t.cmView) { try { t.cmView.destroy(); } catch(e) {} }
            var pane = document.getElementById("tab-pane-" + t.id);
            if (pane) pane.remove();
        });
        _tabs = [];
        _activeTabId = null;
        window._activeTabId = null;
        var tabBar = document.getElementById("tab-bar");
        if (tabBar) tabBar.style.display = "none";

        editorContainer.style.display = "none";
        if (docShell) docShell.style.display = "";
        else if (viewContainer) viewContainer.style.display = "";
        if (readingProgress) readingProgress.style.display = "";
        toggleBtn.textContent = "Edit";
        toggleBtn.classList.remove("active");
        _isDirty = false;

        // Refresh rendered content
        var src = _cmView ? _cmView.state.doc.toString() : "";
        fetch("/api/preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: src }),
        })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (viewContainer) {
                    viewContainer.innerHTML = data.html;
                    if (window.renderDiagrams) window.renderDiagrams(viewContainer);
                }
            })
            .catch(function() { location.reload(); });
    }

    // --- Save ---
    if (saveBtn) saveBtn.addEventListener("click", doSave);

    document.addEventListener("keydown", function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === "s") {
            if (window._editorActive) { e.preventDefault(); doSave(); }
        }
    });

    function doSave() {
        if (!_cmView) return;
        var content = _cmView.state.doc.toString();
        saveSnapshot(_filePath, content, "Manual save");
        if (statusEl) statusEl.textContent = "Saving...";

        fetch("/api/save", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: _filePath, content: content, last_modified: _lastModified }),
        })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) {
                    _lastModified = data.modified;
                    _isDirty = false;
                    var activeTab = _tabs.find(function(t) { return t.id === _activeTabId; });
                    if (activeTab) { activeTab.lastModified = data.modified; activeTab.isDirty = false; }
                    if (statusEl) statusEl.textContent = "Saved";
                    if (saveBtn) saveBtn.classList.remove("unsaved");
                    if (window.showToast) window.showToast("Saved", "success");
                    _renderTabBar();
                } else if (data.error === "conflict") {
                    if (statusEl) statusEl.textContent = "Conflict!";
                    if (window.showToast) window.showToast("File modified externally. Your edits are preserved.", "error");
                    _lastModified = data.server_modified;
                } else {
                    if (statusEl) statusEl.textContent = "Error";
                    if (window.showToast) window.showToast(data.error || "Save failed", "error");
                }
            })
            .catch(function() {
                if (statusEl) statusEl.textContent = "Error";
                if (window.showToast) window.showToast("Network error", "error");
            });
    }

    // --- Live preview ---
    var previewTimer = null;
    var previewAbort = null;
    var lastPreviewedContent = null;
    function requestPreview() {
        clearTimeout(previewTimer);
        previewTimer = setTimeout(function() {
            if (!_cmView) return;
            var content = _cmView.state.doc.toString();
            if (content === lastPreviewedContent) return;
            if (previewAbort) previewAbort.abort();
            previewAbort = new AbortController();
            fetch("/api/preview", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content: content }),
                signal: previewAbort.signal,
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    lastPreviewedContent = content;
                    var preview = document.getElementById("live-preview");
                    if (preview) {
                        preview.innerHTML = data.html;
                        if (window.renderDiagrams) window.renderDiagrams(preview);
                    }
                })
                .catch(function(err) { if (err.name !== "AbortError") throw err; });
        }, 500);
    }

    // --- Keybinding mode selector ---
    var keybindingSelect = document.getElementById("keybinding-select");
    var _keybindingMode = localStorage.getItem("mdv-keybinding-mode") || "default";
    if (keybindingSelect) {
        keybindingSelect.value = _keybindingMode;
        keybindingSelect.addEventListener("change", function() {
            _keybindingMode = keybindingSelect.value;
            localStorage.setItem("mdv-keybinding-mode", _keybindingMode);
            if (window._setKeybindingMode) window._setKeybindingMode(_keybindingMode);
        });
    }

    // --- Auto-save & version history ---
    var _autoSaveTimer = null;
    var _autoSaveConflicts = 0;
    var AUTOSAVE_INTERVAL = (function() {
        var v = parseInt(localStorage.getItem("mdv-autosave-interval"), 10);
        return isNaN(v) ? 30000 : v;
    })();

    function _historyKey(path) { return "mdv-history-" + encodeURIComponent(path); }

    function saveSnapshot(path, content, label) {
        try {
            var key = _historyKey(path);
            var snapshots = JSON.parse(localStorage.getItem(key) || "[]");
            snapshots.unshift({ content: content.slice(0, 51200), timestamp: Date.now(), label: label || "Auto" });
            if (snapshots.length > 10) snapshots = snapshots.slice(0, 10);
            localStorage.setItem(key, JSON.stringify(snapshots));
        } catch(e) {}
    }

    function startAutoSave() {
        stopAutoSave();
        if (AUTOSAVE_INTERVAL <= 0) return;
        _autoSaveTimer = setInterval(function() {
            if (!_isDirty || !_cmView || _autoSaveConflicts >= 3) return;
            var content = _cmView.state.doc.toString();
            saveSnapshot(_filePath, content, "Auto");
            fetch("/api/save", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path: _filePath, content: content, last_modified: _lastModified }),
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.success) {
                        _lastModified = data.modified;
                        _isDirty = false;
                        var activeTab = _tabs.find(function(t) { return t.id === _activeTabId; });
                        if (activeTab) { activeTab.lastModified = data.modified; activeTab.isDirty = false; }
                        if (statusEl) statusEl.textContent = "Auto-saved";
                        if (saveBtn) saveBtn.classList.remove("unsaved");
                        _autoSaveConflicts = 0;
                        _renderTabBar();
                    } else if (data.error === "conflict") {
                        _autoSaveConflicts++;
                        if (_autoSaveConflicts >= 3) {
                            stopAutoSave();
                            if (window.showToast) window.showToast("Auto-save paused: file modified externally", "error");
                        }
                    }
                })
                .catch(function() {});
        }, AUTOSAVE_INTERVAL);
    }

    function stopAutoSave() {
        if (_autoSaveTimer) { clearInterval(_autoSaveTimer); _autoSaveTimer = null; }
    }

    function showHistoryPanel() {
        var panel = document.getElementById("history-panel");
        if (!panel) return;
        var list = document.getElementById("history-list");
        if (!list) return;
        var snapshots = [];
        try { snapshots = JSON.parse(localStorage.getItem(_historyKey(_filePath)) || "[]"); } catch(e) {}
        if (snapshots.length === 0) {
            list.innerHTML = '<p class="empty-message">No snapshots yet.</p>';
        } else {
            list.innerHTML = snapshots.map(function(s, i) {
                var d = new Date(s.timestamp);
                return '<div class="history-entry" data-index="' + i + '">' +
                    '<span class="history-label">' + s.label + ' — ' + d.toLocaleTimeString() + ' ' + d.toLocaleDateString() + '</span>' +
                    '<span class="history-chars">' + s.content.length + ' chars</span>' +
                    '<button class="btn btn-sm btn-secondary history-restore-btn">Restore</button>' +
                    '</div>';
            }).join('');
        }
        panel.classList.add("history-panel-open");
    }

    window._showHistoryPanel = showHistoryPanel;

    var historyPanel = document.getElementById("history-panel");
    if (historyPanel) {
        historyPanel.addEventListener("click", function(e) {
            var btn = e.target.closest(".history-restore-btn");
            if (!btn || !_cmView) return;
            var idx = parseInt(btn.closest(".history-entry").getAttribute("data-index"), 10);
            var snapshots = [];
            try { snapshots = JSON.parse(localStorage.getItem(_historyKey(_filePath)) || "[]"); } catch(ex) {}
            if (snapshots[idx]) {
                _cmView.dispatch({ changes: { from: 0, to: _cmView.state.doc.length, insert: snapshots[idx].content } });
                historyPanel.classList.remove("history-panel-open");
                if (window.showToast) window.showToast("Version restored", "success");
            }
        });
    }

    // --- Formatting toolbar ---
    var fmtToolbar = document.getElementById("formatting-toolbar");
    var fmtToggleBtn = document.getElementById("fmt-toggle-btn");

    if (localStorage.getItem("mdv-toolbar-hidden") === "1" && fmtToolbar) {
        fmtToolbar.classList.add("fmt-toolbar-hidden");
    }
    if (fmtToggleBtn) {
        fmtToggleBtn.addEventListener("click", function() {
            var hidden = fmtToolbar.classList.toggle("fmt-toolbar-hidden");
            localStorage.setItem("mdv-toolbar-hidden", hidden ? "1" : "0");
        });
    }

    function applyFormat(fmt) {
        if (!_cmView) return;
        var state = _cmView.state;
        var sel = state.selection.main;
        var selectedText = state.sliceDoc(sel.from, sel.to);
        var dispatch = _cmView.dispatch.bind(_cmView);

        function wrapInline(open, close) {
            if (selectedText) {
                dispatch({ changes: { from: sel.from, to: sel.to, insert: open + selectedText + close }, selection: { anchor: sel.from + open.length, head: sel.to + open.length } });
            } else {
                dispatch({ changes: { from: sel.from, insert: open + close }, selection: { anchor: sel.from + open.length } });
            }
        }
        function prefixLine(prefix) {
            var line = state.doc.lineAt(sel.from);
            if (line.text.startsWith(prefix)) {
                dispatch({ changes: { from: line.from, to: line.from + prefix.length, insert: "" }, selection: { anchor: Math.max(line.from, sel.from - prefix.length) } });
            } else {
                dispatch({ changes: { from: line.from, insert: prefix }, selection: { anchor: sel.from + prefix.length } });
            }
        }
        function prefixSelectedLines(prefix) {
            var fromLine = state.doc.lineAt(sel.from);
            var toLine = state.doc.lineAt(sel.to);
            var changes = [];
            for (var n = fromLine.number; n <= toLine.number; n++) {
                changes.push({ from: state.doc.line(n).from, insert: prefix });
            }
            dispatch({ changes: changes });
        }

        switch (fmt) {
            case "bold":       wrapInline("**", "**"); break;
            case "italic":     wrapInline("*", "*"); break;
            case "strike":     wrapInline("~~", "~~"); break;
            case "code":       wrapInline("`", "`"); break;
            case "h1":         prefixLine("# "); break;
            case "h2":         prefixLine("## "); break;
            case "h3":         prefixLine("### "); break;
            case "blockquote": prefixLine("> "); break;
            case "ul":         prefixSelectedLines("- "); break;
            case "ol":         prefixSelectedLines("1. "); break;
            case "hr":         dispatch({ changes: { from: sel.from, insert: "\n---\n" }, selection: { anchor: sel.from + 5 } }); break;
            case "link":
                if (selectedText) {
                    dispatch({ changes: { from: sel.from, to: sel.to, insert: "[" + selectedText + "](url)" }, selection: { anchor: sel.from + selectedText.length + 3, head: sel.from + selectedText.length + 6 } });
                } else {
                    dispatch({ changes: { from: sel.from, insert: "[text](url)" }, selection: { anchor: sel.from + 1, head: sel.from + 5 } });
                }
                break;
            case "image":     dispatch({ changes: { from: sel.from, insert: "![alt](url)" }, selection: { anchor: sel.from + 2, head: sel.from + 5 } }); break;
            case "codeblock": wrapInline("\n```\n", "\n```\n"); break;
        }
        _cmView.focus();
    }

    if (fmtToolbar) {
        fmtToolbar.addEventListener("click", function(e) {
            var btn = e.target.closest("[data-fmt]");
            if (btn) applyFormat(btn.getAttribute("data-fmt"));
        });
    }

    document.addEventListener("keydown", function(e) {
        if (!window._editorActive || !_cmView) return;
        if (e.ctrlKey || e.metaKey) {
            if (e.key === "b") { e.preventDefault(); applyFormat("bold"); }
            else if (e.key === "i") { e.preventDefault(); applyFormat("italic"); }
            else if (e.key === "k") { e.preventDefault(); applyFormat("link"); }
        }
    });

    // --- Tab management ---
    function _escHtml(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

    function _renderTabBar() {
        var bar = document.getElementById("tab-bar");
        if (!bar) return;
        if (_tabs.length <= 1) { bar.style.display = "none"; return; }
        bar.style.display = "flex";
        bar.innerHTML = _tabs.map(function(tab) {
            var name = _escHtml(tab.filePath.split('/').pop());
            var active = tab.id === _activeTabId ? " tab-active" : "";
            var dot = tab.isDirty ? '<span class="tab-dirty">●</span>' : '';
            return '<div class="tab-item' + active + '" data-tab-id="' + tab.id + '" title="' + _escHtml(tab.filePath) + '">' +
                '<span class="tab-name">' + name + dot + '</span>' +
                '<button class="tab-close-btn" data-tab-close="' + tab.id + '">×</button>' +
                '</div>';
        }).join('');
    }

    function _activateTab(id) {
        var tab = _tabs.find(function(t) { return t.id === id; });
        if (!tab) return;
        _activeTabId = id;
        window._activeTabId = id;
        _filePath = tab.filePath;
        _lastModified = tab.lastModified;
        _isDirty = tab.isDirty;
        _cmView = tab.cmView;
        _tabs.forEach(function(t) {
            var el = document.getElementById("tab-pane-" + t.id);
            if (el) el.style.display = t.id === id ? "" : "none";
        });
        if (statusEl) statusEl.textContent = _isDirty ? "Unsaved changes" : "Editing";
        if (saveBtn) saveBtn.classList.toggle("unsaved", _isDirty);
        _renderTabBar();
        setKeybindingMode(_keybindingMode);
        requestPreview();
    }

    function _closeTab(id) {
        var idx = _tabs.findIndex(function(t) { return t.id === id; });
        if (idx < 0) return;
        var tab = _tabs[idx];
        if (tab.isDirty && !confirm("Discard unsaved changes in " + tab.filePath.split('/').pop() + "?")) return;
        if (tab.cmView) { try { tab.cmView.destroy(); } catch(e) {} }
        var pane = document.getElementById("tab-pane-" + id);
        if (pane) pane.remove();
        _tabs.splice(idx, 1);
        if (_tabs.length === 0) {
            exitEditMode();
        } else if (_activeTabId === id) {
            _activateTab(_tabs[Math.min(idx, _tabs.length - 1)].id);
        } else {
            _renderTabBar();
        }
    }

    function _openInNewTab(filePath) {
        var existing = _tabs.find(function(t) { return t.filePath === filePath; });
        if (existing) { _activateTab(existing.id); return; }
        var tabId = ++_tabIdCounter;
        var tab = { id: tabId, filePath: filePath, cmView: null, isDirty: false, lastModified: "" };
        _tabs.push(tab);
        _renderTabBar();
        _activateTab(tabId);
        fetch("/api/content/" + encodeURI(filePath))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                tab.lastModified = data.modified;
                if (_activeTabId === tabId) _lastModified = data.modified;
                saveSnapshot(filePath, data.content, "Before edit");
                _loadTabEditor(tab, data.content);
                if (_activeTabId === tabId) startAutoSave();
            })
            .catch(function() {
                if (window.showToast) window.showToast("Failed to open " + filePath, "error");
            });
    }

    function _loadTabEditor(tab, content) {
        var editorPane = document.getElementById("editor-pane");
        var paneDiv = document.createElement("div");
        paneDiv.id = "tab-pane-" + tab.id;
        paneDiv.style.cssText = "height:100%;display:" + (tab.id === _activeTabId ? "" : "none") + ";";
        editorPane.appendChild(paneDiv);

        loadCodeMirrorModules()
            .then(function(cm) {
                if (!_tabs.some(function(t) { return t.id === tab.id; })) return;

                var kbComp = new cm.Compartment();
                var updateListener = cm.EditorView.updateListener.of(function(update) {
                    if (update.docChanged && window._activeTabId === tab.id) {
                        window._tabDirty(tab.id);
                        window._editorPreview();
                    }
                });
                var view = new cm.EditorView({
                    doc: content,
                    extensions: [
                        cm.basicSetup,
                        cm.markdown(),
                        updateListener,
                        cm.EditorView.lineWrapping,
                        cm.EditorView.theme({
                            "&": { height: "100%" },
                            ".cm-scroller": { overflow: "auto" },
                            ".cm-content": {
                                fontFamily: "SFMono-Regular,Consolas,Liberation Mono,Menlo,monospace",
                                fontSize: "14px"
                            }
                        }),
                        kbComp.of([])
                    ],
                    parent: paneDiv
                });

                tab.cmView = view;
                tab._kbComp = kbComp;
                if (_activeTabId === tab.id) {
                    _cmView = view;
                    setKeybindingMode(_keybindingMode);
                    requestPreview();
                }
            })
            .catch(function(error) {
                console.warn("CodeMirror load failed", error);
                if (window.showToast) window.showToast("Editor failed to load", "error");
            });
    }

    function setKeybindingMode(mode) {
        _keybindingMode = mode || "default";
        var activeTab = _tabs.find(function(t) { return t.id === _activeTabId; });
        if (!activeTab || !activeTab.cmView || !activeTab._kbComp) return;

        if (_keybindingMode !== "vim") {
            activeTab.cmView.dispatch({ effects: activeTab._kbComp.reconfigure([]) });
            return;
        }

        loadVimModule()
            .then(function(vimModule) {
                if (_activeTabId !== activeTab.id || !activeTab.cmView || !activeTab._kbComp) return;
                var ext = [vimModule.vim({ status: true })];
                vimModule.Vim.defineEx("w", "", function() { if (window._doSave) window._doSave(); });
                vimModule.Vim.defineEx("wq", "", function() { if (window._doSave) window._doSave(); });
                vimModule.Vim.defineEx("q", "", function() { if (window._exitEditor) window._exitEditor(); });
                activeTab.cmView.dispatch({ effects: activeTab._kbComp.reconfigure(ext) });
            })
            .catch(function(error) {
                console.warn("Vim load failed", error);
                if (window.showToast) window.showToast("Vim mode failed to load", "error");
            });
    }

    // Tab bar click delegation
    var tabBarEl = document.getElementById("tab-bar");
    if (tabBarEl) {
        tabBarEl.addEventListener("click", function(e) {
            var closeBtn = e.target.closest("[data-tab-close]");
            if (closeBtn) { e.stopPropagation(); _closeTab(parseInt(closeBtn.getAttribute("data-tab-close"), 10)); return; }
            var item = e.target.closest("[data-tab-id]");
            if (item) _activateTab(parseInt(item.getAttribute("data-tab-id"), 10));
        });
    }

    // Sidebar link interception: open in new tab when editor is active
    document.addEventListener("click", function(e) {
        if (!window._editorActive) return;
        var link = e.target.closest("#sidebar-tree a, #sidebar-quick-access a");
        if (!link) return;
        var href = link.getAttribute("href");
        if (!href || !href.startsWith("/view/")) return;
        e.preventDefault();
        _openInNewTab(decodeURI(href.slice(6)));
    });

    // Expose tab helpers for module scripts
    window._getTabById = function(id) { return _tabs.find(function(t) { return t.id === id; }); };
    window._activeTabId = null;
    window._tabDirty = function(tabId) {
        var tab = _tabs.find(function(t) { return t.id === tabId; });
        if (!tab) return;
        tab.isDirty = true;
        if (tabId === _activeTabId) {
            _isDirty = true;
            if (statusEl) statusEl.textContent = "Unsaved changes";
            if (saveBtn) saveBtn.classList.add("unsaved");
        }
        _renderTabBar();
    };

    // Expose callbacks for module scripts and keybinding ex-commands
    window._doSave = doSave;
    window._exitEditor = exitEditMode;
    window._editorDirty = function() {
        _isDirty = true;
        if (statusEl) statusEl.textContent = "Unsaved changes";
        if (saveBtn) saveBtn.classList.add("unsaved");
    };
    window._editorPreview = requestPreview;
    window._setKeybindingMode = setKeybindingMode;

    // Keep _cmView in sync so module scripts can write to it
    window._setCmView = function(v) { _cmView = v; };

    // Split divider drag
    initSplitDivider();
}

function initSplitDivider() {
    var divider = document.getElementById("split-divider");
    if (!divider) return;
    var splitPane = divider.parentElement;
    var isDragging = false;

    divider.addEventListener("mousedown", function(e) {
        isDragging = true;
        e.preventDefault();
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
    });
    document.addEventListener("mousemove", function(e) {
        if (!isDragging) return;
        var rect = splitPane.getBoundingClientRect();
        var pct = Math.max(20, Math.min(80, ((e.clientX - rect.left) / rect.width) * 100));
        splitPane.style.gridTemplateColumns = pct + "% 4px " + (100 - pct) + "%";
    });
    document.addEventListener("mouseup", function() {
        if (isDragging) { isDragging = false; document.body.style.cursor = ""; document.body.style.userSelect = ""; }
    });
}
