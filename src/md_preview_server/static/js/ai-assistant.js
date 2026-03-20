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

        // 1. Get the current document path
        const filepath = docPathEl ? docPathEl.textContent.trim() : "";
        if (!filepath) {
            appendMessage("assistant", "Error: No document is currently open.");
            return;
        }

        // 2. Fetch the document content (from editor if active, otherwise fetch from server again, or read from live-preview)
        // Since the server reads from the file based on the path, we can either pass the filepath and have the server read it,
        // or we can pass the content. Let's fetch the latest content from the API if it's not currently being edited,
        // or if it is being edited we get from editor window.
        let documentContent = "";
        
        // Check if CodeMirror is active
        if (window._cmEditor && document.getElementById("editor-container").style.display !== "none") {
            documentContent = window._cmEditor.state.doc.toString();
        } else {
            // Fetch content from API
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

        // 3. Display user prompt in chat
        appendMessage("user", promptText);
        aiInput.value = "";
        aiSubmitBtn.disabled = true;
        
        // Show loading indicator
        const loadingId = appendLoading();

        try {
            // 4. Send request to backend
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
