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
    let pointerSortState = null;

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
            article.className = "composer-file-card composer-file-card--compact";
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

            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "composer-file-card__remove";
            remove.setAttribute("aria-label", t("composer.remove", {}, "Remove"));
            remove.textContent = "\u00d7";
            remove.addEventListener("click", () => {
                if (entry.objectUrl) {
                    URL.revokeObjectURL(entry.objectUrl);
                }
                selectedFiles = selectedFiles.filter((item) => item.id !== entry.id);
                syncInputFiles();
                renderPreviewList();
                onFilesChange();
            }, { signal });

            const orderBadge = document.createElement("span");
            orderBadge.className = "composer-file-card__order";
            orderBadge.textContent = String(index + 1);

            const dragHandle = document.createElement("button");
            dragHandle.type = "button";
            dragHandle.className = "composer-file-card__drag";
            dragHandle.setAttribute("aria-label", t("composer.reorder", {}, "Drag to reorder"));
            dragHandle.innerHTML = "&#8942;&#8942;";

            dragHandle.addEventListener("pointerdown", (event) => {
                if (!(event instanceof PointerEvent) || event.button !== 0) {
                    return;
                }

                pointerSortState = {
                    pointerId: event.pointerId,
                    article,
                    index,
                    targetIndex: index,
                    startX: event.clientX,
                    startY: event.clientY,
                    active: false,
                };

                dragHandle.setPointerCapture?.(event.pointerId);
                event.preventDefault();
            }, { signal });

            article.append(previewButton, orderBadge, remove, dragHandle);

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

    function clearPointerSortState() {
        previewList?.querySelectorAll(".is-drop-target").forEach((node) => {
            node.classList.remove("is-drop-target");
        });
        previewList?.classList.remove("is-sorting");
        if (pointerSortState?.article instanceof HTMLElement) {
            pointerSortState.article.classList.remove("is-pointer-dragging");
            pointerSortState.article.style.removeProperty("transform");
            pointerSortState.article.style.removeProperty("z-index");
        }
        pointerSortState = null;
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

    document.addEventListener("pointermove", (event) => {
        if (!pointerSortState || event.pointerId !== pointerSortState.pointerId) {
            return;
        }

        const deltaX = event.clientX - pointerSortState.startX;
        const deltaY = event.clientY - pointerSortState.startY;

        if (!pointerSortState.active && Math.hypot(deltaX, deltaY) > 6) {
            pointerSortState.active = true;
            pointerSortState.article.classList.add("is-pointer-dragging");
            previewList?.classList.add("is-sorting");
        }

        if (!pointerSortState.active) {
            return;
        }

        pointerSortState.article.style.transform = `translate3d(${deltaX}px, ${deltaY}px, 0)`;
        pointerSortState.article.style.zIndex = "4";

        previewList?.querySelectorAll(".is-drop-target").forEach((node) => {
            if (node !== pointerSortState.article) {
                node.classList.remove("is-drop-target");
            }
        });

        const hovered = document.elementFromPoint(event.clientX, event.clientY)?.closest(".composer-file-card");
        if (!(hovered instanceof HTMLElement) || hovered === pointerSortState.article) {
            return;
        }

        const targetIndex = Number(hovered.dataset.index || "");
        if (Number.isInteger(targetIndex) && targetIndex >= 0) {
            pointerSortState.targetIndex = targetIndex;
            hovered.classList.add("is-drop-target");
        }
    }, { signal });

    const finishPointerSort = (event) => {
        if (!pointerSortState || event.pointerId !== pointerSortState.pointerId) {
            return;
        }

        const { active, index, targetIndex } = pointerSortState;
        clearPointerSortState();

        if (!active || targetIndex === index) {
            return;
        }

        selectedFiles = reorderEntries(selectedFiles, index, targetIndex);
        syncInputFiles();
        renderPreviewList();
        onFilesChange();
    };

    document.addEventListener("pointerup", finishPointerSort, { signal });
    document.addEventListener("pointercancel", finishPointerSort, { signal });

    signal.addEventListener("abort", () => {
        selectedFiles.forEach((entry) => {
            if (entry.objectUrl) {
                URL.revokeObjectURL(entry.objectUrl);
            }
        });
        clearPointerSortState();
    }, { once: true });

    return {
        getSelectedFiles: () => selectedFiles,
        appendSelectedFiles,
        renderPreviewList,
        syncInputFiles,
    };
}
