import { bindLocationResolver } from "./geolocation.js";
import { t } from "./i18n.js";

const previewableExtensions = {
    image: new Set(["jpg", "jpeg", "png", "gif", "webp"]),
    video: new Set(["mp4", "mov", "webm"]),
    pdf: new Set(["pdf"]),
    docx: new Set(["docx"]),
    doc: new Set(["doc"]),
    text: new Set(["txt"]),
};

function extensionForFile(file) {
    const parts = file.name.toLowerCase().split(".");
    return parts.length > 1 ? parts.at(-1) || "" : "";
}

function previewKindForFile(file) {
    const extension = extensionForFile(file);

    if (previewableExtensions.image.has(extension)) {
        return "image";
    }
    if (previewableExtensions.video.has(extension)) {
        return "video";
    }
    if (previewableExtensions.pdf.has(extension)) {
        return "pdf";
    }
    if (previewableExtensions.docx.has(extension)) {
        return "docx";
    }
    if (previewableExtensions.doc.has(extension)) {
        return "doc";
    }
    if (previewableExtensions.text.has(extension)) {
        return "text";
    }
    return "document";
}

function fileSignature(file) {
    return `${file.name}::${file.size}::${file.lastModified}`;
}

function buildFileList(fileInput, selectedFiles) {
    const transfer = new DataTransfer();
    selectedFiles.forEach((entry) => transfer.items.add(entry.file));
    fileInput.files = transfer.files;
}

function updateFileSummary(modal) {
    const fileInput = modal.querySelector("[data-file-input]");
    const summary = modal.querySelector("[data-file-summary]");
    if (!fileInput || !summary) {
        return;
    }

    const count = fileInput.files ? fileInput.files.length : 0;
    summary.hidden = count === 0;
    summary.textContent = count
        ? t("composer.attachments_selected", { count }, `${count} attachment(s) selected.`)
        : "";
}

function reorderEntries(entries, fromIndex, toIndex) {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) {
        return entries;
    }

    const next = [...entries];
    const [moved] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, moved);
    return next;
}

function buildCitationCover(item, className) {
    const cover = document.createElement("span");
    cover.className = className;

    if (item.cover) {
        const image = document.createElement("img");
        image.src = item.cover;
        image.alt = item.title || item.label || t("composer.citation_default", {}, "Citation");
        image.loading = "lazy";
        cover.append(image);
        return cover;
    }

    const fallback = document.createElement("span");
    fallback.textContent = (
        item.label || t("composer.citation_default", {}, "Citation")
    ).slice(0, 2);
    cover.append(fallback);
    return cover;
}

