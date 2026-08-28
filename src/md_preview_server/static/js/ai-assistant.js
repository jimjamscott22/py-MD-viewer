/**
 * ai-assistant.js
 * Handles the AI Assistant chat interface interaction.
 */

document.addEventListener("DOMContentLoaded", () => {
    const aiForm = document.getElementById("ai-assistant-form");
    const aiInput = document.getElementById("ai-assistant-input");
    const aiHistory = document.getElementById("ai-assistant-history");
    const aiSubmitBtn = document.getElementById("ai-assistant-submit");
    const docPathEl = document.querySelector(".doc-path");

    if (!aiForm) return;

    aiForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const promptText = aiInput.value.trim();
        if (!promptText) return;

        // Use the active editor tab's in-memory content, including unsaved edits.
        // Outside edit mode, fall back to the current document's saved content.
        let filepath = docPathEl ? docPathEl.textContent.trim() : "";
        let documentContent = "";
        const editor = window.mdEditor;
        const editorActive = editor && editor.isActive();

        if (editorActive) {
            filepath = editor.getActivePath();
            documentContent = editor.getActiveContent();
        }

        if (!filepath) {
            appendMessage("assistant", "Error: No document is currently open.");
            return;
        }

        if (!editorActive) {
            try {
                const res = await fetch(`/api/content/${filepath}`);
                if (res.ok) {
                    const data = await res.json();
                    documentContent = data.content;
                } else {
                    documentContent = document.getElementById("view-container").innerText;
                }
            } catch (err) {
                documentContent = document.getElementById("view-container").innerText;
            }
        }

        // Display user prompt in chat
        appendMessage("user", promptText);
        aiInput.value = "";
        aiSubmitBtn.disabled = true;
        
        // Show loading indicator
        const loadingId = appendLoading();

        try {
            // Send request to backend
            const response = await fetch("/api/ai/ask", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    prompt: promptText,
                    document_content: documentContent
                })
            });

            removeLoading(loadingId);
            aiSubmitBtn.disabled = false;

            const result = await response.json();

            if (response.ok && result.success) {
                appendMessage("assistant", result.response);
            } else {
                appendMessage("assistant", "Error: " + (result.error || "Failed to get response"));
            }

        } catch (error) {
            removeLoading(loadingId);
            aiSubmitBtn.disabled = false;
            appendMessage("assistant", "Network Error: Could not connect to AI endpoint.");
        }
    });

    aiInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            aiForm.dispatchEvent(new Event("submit"));
        }
    });

    function appendMessage(role, text) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `ai-msg ai-msg-${role}`;
        
        // Basic markdown formatting for assistant responses (bold, code blocks)
        let formattedText = escapeHtml(text)
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');

        msgDiv.innerHTML = `<div class="ai-msg-bubble">${formattedText}</div>`;
        aiHistory.appendChild(msgDiv);
        aiHistory.scrollTop = aiHistory.scrollHeight;
    }

    let loadingCounter = 0;
    function appendLoading() {
        loadingCounter++;
        const id = "ai-loading-" + loadingCounter;
        const msgDiv = document.createElement("div");
        msgDiv.className = `ai-msg ai-msg-assistant ai-loading`;
        msgDiv.id = id;
        msgDiv.innerHTML = `<div class="ai-msg-bubble"><span class="ai-dot"></span><span class="ai-dot"></span><span class="ai-dot"></span></div>`;
        aiHistory.appendChild(msgDiv);
        aiHistory.scrollTop = aiHistory.scrollHeight;
        return id;
    }

    function removeLoading(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }
});
