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
    documentInput,
    cameraInput,
    previewSection,
    previewList,
    signal,
    onFilesChange,
}) {
    let selectedFiles = [];
    let dragIndex = null;
    let pointerSortState = null;
    let suppressPreviewClick = false;

    function getPreviewCards() {
        return Array.from(previewList?.querySelectorAll(".composer-file-card") || []);
    }

    function animatePreviewLayout(mutator, { skip = null } = {}) {
        if (!(previewList instanceof HTMLElement)) {
            mutator();
            return;
        }

        const cards = getPreviewCards();
        const firstRects = new Map(cards.map((card) => [card, card.getBoundingClientRect()]));
        mutator();
        const lastRects = new Map(cards.map((card) => [card, card.getBoundingClientRect()]));

        cards.forEach((card) => {
            if (!(card instanceof HTMLElement) || card === skip) {
                return;
            }

            const firstRect = firstRects.get(card);
            const lastRect = lastRects.get(card);
            if (!firstRect || !lastRect) {
                return;
            }

            const deltaX = firstRect.left - lastRect.left;
            const deltaY = firstRect.top - lastRect.top;
            if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) {
                return;
            }

            card.getAnimations().forEach((animation) => animation.cancel());
            card.animate(
                [
                    { transform: `translate(${deltaX}px, ${deltaY}px)` },
                    { transform: "translate(0, 0)" },
                ],
                {
                    duration: 180,
                    easing: "cubic-bezier(0.22, 1, 0.36, 1)",
                },
            );
        });
    }

    function applyPointerSortPreview(fromIndex, toIndex) {
        if (!(previewList instanceof HTMLElement)) {
            return;
        }

        const previewOrder = reorderEntries(
            selectedFiles.map((_, index) => index),
            fromIndex,
            toIndex,
        );
        const orderMap = new Map(previewOrder.map((originalIndex, previewIndex) => [originalIndex, previewIndex]));

        animatePreviewLayout(() => {
            previewList.querySelectorAll(".composer-file-card[data-index]").forEach((node) => {
                if (!(node instanceof HTMLElement)) {
                    return;
                }
                const originalIndex = Number(node.dataset.index || "");
                const previewIndex = orderMap.get(originalIndex);
                if (!Number.isInteger(originalIndex) || previewIndex === undefined) {
                    return;
                }

                node.style.order = String(previewIndex);
                node.classList.toggle("is-sort-preview", previewIndex !== originalIndex);
                node.classList.toggle(
                    "is-drop-target",
                    previewIndex === toIndex && originalIndex !== fromIndex,
                );
            });
        }, { skip: pointerSortState?.article ?? null });
    }

    function resetPreviewOrder({ animate = false, skip = null } = {}) {
        const reset = () => {
            previewList?.querySelectorAll(".composer-file-card[data-index]").forEach((node) => {
                if (!(node instanceof HTMLElement)) {
                    return;
                }
                node.style.removeProperty("order");
                node.classList.remove("is-sort-preview");
                node.classList.remove("is-drop-target");
            });
        };

        if (animate) {
            animatePreviewLayout(reset, { skip });
            return;
        }
        reset();
    }

    function triggerPicker(input) {
        if (!(input instanceof HTMLInputElement)) {
            return;
        }
        if (typeof input.showPicker === "function") {
            input.showPicker();
            return;
        }
        input.click();
    }

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

    function startPointerSort(event, article, index, { immediate = false } = {}) {
        if (!(event instanceof PointerEvent) || event.button !== 0) {
            return;
        }

        const pointerId = event.pointerId;
        const state = {
            pointerId,
            article,
            index,
            targetIndex: index,
            startX: event.clientX,
            startY: event.clientY,
            pointerOffsetX: 0,
            pointerOffsetY: 0,
            active: false,
            activationTimer: null,
        };

        const activate = () => {
            if (pointerSortState !== state) {
                return;
            }
            const rect = article.getBoundingClientRect();
            state.pointerOffsetX = event.clientX - rect.left;
            state.pointerOffsetY = event.clientY - rect.top;
            state.active = true;
            article.classList.add("is-pointer-dragging");
            previewList?.classList.add("is-sorting");
            suppressPreviewClick = true;
        };

        pointerSortState = state;
        if (immediate) {
            activate();
        } else {
            state.activationTimer = window.setTimeout(activate, 180);
        }

        event.currentTarget?.setPointerCapture?.(pointerId);
        event.preventDefault();
    }

    function renderPreviewList() {
        if (!previewSection || !previewList) {
            return;
        }

        previewList.replaceChildren();
        previewSection.hidden = selectedFiles.length === 0;
        if (!selectedFiles.length) {
            return;
        }

        selectedFiles.forEach((entry, index) => {
            const article = document.createElement("article");
            article.className = "composer-file-card composer-file-card--compact";
            article.draggable = true;
            article.dataset.index = String(index);
            article.style.order = String(index);

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
            previewButton.addEventListener("pointerdown", (event) => {
                startPointerSort(event, article, index);
            }, { signal });
            previewButton.addEventListener("click", (event) => {
                if (!suppressPreviewClick) {
                    return;
                }
                event.preventDefault();
                event.stopPropagation();
                suppressPreviewClick = false;
            }, { signal, capture: true });

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

            article.append(previewButton, remove);

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

    function clearPointerSortState({ keepPreviewOrder = false } = {}) {
        previewList?.classList.remove("is-sorting");
        if (pointerSortState?.article instanceof HTMLElement) {
            pointerSortState.article.classList.remove("is-pointer-dragging");
            pointerSortState.article.style.removeProperty("transform");
            pointerSortState.article.style.removeProperty("z-index");
        }
        if (pointerSortState?.activationTimer) {
            window.clearTimeout(pointerSortState.activationTimer);
        }
        if (!keepPreviewOrder) {
            resetPreviewOrder({
                animate: Boolean(pointerSortState?.active),
                skip: pointerSortState?.article ?? null,
            });
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

    documentInput?.addEventListener("change", () => {
        appendSelectedFiles(Array.from(documentInput.files || []));
        if (documentInput instanceof HTMLInputElement) {
            documentInput.value = "";
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
            if (pointerSortState.activationTimer) {
                window.clearTimeout(pointerSortState.activationTimer);
                pointerSortState.activationTimer = null;
            }
            clearPointerSortState();
            return;
        }

        if (!pointerSortState.active) {
            return;
        }

        const hovered = document.elementFromPoint(event.clientX, event.clientY)?.closest(".composer-file-card");
        if (hovered instanceof HTMLElement && hovered !== pointerSortState.article) {
            const targetIndex = Number(hovered.dataset.index || "");
            if (Number.isInteger(targetIndex) && targetIndex >= 0 && targetIndex !== pointerSortState.targetIndex) {
                pointerSortState.targetIndex = targetIndex;
                applyPointerSortPreview(pointerSortState.index, targetIndex);
            }
        }

        const rect = pointerSortState.article.getBoundingClientRect();
        const translateX = event.clientX - pointerSortState.pointerOffsetX - rect.left;
        const translateY = event.clientY - pointerSortState.pointerOffsetY - rect.top;
        pointerSortState.article.style.transform = `translate3d(${translateX}px, ${translateY}px, 0)`;
        pointerSortState.article.style.zIndex = "4";
    }, { signal });

    const finishPointerSort = (event) => {
        if (!pointerSortState || event.pointerId !== pointerSortState.pointerId) {
            return;
        }

        const { active, index, targetIndex } = pointerSortState;
        if (!active || targetIndex === index) {
            clearPointerSortState();
            suppressPreviewClick = false;
            return;
        }

        clearPointerSortState({ keepPreviewOrder: true });
        selectedFiles = reorderEntries(selectedFiles, index, targetIndex);
        syncInputFiles();
        renderPreviewList();
        onFilesChange();
        window.setTimeout(() => {
            suppressPreviewClick = false;
        }, 0);
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
        openCameraPicker: () => triggerPicker(cameraInput),
        openDocumentPicker: () => triggerPicker(documentInput),
        openLibraryPicker: () => triggerPicker(libraryInput),
        renderPreviewList,
        syncInputFiles,
    };
}