export function initComposerModal() {
    const modal = document.querySelector('[data-modal="composer"]');
    if (!modal) {
        return;
    }

    const openButtons = document.querySelectorAll("[data-open-composer]");
    const closeButtons = modal.querySelectorAll("[data-close-composer]");
    const fileInput = modal.querySelector("[data-file-input]");
    const form = modal.querySelector("[data-composer-form]");
    const previewSection = modal.querySelector("[data-composer-preview]");
    const previewList = modal.querySelector("[data-composer-file-list]");
    const citationToggle = modal.querySelector("[data-citation-toggle]");
    const citationPanel = modal.querySelector("[data-citation-panel]");
    const citationSearch = modal.querySelector("[data-citation-search]");
    const citationResults = modal.querySelector("[data-citation-results]");
    const selectedCitationShell = modal.querySelector("[data-selected-citation]");
    const citationKindField = modal.querySelector("[data-citation-kind]");
    const citationTargetIdField = modal.querySelector("[data-citation-target-id]");
    const citationScopeButtons = modal.querySelectorAll("[data-citation-scope]");

    let selectedFiles = [];
    let dragIndex = null;
    let selectedCitation = null;
    let citationScope = "all";
    let citationSearchTimer = null;
    let citationRequestToken = 0;

    const syncInputFiles = () => {
        if (!fileInput) {
            return;
        }

        buildFileList(fileInput, selectedFiles);
        updateFileSummary(modal);
    };

    const renderPreviewList = () => {
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
            });

            const moveLater = document.createElement("button");
            moveLater.type = "button";
            moveLater.className = "button button--ghost button--compact";
            moveLater.textContent = t("composer.later", {}, "Later");
            moveLater.disabled = index === selectedFiles.length - 1;
            moveLater.addEventListener("click", () => {
                selectedFiles = reorderEntries(selectedFiles, index, index + 1);
                syncInputFiles();
                renderPreviewList();
            });

            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "button button--danger button--compact";
            remove.textContent = t("composer.remove", {}, "Remove");
            remove.addEventListener("click", () => {
                entry.objectUrl && URL.revokeObjectURL(entry.objectUrl);
                selectedFiles = selectedFiles.filter((item) => item.id !== entry.id);
                syncInputFiles();
                renderPreviewList();
            });

            actions.append(moveEarlier, moveLater, remove);
            article.append(previewButton, meta, actions);

            article.addEventListener("dragstart", () => {
                dragIndex = index;
                article.classList.add("is-dragging");
            });

            article.addEventListener("dragend", () => {
                dragIndex = null;
                article.classList.remove("is-dragging");
            });

            article.addEventListener("dragover", (event) => {
                event.preventDefault();
                article.classList.add("is-drop-target");
            });

            article.addEventListener("dragleave", () => {
                article.classList.remove("is-drop-target");
            });

            article.addEventListener("drop", (event) => {
                event.preventDefault();
                article.classList.remove("is-drop-target");
                if (dragIndex === null || dragIndex === index) {
                    return;
                }
                selectedFiles = reorderEntries(selectedFiles, dragIndex, index);
                syncInputFiles();
                renderPreviewList();
            });

            previewList.append(article);
        });
    };

    const syncCitationFields = () => {
        if (
            !(citationKindField instanceof HTMLInputElement) ||
            !(citationTargetIdField instanceof HTMLInputElement)
        ) {
            return;
        }

        citationKindField.value = selectedCitation?.kind || "";
        citationTargetIdField.value = selectedCitation?.id ? String(selectedCitation.id) : "";
    };

    const renderSelectedCitation = () => {
        if (!(selectedCitationShell instanceof HTMLElement)) {
            return;
        }

        selectedCitationShell.replaceChildren();
        syncCitationFields();

        if (!selectedCitation) {
            selectedCitationShell.hidden = true;
            return;
        }

        selectedCitationShell.hidden = false;

        const article = document.createElement("article");
        article.className = "composer-citation-card composer-citation-card--selected";

        const body = document.createElement("div");
        body.className = "composer-citation-card__body";
        body.append(buildCitationCover(selectedCitation, "composer-citation-card__cover"));

        const copy = document.createElement("div");
        copy.className = "composer-citation-card__copy";

        const label = document.createElement("span");
        label.className = "composer-citation-card__label";
        label.textContent =
            selectedCitation.label || t("composer.citation_default", {}, "Citation");
        copy.append(label);

        const title = document.createElement("strong");
        title.textContent = selectedCitation.title || t("composer.untitled", {}, "Untitled");
        copy.append(title);

        if (selectedCitation.subtitle) {
            const subtitle = document.createElement("span");
            subtitle.className = "composer-citation-card__subtitle";
            subtitle.textContent = selectedCitation.subtitle;
            copy.append(subtitle);
        }

        if (selectedCitation.excerpt) {
            const excerpt = document.createElement("p");
            excerpt.className = "composer-citation-card__excerpt";
            excerpt.textContent = selectedCitation.excerpt;
            copy.append(excerpt);
        }

        body.append(copy);
        article.append(body);

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "button button--subtle button--compact";
        remove.textContent = t("composer.remove", {}, "Remove");
        remove.addEventListener("click", () => {
            selectedCitation = null;
            renderSelectedCitation();
        });
        article.append(remove);

        selectedCitationShell.append(article);
    };

    const renderCitationResults = (items, query = "") => {
        if (!(citationResults instanceof HTMLElement)) {
            return;
        }

        citationResults.replaceChildren();

        if (!items.length) {
            if (!query) {
                return;
            }
            const empty = document.createElement("div");
            empty.className = "empty-state empty-state--compact";
            const message = document.createElement("p");
            message.textContent = query
                ? t("composer.no_results", {}, "Nothing matched that search yet.")
                : t("composer.search_prompt", {}, "Search once, then pick one item to cite.");
            empty.append(message);
            citationResults.append(empty);
            return;
        }

        items.forEach((item) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "composer-citation-card";

            const body = document.createElement("div");
            body.className = "composer-citation-card__body";
            body.append(buildCitationCover(item, "composer-citation-card__cover"));

            const copy = document.createElement("div");
            copy.className = "composer-citation-card__copy";

            const label = document.createElement("span");
            label.className = "composer-citation-card__label";
            label.textContent = item.label || t("composer.citation_default", {}, "Citation");
            copy.append(label);

            const title = document.createElement("strong");
            title.textContent = item.title || t("composer.untitled", {}, "Untitled");
            copy.append(title);

            if (item.subtitle) {
                const subtitle = document.createElement("span");
                subtitle.className = "composer-citation-card__subtitle";
                subtitle.textContent = item.subtitle;
                copy.append(subtitle);
            }

            if (item.excerpt) {
                const excerpt = document.createElement("p");
                excerpt.className = "composer-citation-card__excerpt";
                excerpt.textContent = item.excerpt;
                copy.append(excerpt);
            }

            body.append(copy);
            button.append(body);

            button.addEventListener("click", () => {
                selectedCitation = item;
                renderSelectedCitation();
                if (citationPanel instanceof HTMLElement) {
                    citationPanel.hidden = true;
                }
                if (citationToggle instanceof HTMLButtonElement) {
                    citationToggle.setAttribute("aria-expanded", "false");
                }
            });

            citationResults.append(button);
        });
    };

    const loadCitationResults = async () => {
        if (!(citationResults instanceof HTMLElement)) {
            return;
        }

        citationRequestToken += 1;
        const token = citationRequestToken;
        const query = citationSearch instanceof HTMLInputElement ? citationSearch.value.trim() : "";

        citationResults.replaceChildren();
        const loading = document.createElement("div");
        loading.className = "empty-state empty-state--compact";
        loading.innerHTML = `<p>${t("composer.loading", {}, "Loading...")}</p>`;
        citationResults.append(loading);

        try {
            const params = new URLSearchParams({
                q: query,
                scope: citationScope,
            });
            const response = await fetch(`/api/citations/search?${params.toString()}`);
            if (!response.ok) {
                throw new Error("Citation search failed");
            }
            const payload = await response.json();
            if (token !== citationRequestToken) {
                return;
            }
            renderCitationResults(Array.isArray(payload.items) ? payload.items : [], query);
        } catch {
            if (token !== citationRequestToken) {
                return;
            }
            citationResults.replaceChildren();
            const empty = document.createElement("div");
            empty.className = "empty-state empty-state--compact";
            empty.innerHTML = `<p>${t(
                "composer.load_error",
                {},
                "Library citations could not be loaded right now.",
            )}</p>`;
            citationResults.append(empty);
        }
    };

    const setCitationPanelOpen = (isOpen) => {
        if (!(citationPanel instanceof HTMLElement) || !(citationToggle instanceof HTMLButtonElement)) {
            return;
        }

        citationPanel.hidden = !isOpen;
        citationToggle.setAttribute("aria-expanded", String(isOpen));
        citationToggle.textContent = isOpen
            ? t("composer.hide_citation", {}, "Hide Citation")
            : t("composer.add_citation", {}, "Add Citation");

        if (isOpen) {
            loadCitationResults();
            citationSearch instanceof HTMLInputElement && citationSearch.focus();
        }
    };

    const openModal = () => {
        document.body.classList.remove("is-sidebar-open");
        modal.hidden = false;
        document.body.classList.add("is-modal-open");
        modal.querySelector("textarea")?.focus();
    };

    const closeModal = () => {
        modal.hidden = true;
        document.body.classList.remove("is-modal-open");
    };

    openButtons.forEach((button) => button.addEventListener("click", openModal));
    closeButtons.forEach((button) => button.addEventListener("click", closeModal));

    citationToggle?.addEventListener("click", () => {
        setCitationPanelOpen(citationPanel?.hidden === true);
    });

    citationScopeButtons.forEach((button) => {
        button.addEventListener("click", () => {
            citationScope = button.dataset.citationScope || "all";
            citationScopeButtons.forEach((entry) =>
                entry.classList.toggle("is-active", entry === button),
            );
            loadCitationResults();
        });
    });

    citationSearch?.addEventListener("input", () => {
        if (citationSearchTimer) {
            window.clearTimeout(citationSearchTimer);
        }
        citationSearchTimer = window.setTimeout(() => {
            loadCitationResults();
        }, 180);
    });

    if (fileInput) {
        fileInput.addEventListener("change", () => {
            const files = Array.from(fileInput.files || []);
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
        });
        updateFileSummary(modal);
    }

    form?.addEventListener("submit", () => {
        syncInputFiles();
        syncCitationFields();
    });

    bindLocationResolver(modal);
    renderSelectedCitation();

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) {
            closeModal();
        }
    });
}
