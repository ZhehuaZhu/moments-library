import { t } from "./i18n.js";
import {
    extensionForFile,
    fileSignature,
    previewKindForFile,
    reorderEntries,
    updateFileSummary,
} from "./composer-file-utils.js";

export function createComposerFileController({
    modal,
    fileInput,
    libraryInput,
    cameraInput,
    previewSection,
    previewList,
    signal,
    onFilesChange,
}) {
    let selectedFiles = [];
    let dragIndex = null;

    function syncInputFiles() {
        updateFileSummary(modal, selectedFiles.length);
    }

    function appendSelectedFiles(files) {
        if (!files.length) {
            return;
        }

        const existing = new Set(selectedFiles.map((entry) => fileSignature(entry.file)));
        files.forEach((file) => {
            const signature = fileSignature(file);
            if (existing.has(signature)) {
                return;
            }

            selectedFiles.push({
                id: crypto.randomUUID(),
                file,
                kind: previewKindForFile(file),
                objectUrl: URL.createObjectURL(file),
            });
            existing.add(signature);
        });

        syncInputFiles();
        renderPreviewList();
        onFilesChange();
    }

    function renderPreviewList() {
        if (!previewSection || !previewList) {
            return;
        }

        previewList.replaceChildren();

        if (!selectedFiles.length) {
            previewSection.hidden = true;
            return;
        }

        previewSection.hidden = false;

        selectedFiles.forEach((entry, index) => {
            const article = document.createElement("article");
            article.className = "composer-file-card";
            article.draggable = true;
            article.dataset.index = String(index);

            const previewButton = document.createElement("button");
            previewButton.type = "button";
            previewButton.className = "composer-file-card__preview";
            previewButton.dataset.mediaPreview = "";
            previewButton.dataset.previewGroup = "composer-draft";
            previewButton.dataset.previewKind = entry.kind;
            previewButton.dataset.previewSrc = entry.objectUrl;
            previewButton.dataset.previewTitle = entry.file.name;
            previewButton.dataset.previewMime = entry.file.type || "";
            previewButton.setAttribute(
                "aria-label",
                `${t("composer.preview", {}, "Preview")} ${entry.file.name}`,
            );
            previewButton.previewPayload = { file: entry.file };

            if (entry.kind === "image") {
                const image = document.createElement("img");
                image.src = entry.objectUrl;
                image.alt = entry.file.name;
                image.loading = "lazy";
                previewButton.append(image);
            } else if (entry.kind === "video") {
                const video = document.createElement("video");
                video.src = entry.objectUrl;
                video.muted = true;
                video.playsInline = true;
                video.preload = "metadata";
                previewButton.append(video);

                const label = document.createElement("span");
                label.className = "composer-file-card__badge";
                label.textContent = t("composer.video", {}, "Video");
                previewButton.append(label);
            } else if (entry.kind === "pdf") {
                const frame = document.createElement("embed");
                frame.src = entry.objectUrl;
                frame.type = "application/pdf";
                previewButton.append(frame);

                const label = document.createElement("span");
                label.className = "composer-file-card__badge";
                label.textContent = t("composer.pdf", {}, "PDF");
                previewButton.append(label);
            } else if (entry.kind === "docx") {
                const placeholder = document.createElement("div");
                placeholder.className = "composer-file-card__placeholder";
                placeholder.textContent = "DOCX";
                previewButton.append(placeholder);

                const label = document.createElement("span");
                label.className = "composer-file-card__badge";
                label.textContent = t("composer.preview", {}, "Preview");
                previewButton.append(label);
            } else if (entry.kind === "doc") {
                const placeholder = document.createElement("div");
                placeholder.className = "composer-file-card__placeholder";
                placeholder.textContent = "DOC";
                previewButton.append(placeholder);

                const label = document.createElement("span");
                label.className = "composer-file-card__badge";
                label.textContent = t("composer.info", {}, "Info");
                previewButton.append(label);
            } else if (entry.kind === "text") {
                const placeholder = document.createElement("div");
                placeholder.className = "composer-file-card__placeholder";
                placeholder.textContent = "TXT";
                previewButton.append(placeholder);

                const label = document.createElement("span");
                label.className = "composer-file-card__badge";
                label.textContent = t("composer.preview", {}, "Preview");
                previewButton.append(label);
            } else {
                const placeholder = document.createElement("div");
                placeholder.className = "composer-file-card__placeholder";
                placeholder.textContent = extensionForFile(entry.file).toUpperCase() || "FILE";
                previewButton.append(placeholder);

                const label = document.createElement("span");
                label.className = "composer-file-card__badge";
                label.textContent = t("composer.document", {}, "Document");
                previewButton.append(label);
            }

            const meta = document.createElement("div");
            meta.className = "composer-file-card__meta";

            const title = document.createElement("strong");
            title.textContent = entry.file.name;
            meta.append(title);

            const details = document.createElement("small");
            details.textContent = `${index + 1}. ${(entry.file.size / 1024 / 1024).toFixed(1)} MB`;
            meta.append(details);

            const actions = document.createElement("div");
            actions.className = "composer-file-card__actions";

            const moveEarlier = document.createElement("button");
            moveEarlier.type = "button";
            moveEarlier.className = "button button--ghost button--compact";
            moveEarlier.textContent = t("composer.earlier", {}, "Earlier");
            moveEarlier.disabled = index === 0;
            moveEarlier.addEventListener("click", () => {
                selectedFiles = reorderEntries(selectedFiles, index, index - 1);
                syncInputFiles();
                renderPreviewList();
                onFilesChange();
            }, { signal });

            const moveLater = document.createElement("button");
            moveLater.type = "button";
            moveLater.className = "button button--ghost button--compact";
            moveLater.textContent = t("composer.later", {}, "Later");
            moveLater.disabled = index === selectedFiles.length - 1;
            moveLater.addEventListener("click", () => {
                selectedFiles = reorderEntries(selectedFiles, index, index + 1);
                syncInputFiles();
                renderPreviewList();
                onFilesChange();
            }, { signal });

            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "button button--danger button--compact";
            remove.textContent = t("composer.remove", {}, "Remove");
            remove.addEventListener("click", () => {
                if (entry.objectUrl) {
                    URL.revokeObjectURL(entry.objectUrl);
                }
                selectedFiles = selectedFiles.filter((item) => item.id !== entry.id);
                syncInputFiles();
                renderPreviewList();
                onFilesChange();
            }, { signal });

            actions.append(moveEarlier, moveLater, remove);
            article.append(previewButton, meta, actions);

            article.addEventListener("dragstart", () => {
                dragIndex = index;
                article.classList.add("is-dragging");
            }, { signal });

            article.addEventListener("dragend", () => {
                dragIndex = null;
                article.classList.remove("is-dragging");
            }, { signal });

            article.addEventListener("dragover", (event) => {
                event.preventDefault();
                article.classList.add("is-drop-target");
            }, { signal });

            article.addEventListener("dragleave", () => {
                article.classList.remove("is-drop-target");
            }, { signal });

            article.addEventListener("drop", (event) => {
                event.preventDefault();
                article.classList.remove("is-drop-target");
                if (dragIndex === null || dragIndex === index) {
                    return;
                }
                selectedFiles = reorderEntries(selectedFiles, dragIndex, index);
                syncInputFiles();
                renderPreviewList();
                onFilesChange();
            }, { signal });

            previewList.append(article);
        });
    }

    if (fileInput) {
        updateFileSummary(modal, selectedFiles.length);
    }

    libraryInput?.addEventListener("change", () => {
        appendSelectedFiles(Array.from(libraryInput.files || []));
        if (libraryInput instanceof HTMLInputElement) {
            libraryInput.value = "";
        }
    }, { signal });

    cameraInput?.addEventListener("change", () => {
        appendSelectedFiles(Array.from(cameraInput.files || []));
        if (cameraInput instanceof HTMLInputElement) {
            cameraInput.value = "";
        }
    }, { signal });

    signal.addEventListener("abort", () => {
        selectedFiles.forEach((entry) => {
            if (entry.objectUrl) {
                URL.revokeObjectURL(entry.objectUrl);
            }
        });
    }, { once: true });

    return {
        getSelectedFiles: () => selectedFiles,
        appendSelectedFiles,
        renderPreviewList,
        syncInputFiles,
    };
}
