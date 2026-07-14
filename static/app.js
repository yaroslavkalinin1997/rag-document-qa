const uploadForm = document.querySelector("#upload-form");
const uploadButton = document.querySelector("#upload-button");
const uploadStatus = document.querySelector("#upload-status");
const documentInput = document.querySelector("#document-file");
const documentList = document.querySelector("#document-list");
const documentsStatus = document.querySelector("#documents-status");
const refreshDocumentsButton = document.querySelector("#refresh-documents");

const questionForm = document.querySelector("#question-form");
const questionInput = document.querySelector("#question");
const askButton = document.querySelector("#ask-button");
const questionStatus = document.querySelector("#question-status");
const answerCard = document.querySelector("#answer-card");
const answerText = document.querySelector("#answer-text");
const sourceSection = document.querySelector("#source-section");
const sourceList = document.querySelector("#source-list");

const documentDialog = document.querySelector("#document-dialog");
const dialogTitle = document.querySelector("#dialog-title");
const dialogMeta = document.querySelector("#dialog-meta");
const dialogContent = document.querySelector("#dialog-content");


async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const responseText = await response.text();
    let data = null;

    if (responseText) {
        try {
            data = JSON.parse(responseText);
        } catch {
            data = responseText;
        }
    }

    if (!response.ok) {
        const message = data?.detail || data || `Request failed with status ${response.status}`;
        throw new Error(message);
    }

    return data;
}


function setStatus(element, message = "", type = "") {
    element.textContent = message;
    element.classList.toggle("error", type === "error");
    element.classList.toggle("success", type === "success");
}


async function openDocument(documentId) {
    dialogTitle.textContent = "Loading document...";
    dialogMeta.textContent = "";
    dialogContent.textContent = "";

    if (typeof documentDialog.showModal === "function") {
        documentDialog.showModal();
    } else {
        documentDialog.setAttribute("open", "");
    }

    try {
        const documentData = await requestJson(`/documents/${encodeURIComponent(documentId)}`);
        dialogTitle.textContent = documentData.filename;
        dialogMeta.textContent = `${documentData.file_type.toUpperCase()} · ${documentData.size_bytes} bytes · ${documentData.chunk_count} chunks`;
        dialogContent.textContent = documentData.full_text;
    } catch (error) {
        dialogTitle.textContent = "Could not open document";
        dialogContent.textContent = error.message;
    }
}


async function deleteDocument(documentId, filename) {
    if (!window.confirm(`Delete “${filename}”?`)) {
        return;
    }

    try {
        await requestJson(`/documents/${encodeURIComponent(documentId)}`, {
            method: "DELETE",
        });
        await loadDocuments();
    } catch (error) {
        setStatus(documentsStatus, error.message, "error");
    }
}


function renderDocuments(documents) {
    documentList.replaceChildren();

    if (!documents.length) {
        setStatus(documentsStatus, "No documents uploaded yet.");
        return;
    }

    setStatus(documentsStatus, `${documents.length} document${documents.length === 1 ? "" : "s"}`);

    for (const documentData of documents) {
        const item = document.createElement("li");
        item.className = "document-item";

        const openButton = document.createElement("button");
        openButton.className = "document-open";
        openButton.type = "button";
        openButton.addEventListener("click", () => openDocument(documentData.id));

        const name = document.createElement("span");
        name.className = "document-name";
        name.textContent = documentData.filename;

        const details = document.createElement("span");
        details.className = "document-details";
        details.textContent = `${documentData.status} · ${documentData.chunk_count} chunks`;

        openButton.append(name, details);

        const deleteButton = document.createElement("button");
        deleteButton.className = "delete-button";
        deleteButton.type = "button";
        deleteButton.textContent = "Delete";
        deleteButton.addEventListener("click", () => {
            deleteDocument(documentData.id, documentData.filename);
        });

        item.append(openButton, deleteButton);
        documentList.append(item);
    }
}


async function loadDocuments() {
    refreshDocumentsButton.disabled = true;
    setStatus(documentsStatus, "Loading documents...");

    try {
        const documents = await requestJson("/documents");
        renderDocuments(documents);
    } catch (error) {
        setStatus(documentsStatus, error.message, "error");
    } finally {
        refreshDocumentsButton.disabled = false;
    }
}


uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const file = documentInput.files[0];

    if (!file) {
        setStatus(uploadStatus, "Select a TXT file first.", "error");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);
    uploadButton.disabled = true;
    setStatus(uploadStatus, "Uploading and indexing...");

    try {
        const result = await requestJson("/documents", {
            method: "POST",
            body: formData,
        });
        uploadForm.reset();
        setStatus(
            uploadStatus,
            `${result.filename} indexed into ${result.chunk_count} chunks.`,
            "success",
        );
        await loadDocuments();
    } catch (error) {
        setStatus(uploadStatus, error.message, "error");
    } finally {
        uploadButton.disabled = false;
    }
});


questionForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const question = questionInput.value.trim();

    if (!question) {
        setStatus(questionStatus, "Enter a question first.", "error");
        return;
    }

    askButton.disabled = true;
    answerCard.hidden = true;
    setStatus(questionStatus, "Searching documents and generating an answer...");

    try {
        const result = await requestJson("/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ question }),
        });

        answerText.textContent = result.answer;
        sourceList.replaceChildren();

        for (const source of result.sources) {
            const item = document.createElement("li");
            const button = document.createElement("button");
            button.className = "source-button";
            button.type = "button";
            button.textContent = source.filename;
            button.addEventListener("click", () => openDocument(source.document_id));
            item.append(button);
            sourceList.append(item);
        }

        sourceSection.hidden = result.sources.length === 0;
        answerCard.hidden = false;
        setStatus(questionStatus);
    } catch (error) {
        setStatus(questionStatus, error.message, "error");
    } finally {
        askButton.disabled = false;
    }
});


refreshDocumentsButton.addEventListener("click", loadDocuments);
loadDocuments();
