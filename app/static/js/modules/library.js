import { ensureEpubJs, ensureMammoth } from "./vendor-loader.js";
import { t } from "./i18n.js";
import { requestJson } from "./http.js";
import { initTimestampHelpers, initTrackLyrics } from "./library-audio-helpers.js";
import { secondsToClock } from "./library-time-utils.js";
import {
    animateMediaVolume,
    applyPlayerAppearance,
    applyPlayerSize,
    clearPlayerResumeIntent,
    readPlayerResumeIntent,
    playerDockPositionKey,
    playerDockStateKey,
    playerStorageKey,
    readPlayerAppearance,
    readPlayerSize,
    readStoredJson,
    readStoredPlayerState,
    readTrackCatalog,
    writePlayerResumeIntent,
    writePlayerAppearance,
    writePlayerSize,
    writeStoredPlayerState,
    normalizePlayerState,
} from "./library-player-utils.js";
import { initVideoCardPreviews, initVideoUploadForms } from "./library-video-previews.js";

const readerUiTimers = new WeakMap();
let libraryPageController = null;
let immersiveReaderGlobalsBound = false;
let sectionReaderGlobalsBound = false;

function getLibraryPageSignal() {
    if (!(libraryPageController instanceof AbortController) || libraryPageController.signal.aborted) {
        libraryPageController = new AbortController();
    }
    return libraryPageController.signal;
}

document.addEventListener("app:before-swap", () => {
    libraryPageController?.abort();
    libraryPageController = null;
    immersiveReaderGlobalsBound = false;
    sectionReaderGlobalsBound = false;
});

function getReaderShell(scope) {
    if (scope instanceof Element) {
        return scope.closest("[data-reader-shell]") || scope.querySelector("[data-reader-shell]");
    }
    return document.querySelector("[data-reader-shell]");
}

function clearReaderUiTimer(shell) {
    const timerId = readerUiTimers.get(shell);
    if (timerId) {
        window.clearTimeout(timerId);
        readerUiTimers.delete(shell);
    }
}

function isCompactReaderViewport() {
    return window.matchMedia("(max-width: 720px)").matches;
}

function scheduleReaderUiHide(shell, delay = 2600) {
    if (!(shell instanceof HTMLElement) || shell.classList.contains("is-reader-notes-visible")) {
        return;
    }

    clearReaderUiTimer(shell);
    const timerId = window.setTimeout(() => {
        shell.classList.remove("is-reader-top-visible", "is-reader-bottom-visible");
        readerUiTimers.delete(shell);
    }, delay);
    readerUiTimers.set(shell, timerId);
}

function openReaderPanel(shell, panel) {
    if (!(shell instanceof HTMLElement)) {
        return;
    }

    shell.classList.add(`is-reader-${panel}-visible`);
    scheduleReaderUiHide(shell);
}

function toggleReaderPanel(shell, panel) {
    if (!(shell instanceof HTMLElement)) {
        return;
    }

    const className = `is-reader-${panel}-visible`;
    const willOpen = !shell.classList.contains(className);
    if (willOpen && isCompactReaderViewport()) {
        const oppositePanel = panel === "top" ? "bottom" : "top";
        shell.classList.remove(`is-reader-${oppositePanel}-visible`);
    }
    shell.classList.toggle(className, willOpen);
    if (willOpen) {
        scheduleReaderUiHide(shell);
        return;
    }

    if (
        shell.classList.contains("is-reader-top-visible") ||
        shell.classList.contains("is-reader-bottom-visible")
    ) {
        scheduleReaderUiHide(shell);
    } else {
        clearReaderUiTimer(shell);
    }
}

function closeReaderPanels(scope) {
    const shell = getReaderShell(scope);
    if (!(shell instanceof HTMLElement)) {
        return;
    }

    shell.classList.remove("is-reader-top-visible", "is-reader-bottom-visible");
    clearReaderUiTimer(shell);
}

function closeReaderNotesDrawer(scope, { keepPanels = false } = {}) {
    const shell = getReaderShell(scope);
    if (!(shell instanceof HTMLElement)) {
        return;
    }

    const drawer = shell.querySelector("[data-reader-notes-drawer]");
    if (drawer instanceof HTMLElement) {
        drawer.setAttribute("aria-hidden", "true");
    }

    shell.classList.remove("is-reader-notes-visible");
    if (keepPanels) {
        scheduleReaderUiHide(shell);
    } else {
        shell.classList.remove("is-reader-top-visible", "is-reader-bottom-visible");
        clearReaderUiTimer(shell);
    }
}

function clampReaderScrollRatio(value) {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
        return 0;
    }
    return Math.max(0, Math.min(numericValue, 1));
}

function getElementScrollRatio(element) {
    if (!(element instanceof HTMLElement)) {
        return 0;
    }

    const maxScroll = Math.max(element.scrollHeight - element.clientHeight, 0);
    if (!maxScroll) {
        return 0;
    }
    return clampReaderScrollRatio(element.scrollTop / maxScroll);
}

function setElementScrollRatio(element, ratio) {
    if (!(element instanceof HTMLElement)) {
        return;
    }

    const normalizedRatio = clampReaderScrollRatio(ratio);
    const maxScroll = Math.max(element.scrollHeight - element.clientHeight, 0);
    if (!maxScroll) {
        return;
    }
    element.scrollTop = maxScroll * normalizedRatio;
}

function createReaderSessionKey() {
    if (typeof crypto?.randomUUID === "function") {
        return crypto.randomUUID();
    }
    return `reader-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function createReaderProgressSaver(endpoint, buildPayload) {
    if (!endpoint || typeof buildPayload !== "function") {
        return {
            schedule() {},
            flush() {},
        };
    }

    let timerId = 0;
    let lastSavedSnapshot = "";

    const persist = async ({ immediate = false } = {}) => {
        if (timerId) {
            window.clearTimeout(timerId);
            timerId = 0;
        }

        const payload = buildPayload();
        if (!payload) {
            return;
        }

        const snapshot = JSON.stringify(payload);
        if (snapshot === lastSavedSnapshot) {
            return;
        }

        const send = async () => {
            try {
                await requestJson(endpoint, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
                lastSavedSnapshot = snapshot;
            } catch {
                // Ignore transient progress save failures to keep reading uninterrupted.
            }
        };

        if (immediate) {
            await send();
            return;
        }

        timerId = window.setTimeout(() => {
            timerId = 0;
            void send();
        }, 420);
    };

    return {
        schedule() {
            void persist();
        },
        flush() {
            void persist({ immediate: true });
        },
    };
}

function initBookReaderSelection() {
    const sources = document.querySelectorAll("[data-book-selection-source]:not([data-section-reader])");
    if (!sources.length) {
        return;
    }

    sources.forEach((source) => {
        if (!(source instanceof HTMLElement) || source.dataset.selectionBound === "true") {
            return;
        }
        source.dataset.selectionBound = "true";
        const scope = source.closest(".reader-layout") || document;
        const quoteField = scope.querySelector("[data-book-quote]");
        const chapterField = scope.querySelector("[data-book-chapter-field]");
        const annotationType = scope.querySelector("[data-book-annotation-type]");
        const anchorStatus = scope.querySelector("[data-book-anchor-status]");
        const sectionIndexField = scope.querySelector("[data-book-section-index]");
        const paragraphIdField = scope.querySelector("[data-book-paragraph-id]");
        const selectionStartField = scope.querySelector("[data-book-selection-start]");
        const selectionEndField = scope.querySelector("[data-book-selection-end]");

        if (!(quoteField instanceof HTMLTextAreaElement)) {
            return;
        }

        const syncSelection = () => {
            const selection = window.getSelection();
            if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
                return;
            }

            const range = selection.getRangeAt(0);
            if (!source.contains(range.commonAncestorContainer)) {
                return;
            }

            const text = selection.toString().trim();
            if (!text) {
                return;
            }

            if (sectionIndexField instanceof HTMLInputElement) {
                sectionIndexField.value = "";
            }
            if (paragraphIdField instanceof HTMLInputElement) {
                paragraphIdField.value = "";
            }
            if (selectionStartField instanceof HTMLInputElement) {
                selectionStartField.value = "";
            }
            if (selectionEndField instanceof HTMLInputElement) {
                selectionEndField.value = "";
            }
            quoteField.value = text;
            if (chapterField instanceof HTMLInputElement && !chapterField.value) {
                chapterField.value = t("composer.selected_section", {}, "Selected section");
            }
            if (annotationType instanceof HTMLInputElement) {
                annotationType.value = "text_selection";
            }
            if (anchorStatus instanceof HTMLElement) {
                anchorStatus.textContent = t(
                    "composer.quote_copied",
                    {},
                    "Quote copied from the current selection.",
                );
                anchorStatus.removeAttribute("data-state");
            }
            openReaderNotesDrawer(scope);
        };

        source.addEventListener("mouseup", syncSelection);
        source.addEventListener("touchend", syncSelection);
    });
}

async function initDocxReaders() {
    const readers = document.querySelectorAll("[data-docx-reader]");
    if (!readers.length) {
        return;
    }

    let mammoth;
    try {
        mammoth = await ensureMammoth();
    } catch {
        readers.forEach((reader) => {
            reader.innerHTML = `<p>${t(
                "books.docx_unavailable",
                {},
                "DOCX preview could not be prepared in the browser.",
            )}</p>`;
        });
        return;
    }

    for (const reader of readers) {
        if (reader instanceof HTMLElement && reader.dataset.docxBound === "true") {
            continue;
        }
        if (reader instanceof HTMLElement) {
            reader.dataset.docxBound = "true";
        }
        const src = reader.getAttribute("data-docx-src");
        if (!src) {
            continue;
        }

        try {
            const response = await fetch(src);
            const arrayBuffer = await response.arrayBuffer();
            const result = await mammoth.convertToHtml({ arrayBuffer });
            reader.innerHTML =
                result.value || `<p>${t("books.docx_empty", {}, "No readable content was extracted.")}</p>`;
        } catch {
            reader.innerHTML = `<p>${t(
                "books.docx_unavailable",
                {},
                "DOCX preview could not be prepared in the browser.",
            )}</p>`;
        }
    }
}

function initLinearReaderProgress() {
    const readers = document.querySelectorAll(
        "[data-reader-progress-source]:not([data-section-reader])",
    );
    if (!readers.length) {
        return;
    }

    readers.forEach((reader) => {
        if (!(reader instanceof HTMLElement)) {
            return;
        }

        const shell = getReaderShell(reader);
        const endpoint = shell?.getAttribute("data-reader-progress-endpoint") || "";
        if (!endpoint) {
            return;
        }

        const initialRatio = clampReaderScrollRatio(
            Number.parseFloat(reader.getAttribute("data-reader-resume-scroll-ratio") || "0"),
        );
        let hasRestoredInitialPosition = initialRatio <= 0;
        const sessionKey = createReaderSessionKey();
        const sessionStartedAt = Date.now();

        const saver = createReaderProgressSaver(endpoint, () => ({
            scroll_ratio: getElementScrollRatio(reader),
            session_key: sessionKey,
            session_elapsed_seconds: Math.max(
                Math.round((Date.now() - sessionStartedAt) / 1000),
                0,
            ),
        }));

        const restoreInitialPosition = () => {
            if (hasRestoredInitialPosition) {
                return;
            }

            const maxScroll = Math.max(reader.scrollHeight - reader.clientHeight, 0);
            if (!maxScroll) {
                return;
            }

            hasRestoredInitialPosition = true;
            window.requestAnimationFrame(() => {
                setElementScrollRatio(reader, initialRatio);
            });
        };

        restoreInitialPosition();
        window.setTimeout(restoreInitialPosition, 180);
        window.setTimeout(restoreInitialPosition, 480);

        const observer = new MutationObserver(() => {
            restoreInitialPosition();
        });
        observer.observe(reader, { childList: true, subtree: true });

        const flushProgress = () => {
            saver.flush();
        };

        reader.addEventListener("scroll", () => {
            saver.schedule();
        }, { passive: true });

        window.addEventListener("pagehide", flushProgress);
        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "hidden") {
                flushProgress();
            }
        });
    });
}

function flattenToc(items, bucket = []) {
    items.forEach((item) => {
        if (!item || !item.href) {
            return;
        }

        bucket.push({ href: item.href, label: item.label || item.href });
        if (Array.isArray(item.subitems) && item.subitems.length) {
            flattenToc(item.subitems, bucket);
        }
    });
    return bucket;
}

function normalizeHref(value) {
    return String(value || "").split("#")[0];
}

function readSectionManifest(shell) {
    const script = shell.querySelector("[data-section-manifest]");
    if (!(script instanceof HTMLScriptElement)) {
        return [];
    }

    try {
        const payload = JSON.parse(script.textContent || "[]");
        return Array.isArray(payload) ? payload : [];
    } catch {
        return [];
    }
}

function readSectionAnnotations(shell) {
    const script = shell.querySelector("[data-reader-annotations]");
    if (!(script instanceof HTMLScriptElement)) {
        return [];
    }

    try {
        const payload = JSON.parse(script.textContent || "[]");
        return Array.isArray(payload) ? payload : [];
    } catch {
        return [];
    }
}

function openReaderNotesDrawer(scope) {
    const shell = getReaderShell(scope);
    if (!(shell instanceof HTMLElement)) {
        return null;
    }

    const drawer = shell.querySelector("[data-reader-notes-drawer]");
    if (drawer instanceof HTMLElement) {
        if (isCompactReaderViewport()) {
            shell.classList.remove("is-reader-top-visible", "is-reader-bottom-visible");
            shell.classList.add("is-reader-notes-visible");
        } else {
            shell.classList.add("is-reader-top-visible", "is-reader-bottom-visible", "is-reader-notes-visible");
        }
        drawer.setAttribute("aria-hidden", "false");
        clearReaderUiTimer(shell);
        return drawer;
    }
    return null;
}

function initImmersiveReaderShells() {
    const shells = document.querySelectorAll("[data-reader-shell]");
    if (!shells.length) {
        return;
    }

    const signal = getLibraryPageSignal();

    shells.forEach((shell) => {
        if (!(shell instanceof HTMLElement) || shell.dataset.readerShellBound === "true") {
            return;
        }
        shell.dataset.readerShellBound = "true";

        const stage = shell.querySelector("[data-reader-stage]");
        const topToggle = shell.querySelector("[data-reader-toggle-top]");
        const bottomToggle = shell.querySelector("[data-reader-toggle-bottom]");
        const notesBackdrop = shell.querySelector("[data-reader-notes-backdrop]");

        topToggle?.addEventListener("click", (event) => {
            event.preventDefault();
            toggleReaderPanel(shell, "top");
        }, { signal });

        bottomToggle?.addEventListener("click", (event) => {
            event.preventDefault();
            toggleReaderPanel(shell, "bottom");
        }, { signal });

        shell.querySelectorAll("[data-reader-open-notes]").forEach((button) => {
            button.addEventListener("click", (event) => {
                event.preventDefault();
                openReaderNotesDrawer(shell);
            }, { signal });
        });

        shell.querySelectorAll("[data-reader-close-notes]").forEach((button) => {
            button.addEventListener("click", (event) => {
                event.preventDefault();
                closeReaderNotesDrawer(shell);
            }, { signal });
        });

        notesBackdrop?.addEventListener("click", () => {
            closeReaderNotesDrawer(shell);
        }, { signal });

        stage?.addEventListener("click", (event) => {
            if (!(event.target instanceof Element)) {
                return;
            }

            const activeSelection = window.getSelection();
            if (activeSelection && !activeSelection.isCollapsed) {
                return;
            }

            if (
                event.target.closest(
                    "a, button, input, select, textarea, label, [role='button'], [data-reader-highlight]",
                )
            ) {
                return;
            }

            if (shell.classList.contains("is-reader-notes-visible")) {
                closeReaderNotesDrawer(shell);
                return;
            }

            if (
                shell.classList.contains("is-reader-top-visible") ||
                shell.classList.contains("is-reader-bottom-visible")
            ) {
                closeReaderPanels(shell);
            }
        }, { signal });
    });

    if (!immersiveReaderGlobalsBound) {
        immersiveReaderGlobalsBound = true;
        document.addEventListener("keydown", (event) => {
            if (event.key !== "Escape") {
                return;
            }

            document.querySelectorAll("[data-reader-shell]").forEach((shell) => {
                if (!(shell instanceof HTMLElement)) {
                    return;
                }

                if (shell.classList.contains("is-reader-notes-visible")) {
                    closeReaderNotesDrawer(shell);
                    return;
                }

                if (
                    shell.classList.contains("is-reader-top-visible") ||
                    shell.classList.contains("is-reader-bottom-visible")
                ) {
                    closeReaderPanels(shell);
                }
            });
        }, { signal });
    }
}

function getClosestElement(node) {
    if (node instanceof Element) {
        return node;
    }
    return node?.parentElement || null;
}

function getTextOffsetWithin(root, container, offset) {
    const range = document.createRange();
    range.selectNodeContents(root);
    range.setEnd(container, offset);
    return range.toString().length;
}

function unwrapReaderHighlights(container) {
    container.querySelectorAll("[data-reader-highlight]").forEach((highlight) => {
        const parent = highlight.parentNode;
        if (!parent) {
            return;
        }
        while (highlight.firstChild) {
            parent.insertBefore(highlight.firstChild, highlight);
        }
        parent.removeChild(highlight);
    });
}

function wrapReaderHighlight(root, start, end, annotationId) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
            return node.nodeValue ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        },
    });
    const textNodes = [];
    while (walker.nextNode()) {
        textNodes.push(walker.currentNode);
    }

    const marks = [];
    let position = 0;

    textNodes.forEach((node) => {
        const length = node.nodeValue?.length || 0;
        if (!length) {
            return;
        }

        const overlapStart = Math.max(start - position, 0);
        const overlapEnd = Math.min(end - position, length);
        position += length;

        if (overlapEnd <= overlapStart) {
            return;
        }

        const range = document.createRange();
        range.setStart(node, overlapStart);
        range.setEnd(node, overlapEnd);

        const mark = document.createElement("mark");
        mark.className = "reader-highlight";
        mark.dataset.readerHighlight = "true";
        mark.dataset.annotationId = String(annotationId);
        mark.tabIndex = 0;

        try {
            range.surroundContents(mark);
        } catch {
            const fragment = range.extractContents();
            mark.append(fragment);
            range.insertNode(mark);
        }

        marks.push(mark);
    });

    return marks;
}

function initSectionReaders() {
    const shells = document.querySelectorAll("[data-section-shell]");
    if (!shells.length) {
        return;
    }

    const signal = getLibraryPageSignal();

    shells.forEach((shell) => {
        if (!(shell instanceof HTMLElement) || shell.dataset.sectionReaderBound === "true") {
            return;
        }
        shell.dataset.sectionReaderBound = "true";
        const reader = shell.querySelector("[data-section-reader]");
        const previous = shell.querySelector("[data-section-prev]");
        const next = shell.querySelector("[data-section-next]");
        const toc = shell.querySelector("[data-section-toc]");
        const title = shell.querySelector("[data-section-title]");
        const progress = shell.querySelector("[data-section-progress]");
        const readerLayout = shell.closest(".reader-layout") || document;
        const chapterField = readerLayout.querySelector("[data-book-chapter-field]");
        const quoteField = readerLayout.querySelector("[data-book-quote]");
        const annotationType = readerLayout.querySelector("[data-book-annotation-type]");
        const nextField = readerLayout.querySelector("[data-book-next-field]");
        const anchorStatus = readerLayout.querySelector("[data-book-anchor-status]");
        const sectionIndexField = readerLayout.querySelector("[data-book-section-index]");
        const paragraphIdField = readerLayout.querySelector("[data-book-paragraph-id]");
        const selectionStartField = readerLayout.querySelector("[data-book-selection-start]");
        const selectionEndField = readerLayout.querySelector("[data-book-selection-end]");
        const peek = readerLayout.querySelector("[data-reader-annotation-peek]");
        const peekMeta = readerLayout.querySelector("[data-reader-annotation-peek-meta]");
        const peekQuote = readerLayout.querySelector("[data-reader-annotation-peek-quote]");
        const peekComment = readerLayout.querySelector("[data-reader-annotation-peek-comment]");
        const annotationCards = Array.from(readerLayout.querySelectorAll("[data-annotation-card]"));
        const progressMeters = Array.from(readerLayout.querySelectorAll("[data-reader-progress-meter]"));
        const progressFills = Array.from(readerLayout.querySelectorAll("[data-reader-progress-fill]"));
        const sectionLabels = Array.from(readerLayout.querySelectorAll("[data-reader-current-section-label]"));
        const progressTexts = Array.from(readerLayout.querySelectorAll("[data-reader-progress-text]"));
        const progressPercents = Array.from(readerLayout.querySelectorAll("[data-reader-progress-percent]"));

        if (
            !(reader instanceof HTMLElement) ||
            !(previous instanceof HTMLButtonElement) ||
            !(next instanceof HTMLButtonElement) ||
            !(toc instanceof HTMLSelectElement) ||
            !(title instanceof HTMLElement) ||
            !(progress instanceof HTMLElement)
        ) {
            return;
        }

        const endpoint = reader.getAttribute("data-section-endpoint");
        const manifest = readSectionManifest(shell);
        const annotations = readSectionAnnotations(shell);
        const annotationMap = new Map(
            annotations
                .map((annotation) => [Number(annotation.id), annotation])
                .filter(([annotationId]) => Number.isInteger(annotationId))
        );
        if (!endpoint || !manifest.length) {
            previous.disabled = true;
            next.disabled = true;
            toc.innerHTML = `<option value="0">${t(
                "books.no_sections_found",
                {},
                "No sections found",
            )}</option>`;
            progress.textContent = t("books.unavailable", {}, "Unavailable");
            return;
        }

        let activeIndex = Number.parseInt(
            reader.getAttribute("data-section-initial-index") || "0",
            10
        );
        if (!Number.isInteger(activeIndex) || activeIndex < 0 || activeIndex >= manifest.length) {
            activeIndex = 0;
        }

        const cache = new Map();
        const initialMarkup = reader.innerHTML.trim();
        if (initialMarkup) {
            cache.set(activeIndex, initialMarkup);
        }

        const initialFocusAnnotationId = Number.parseInt(
            readerLayout.getAttribute("data-reader-focus-annotation-id") || "",
            10,
        );
        let pendingAnnotationId = Number.isInteger(initialFocusAnnotationId)
            ? initialFocusAnnotationId
            : null;
        let pendingResumeScrollRatio = clampReaderScrollRatio(
            Number.parseFloat(reader.getAttribute("data-reader-resume-scroll-ratio") || "0"),
        );
        const sessionKey = createReaderSessionKey();
        const sessionStartedAt = Date.now();
        const saveProgressEndpoint =
            (readerLayout instanceof Element
                ? readerLayout.getAttribute("data-reader-progress-endpoint")
                : "") || "";
        const progressSaver = createReaderProgressSaver(saveProgressEndpoint, () => ({
            section_index: activeIndex,
            scroll_ratio: getElementScrollRatio(reader),
            session_key: sessionKey,
            session_elapsed_seconds: Math.max(
                Math.round((Date.now() - sessionStartedAt) / 1000),
                0,
            ),
        }));

        const clearAnnotationLocation = () => {
            const url = new URL(window.location.href);
            if (!url.searchParams.has("annotation")) {
                return;
            }

            url.searchParams.delete("annotation");
            window.history.replaceState({ section: activeIndex }, "", url);
            if (nextField instanceof HTMLInputElement) {
                nextField.value = `${url.pathname}${url.search}`;
            }
        };

        const clearAnchorCapture = ({ message = "", state = "", preserveQuote = true } = {}) => {
            if (sectionIndexField instanceof HTMLInputElement) {
                sectionIndexField.value = "";
            }
            if (paragraphIdField instanceof HTMLInputElement) {
                paragraphIdField.value = "";
            }
            if (selectionStartField instanceof HTMLInputElement) {
                selectionStartField.value = "";
            }
            if (selectionEndField instanceof HTMLInputElement) {
                selectionEndField.value = "";
            }
            if (annotationType instanceof HTMLInputElement) {
                annotationType.value = "text_selection";
            }
            if (!preserveQuote && quoteField instanceof HTMLTextAreaElement) {
                quoteField.value = "";
            }
            if (anchorStatus instanceof HTMLElement && message) {
                anchorStatus.textContent = message;
                if (state) {
                    anchorStatus.setAttribute("data-state", state);
                } else {
                    anchorStatus.removeAttribute("data-state");
                }
            } else if (anchorStatus instanceof HTMLElement && !message) {
                anchorStatus.removeAttribute("data-state");
            }
        };

        const clearActiveAnnotationState = () => {
            annotationCards.forEach((card) => {
                card.classList.remove("is-active");
            });
            reader.querySelectorAll("[data-reader-highlight]").forEach((highlight) => {
                highlight.classList.remove("is-active");
            });
        };

        const hidePeek = () => {
            if (peek instanceof HTMLElement) {
                peek.hidden = true;
                delete peek.dataset.annotationId;
            }
        };

        const showPeek = (annotation) => {
            if (!(peek instanceof HTMLElement) || !(peekMeta instanceof HTMLElement) || !(peekComment instanceof HTMLElement)) {
                return;
            }

            openReaderNotesDrawer(readerLayout);

            const metaParts = [];
            if (annotation.chapter_label) {
                metaParts.push(annotation.chapter_label);
            }
            if (annotation.page_label) {
                metaParts.push(`Page ${annotation.page_label}`);
            }
            if (annotation.tag) {
                metaParts.push(annotation.tag);
            }
            if (annotation.created_at) {
                metaParts.push(annotation.created_at);
            }

            peek.hidden = false;
            peek.dataset.annotationId = String(annotation.id);
            peekMeta.textContent = metaParts.join(" - ") || "Saved note";
            peekComment.textContent = annotation.comment || "";

            if (peekQuote instanceof HTMLElement) {
                const hasQuote = Boolean(annotation.quoted_text);
                peekQuote.hidden = !hasQuote;
                peekQuote.textContent = annotation.quoted_text || "";
            }
        };

        const focusAnnotation = (annotation, { scrollReader = false, scrollCard = false } = {}) => {
            if (!annotation) {
                return;
            }

            pendingAnnotationId = null;
            clearActiveAnnotationState();

            const annotationId = String(annotation.id);
            const card = annotationCards.find(
                (item) => item.getAttribute("data-annotation-id") === annotationId
            );
            if (card) {
                card.classList.add("is-active");
                if (scrollCard) {
                    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
                }
            }

            const highlights = reader.querySelectorAll(`[data-annotation-id="${annotationId}"]`);
            highlights.forEach((highlight, index) => {
                highlight.classList.add("is-active");
                if (index === 0 && scrollReader) {
                    highlight.scrollIntoView({ behavior: "smooth", block: "center" });
                }
            });

            showPeek(annotation);
        };

        const restoreReaderScroll = () => {
            if (pendingResumeScrollRatio <= 0) {
                return;
            }

            const targetRatio = pendingResumeScrollRatio;
            pendingResumeScrollRatio = 0;

            window.requestAnimationFrame(() => {
                setElementScrollRatio(reader, targetRatio);
            });
        };

        const flushProgressSave = () => {
            progressSaver.flush();
        };

        const renderHighlights = () => {
            unwrapReaderHighlights(reader);
            clearActiveAnnotationState();

            annotations
                .filter((annotation) => Number(annotation.section_index) === activeIndex && annotation.paragraph_id)
                .forEach((annotation) => {
                    const paragraph = reader.querySelector(
                        `[data-reader-paragraph-id="${annotation.paragraph_id}"]`
                    );
                    const start = Number(annotation.selection_start);
                    const end = Number(annotation.selection_end);
                    if (
                        !(paragraph instanceof HTMLElement) ||
                        !Number.isInteger(start) ||
                        !Number.isInteger(end) ||
                        end <= start
                    ) {
                        return;
                    }
                    wrapReaderHighlight(paragraph, start, end, annotation.id);
                });

            const activePeekId =
                peek instanceof HTMLElement ? Number(peek.dataset.annotationId || "") : NaN;
            if (Number.isInteger(activePeekId)) {
                const activeAnnotation = annotationMap.get(activePeekId);
                if (activeAnnotation && Number(activeAnnotation.section_index) === activeIndex) {
                    focusAnnotation(activeAnnotation);
                    return;
                }
            }

            if (Number.isInteger(pendingAnnotationId)) {
                const pendingAnnotation = annotationMap.get(pendingAnnotationId);
                if (pendingAnnotation && Number(pendingAnnotation.section_index) === activeIndex) {
                    focusAnnotation(pendingAnnotation, { scrollReader: true, scrollCard: true });
                    clearAnnotationLocation();
                    return;
                }
            }

            hidePeek();
            restoreReaderScroll();
        };

        const sync = (index) => {
            activeIndex = Math.max(0, Math.min(index, manifest.length - 1));
            const section = manifest[activeIndex];
            const label = section?.label || `Section ${activeIndex + 1}`;
            const optionLabel = section?.is_front_matter
                ? `${label} (${t("books.front_matter", {}, "Front matter")})`
                : label;
            const percent = manifest.length ? ((activeIndex + 1) / manifest.length) * 100 : 0;
            const progressLabel = `${activeIndex + 1} / ${manifest.length}`;
            const topProgressLabel = section?.is_front_matter
                ? `${t("books.front_matter", {}, "Front matter")} - ${t("books.section", {}, "Section")} ${progressLabel}`
                : `${t("books.section", {}, "Section")} ${progressLabel}`;

            title.textContent = label;
            progress.textContent = topProgressLabel;
            sectionLabels.forEach((node) => {
                node.textContent = label;
                node.setAttribute("title", label);
            });
            progressTexts.forEach((node) => {
                node.textContent = progressLabel;
            });
            progressPercents.forEach((node) => {
                node.textContent = `${Math.round(percent)}%`;
            });
            progressFills.forEach((fill) => {
                fill.style.width = `${percent}%`;
            });
            progressMeters.forEach((meter) => {
                meter.setAttribute("aria-valuemax", String(manifest.length));
                meter.setAttribute("aria-valuenow", String(activeIndex + 1));
            });
            toc.value = String(activeIndex);
            if (toc.options[activeIndex]) {
                toc.options[activeIndex].textContent = optionLabel;
            }
            previous.disabled = activeIndex === 0;
            next.disabled = activeIndex === manifest.length - 1;
            if (chapterField instanceof HTMLInputElement) {
                chapterField.value = label;
            }
        };

        const writeLocation = () => {
            const url = new URL(window.location.href);
            url.searchParams.set("section", String(activeIndex + 1));
            window.history.replaceState({ section: activeIndex }, "", url);
            if (nextField instanceof HTMLInputElement) {
                nextField.value = `${url.pathname}${url.search}`;
            }
        };

        const loadSection = async (index, { updateLocation = true } = {}) => {
            const previousIndex = activeIndex;
            sync(index);
            if (updateLocation) {
                writeLocation();
            }
            if (previousIndex !== activeIndex) {
                clearAnchorCapture({
                    message: "Highlight anchor cleared after section change. Select the passage again if needed.",
                    state: "warning",
                });
            }

            if (cache.has(activeIndex)) {
                reader.innerHTML = cache.get(activeIndex) || "";
                reader.scrollTop = 0;
                renderHighlights();
                progressSaver.schedule();
                return;
            }

            reader.innerHTML = `<p class='helper-text'>${t(
                "books.section_loading",
                {},
                "Loading section...",
            )}</p>`;
            reader.classList.add("is-loading");

            try {
                const response = await fetch(`${endpoint}?index=${activeIndex}`, {
                    headers: { Accept: "application/json" },
                });
                if (!response.ok) {
                    throw new Error("Section request failed.");
                }

                const payload = await response.json();
                if (payload.label) {
                    manifest[activeIndex] = {
                        ...(manifest[activeIndex] || {}),
                        index: activeIndex,
                        label: payload.label,
                        is_front_matter: Boolean(payload.is_front_matter),
                    };
                }
                const markup =
                    payload.html || "<p class='helper-text'>This section is empty.</p>";
                cache.set(activeIndex, markup);
                reader.innerHTML = markup;
                reader.scrollTop = 0;
                sync(activeIndex);
                renderHighlights();
                progressSaver.schedule();
            } catch {
                reader.innerHTML =
                    "<p class='helper-text'>This section could not be loaded right now.</p>";
                hidePeek();
                clearActiveAnnotationState();
            } finally {
                reader.classList.remove("is-loading");
            }
        };

        const syncSelection = () => {
            const selection = window.getSelection();
            if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
                return;
            }

            const range = selection.getRangeAt(0);
            if (!reader.contains(range.commonAncestorContainer)) {
                return;
            }

            const rawText = selection.toString();
            const text = rawText.trim();
            if (!text) {
                return;
            }

            if (quoteField instanceof HTMLTextAreaElement) {
                quoteField.value = text;
            }
            if (chapterField instanceof HTMLInputElement) {
                chapterField.value = manifest[activeIndex]?.label || `Section ${activeIndex + 1}`;
            }

            const startElement = getClosestElement(range.startContainer)?.closest(
                "[data-reader-paragraph-id]"
            );
            const endElement = getClosestElement(range.endContainer)?.closest(
                "[data-reader-paragraph-id]"
            );

            if (!(startElement instanceof HTMLElement) || startElement !== endElement) {
                clearAnchorCapture({
                    message: "For precise highlights, keep the selection inside one paragraph.",
                    state: "warning",
                });
                return;
            }

            const paragraphId = startElement.getAttribute("data-reader-paragraph-id");
            if (!paragraphId) {
                clearAnchorCapture({
                    message: "This passage could not be anchored precisely. Try selecting it again.",
                    state: "warning",
                });
                return;
            }

            const leadingWhitespace = rawText.length - rawText.replace(/^\s+/, "").length;
            const trailingWhitespace = rawText.length - rawText.replace(/\s+$/, "").length;
            const selectionStart =
                getTextOffsetWithin(startElement, range.startContainer, range.startOffset) +
                leadingWhitespace;
            const selectionEnd =
                getTextOffsetWithin(startElement, range.endContainer, range.endOffset) -
                trailingWhitespace;

            if (!Number.isFinite(selectionStart) || !Number.isFinite(selectionEnd) || selectionEnd <= selectionStart) {
                clearAnchorCapture({
                    message: "This highlight range was not stable enough to save. Select it again.",
                    state: "warning",
                });
                return;
            }

            if (sectionIndexField instanceof HTMLInputElement) {
                sectionIndexField.value = String(activeIndex);
            }
            if (paragraphIdField instanceof HTMLInputElement) {
                paragraphIdField.value = paragraphId;
            }
            if (selectionStartField instanceof HTMLInputElement) {
                selectionStartField.value = String(selectionStart);
            }
            if (selectionEndField instanceof HTMLInputElement) {
                selectionEndField.value = String(selectionEnd);
            }
            if (annotationType instanceof HTMLInputElement) {
                annotationType.value = "text_anchor";
            }
            if (anchorStatus instanceof HTMLElement) {
                anchorStatus.textContent = `Precise highlight captured in ${manifest[activeIndex]?.label || "this section"}.`;
                anchorStatus.setAttribute("data-state", "success");
            }
            openReaderNotesDrawer(readerLayout);
        };

        previous.addEventListener("click", () => {
            if (activeIndex > 0) {
                void loadSection(activeIndex - 1);
            }
        }, { signal });

        next.addEventListener("click", () => {
            if (activeIndex < manifest.length - 1) {
                void loadSection(activeIndex + 1);
            }
        }, { signal });

        toc.addEventListener("change", () => {
            const nextIndex = Number.parseInt(toc.value, 10);
            if (Number.isInteger(nextIndex)) {
                void loadSection(nextIndex);
            }
        }, { signal });

        reader.addEventListener("scroll", () => {
            progressSaver.schedule();
        }, { passive: true, signal });
        reader.addEventListener("mouseup", syncSelection, { signal });
        reader.addEventListener("touchend", syncSelection, { signal });
        reader.addEventListener("click", (event) => {
            if (!(event.target instanceof Element)) {
                return;
            }

            const highlight = event.target.closest("[data-reader-highlight]");
            if (!highlight) {
                return;
            }

            const annotationId = Number(highlight.getAttribute("data-annotation-id"));
            if (!Number.isInteger(annotationId)) {
                return;
            }

            const annotation = annotationMap.get(annotationId);
            if (annotation) {
                focusAnnotation(annotation, { scrollCard: true });
            }
        }, { signal });

        annotationCards.forEach((card) => {
            const openCardAnnotation = () => {
                const annotationId = Number(card.getAttribute("data-annotation-id"));
                if (!Number.isInteger(annotationId)) {
                    return;
                }

                const annotation = annotationMap.get(annotationId);
                if (!annotation) {
                    return;
                }

                const targetSectionIndex = Number(annotation.section_index);
                if (Number.isInteger(targetSectionIndex) && targetSectionIndex !== activeIndex) {
                    pendingAnnotationId = annotationId;
                    void loadSection(targetSectionIndex);
                    return;
                }

                focusAnnotation(annotation, { scrollReader: true });
            };

            card.addEventListener("click", openCardAnnotation, { signal });
            card.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openCardAnnotation();
                }
            }, { signal });
        });

        window.addEventListener("pagehide", flushProgressSave, { signal });
        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "hidden") {
                flushProgressSave();
            }
        }, { signal });

        sync(activeIndex);
        writeLocation();
        renderHighlights();
        progressSaver.schedule();

        if (!sectionReaderGlobalsBound) {
            sectionReaderGlobalsBound = true;
            document.addEventListener("keydown", (event) => {
                const activeShell = document.querySelector("[data-section-shell]");
                if (!(activeShell instanceof HTMLElement) || !activeShell.contains(reader)) {
                    return;
                }

                const activeTag = document.activeElement?.tagName || "";
                if (["INPUT", "TEXTAREA", "SELECT"].includes(activeTag)) {
                    return;
                }

                if (event.key === "ArrowLeft" && activeIndex > 0) {
                    event.preventDefault();
                    void loadSection(activeIndex - 1);
                }
                if (event.key === "ArrowRight" && activeIndex < manifest.length - 1) {
                    event.preventDefault();
                    void loadSection(activeIndex + 1);
                }
            }, { signal });
        }
    });
}

const frontMatterHints = [
    "cover",
    "copyright",
    "titlepage",
    "title page",
    "contents",
    "table of contents",
    "toc",
    "nav",
    "colophon",
    "preface",
    "foreword",
    "introduction",
    "dedication",
    "acknowledgement",
    "acknowledgment",
    "acknowledgements",
    "acknowledgments",
    "封面",
    "版权",
    "目录",
    "扉页",
    "前言",
    "序",
    "引言",
    "致谢",
];

function isFrontMatterReference(href, label = "") {
    const haystack = `${normalizeHref(href)} ${String(label || "")}`.toLowerCase();
    return frontMatterHints.some((hint) => haystack.includes(hint));
}

function pickInitialTocItem(items) {
    if (!items.length) {
        return null;
    }

    return items.find((item) => !isFrontMatterReference(item.href, item.label)) || items[0];
}

async function initEpubReaders() {
    const shells = document.querySelectorAll("[data-epub-shell]");
    if (!shells.length) {
        return;
    }

    const signal = getLibraryPageSignal();

    let ePubFactory;
    try {
        ePubFactory = await ensureEpubJs();
    } catch {
        shells.forEach((shell) => {
            const mount = shell.querySelector("[data-epub-reader]");
            if (mount) {
                mount.innerHTML = `<p class='helper-text'>${t(
                    "books.epub_assets_failed",
                    {},
                    "EPUB reader assets did not load in the browser.",
                )}</p>`;
            }
        });
        return;
    }

    for (const shell of shells) {
        if (shell instanceof HTMLElement && shell.dataset.epubBound === "true") {
            continue;
        }
        if (shell instanceof HTMLElement) {
            shell.dataset.epubBound = "true";
        }
        const mount = shell.querySelector("[data-epub-reader]");
        const previous = shell.querySelector("[data-epub-prev]");
        const next = shell.querySelector("[data-epub-next]");
        const toc = shell.querySelector("[data-epub-toc]");
        const sectionLabel = shell.querySelector("[data-epub-section]");
        const progressLabel = shell.querySelector("[data-epub-progress]");
        const readerLayout = shell.closest(".reader-layout") || document;
        const quoteField = readerLayout.querySelector("[data-book-quote]");
        const chapterField = readerLayout.querySelector("[data-book-chapter-field]");
        const annotationType = readerLayout.querySelector("[data-book-annotation-type]");

        if (
            !(mount instanceof HTMLElement) ||
            !(previous instanceof HTMLButtonElement) ||
            !(next instanceof HTMLButtonElement) ||
            !(toc instanceof HTMLSelectElement) ||
            !(sectionLabel instanceof HTMLElement) ||
            !(progressLabel instanceof HTMLElement)
        ) {
            continue;
        }

        const src = mount.getAttribute("data-epub-src");
        if (!src) {
            continue;
        }

        try {
            const book = ePubFactory(src);
            const rendition = book.renderTo(mount, {
                width: "100%",
                height: "100%",
                spread: "auto",
            });

            const tocItems = [];
            let currentSectionLabel = sectionLabel.textContent || "Current section";

            const syncLocation = (location) => {
                if (!location || !location.start) {
                    return;
                }

                const currentHref = normalizeHref(location.start.href);
                const matched = tocItems.length
                    ? tocItems.find((item) => normalizeHref(item.href) === currentHref)
                    : null;
                if (matched) {
                    currentSectionLabel = matched.label;
                    toc.value = matched.href;
                }

                sectionLabel.textContent = currentSectionLabel;
                if (chapterField instanceof HTMLInputElement) {
                    chapterField.value = currentSectionLabel;
                }

                let progress = location.start.percentage;
                if (typeof progress !== "number" && book.locations && location.start.cfi) {
                    try {
                        progress = book.locations.percentageFromCfi(location.start.cfi);
                    } catch {
                        progress = undefined;
                    }
                }

                progressLabel.textContent =
                    typeof progress === "number" && Number.isFinite(progress)
                        ? `${Math.round(progress * 100)}%`
                        : "Reading";
            };

            rendition.on("selected", (cfiRange, contents) => {
                const selection = contents?.window?.getSelection?.();
                const text = selection ? selection.toString().trim() : "";
                if (text && quoteField instanceof HTMLTextAreaElement) {
                    quoteField.value = text;
                }
                if (chapterField instanceof HTMLInputElement) {
                    chapterField.value = currentSectionLabel;
                }
                if (annotationType instanceof HTMLInputElement) {
                    annotationType.value = "text_selection";
                }
                if (selection) {
                    selection.removeAllRanges();
                }
                if (typeof rendition.annotations?.remove === "function") {
                    try {
                        rendition.annotations.remove(cfiRange, "highlight");
                    } catch {
                        // Ignore annotation cleanup issues from the third-party reader.
                    }
                }
            });

            rendition.on("relocated", syncLocation);

            previous.addEventListener("click", () => {
                rendition.prev();
            }, { signal });

            next.addEventListener("click", () => {
                rendition.next();
            }, { signal });

            toc.addEventListener("change", () => {
                if (toc.value) {
                    rendition.display(toc.value);
                }
            }, { signal });

            await rendition.display();

            const initialLocation = rendition.currentLocation();
            if (initialLocation) {
                syncLocation(initialLocation);
            }

            book.loaded.navigation
                .then((navigation) => {
                    toc.innerHTML = "";
                    const flattened = flattenToc(navigation?.toc || []);
                    tocItems.splice(0, tocItems.length, ...flattened);

                    if (tocItems.length) {
                        tocItems.forEach((item) => {
                            const option = document.createElement("option");
                            option.value = item.href;
                            option.textContent = item.label;
                            toc.append(option);
                        });
                    } else {
                        const option = document.createElement("option");
                        option.value = "";
                        option.textContent = t("books.current_book", {}, "Current book");
                        toc.append(option);
                    }

                    const preferredItem = pickInitialTocItem(tocItems);
                    const currentLocation = rendition.currentLocation();
                    const currentHref = currentLocation?.start?.href || "";

                    if (
                        preferredItem &&
                        (!currentHref || isFrontMatterReference(currentHref, currentSectionLabel))
                    ) {
                        currentSectionLabel = preferredItem.label;
                        sectionLabel.textContent = currentSectionLabel;
                        if (chapterField instanceof HTMLInputElement) {
                            chapterField.value = currentSectionLabel;
                        }
                        toc.value = preferredItem.href;
                        void rendition.display(preferredItem.href).then(() => {
                            const relocated = rendition.currentLocation();
                            if (relocated) {
                                syncLocation(relocated);
                            }
                        });
                    } else if (currentLocation) {
                        syncLocation(currentLocation);
                    }
                })
                .catch(() => {
                    toc.innerHTML = `<option value="">${t(
                        "books.current_book",
                        {},
                        "Current book",
                    )}</option>`;
                });

            const generateLocations = async () => {
                try {
                    await book.locations.generate(1200);
                    const currentLocation = rendition.currentLocation();
                    if (currentLocation) {
                        syncLocation(currentLocation);
                    }
                } catch {
                    // Progress can still work without generated locations.
                }
            };

            if ("requestIdleCallback" in window) {
                window.requestIdleCallback(() => {
                    void generateLocations();
                });
            } else {
                window.setTimeout(() => {
                    void generateLocations();
                }, 0);
            }
        } catch {
            mount.innerHTML = `<p class='helper-text'>${t(
                "books.epub_reader_failed",
                {},
                "EPUB reader could not be prepared in the browser.",
            )}</p>`;
        }
    }
}
function getPlayerLabel(track) {
    return track?.artist ? `${track.title} - ${track.artist}` : track?.title || "";
}

function hashPlayerSeed(seed) {
    let hash = 0;
    const text = String(seed || "");
    for (let index = 0; index < text.length; index += 1) {
        hash = (hash << 5) - hash + text.charCodeAt(index);
        hash |= 0;
    }
    return Math.abs(hash);
}

function getTrackArtworkLabel(track) {
    const source = `${track?.title || ""}${track?.artist || ""}`.replace(/\s+/g, "");
    if (!source) {
        return "♪";
    }

    const glyphs = Array.from(source);
    const ascii = source
        .replace(/[^a-z0-9]/gi, "")
        .slice(0, 2)
        .toUpperCase();
    if (ascii) {
        return ascii;
    }
    return glyphs.slice(0, Math.min(2, glyphs.length)).join("");
}

function buildTrackArtwork(track) {
    const seed = `${track?.title || "track"}|${track?.artist || ""}`;
    const hue = hashPlayerSeed(seed) % 360;
    const accentHue = (hue + 46) % 360;
    return {
        label: getTrackArtworkLabel(track),
        start: `hsl(${hue} 42% 58%)`,
        end: `hsl(${accentHue} 45% 28%)`,
    };
}

function updatePlayerArtwork(scope, track) {
    if (!(scope instanceof Element)) {
        return;
    }

    const artwork = buildTrackArtwork(track);
    scope.querySelectorAll("[data-player-artwork]").forEach((node) => {
        if (!(node instanceof HTMLElement)) {
            return;
        }

        node.style.setProperty("--player-art-start", artwork.start);
        node.style.setProperty("--player-art-end", artwork.end);
        node.style.backgroundImage = track?.cover
            ? `linear-gradient(180deg, rgba(16, 22, 24, 0.08), rgba(16, 22, 24, 0.14)), url("${track.cover}")`
            : "";
        node.style.backgroundSize = track?.cover ? "cover" : "";
        node.style.backgroundPosition = track?.cover ? "center" : "";
        const label = node.querySelector("[data-player-artwork-label]");
        if (label instanceof HTMLElement) {
            label.textContent = artwork.label;
            label.hidden = Boolean(track?.cover);
        }
    });

    const bubble = scope.querySelector("[data-player-bubble]");
    if (bubble instanceof HTMLButtonElement) {
        bubble.setAttribute(
            "aria-label",
            track
                ? t(
                    "player.open_mini_player_for",
                    { label: getPlayerLabel(track) },
                    `Open mini player for ${getPlayerLabel(track)}`,
                )
                : t("player.open_mini_player", {}, "Open mini player")
        );
    }
}

function setPlayerToggleIcon(button, isPlaying) {
    if (!(button instanceof HTMLButtonElement)) {
        return;
    }

    button.innerHTML = isPlaying
        ? '<span aria-hidden="true">&#10074;&#10074;</span>'
        : '<span aria-hidden="true">&#9654;</span>';
    button.setAttribute(
        "aria-label",
        isPlaying ? t("player.pause", {}, "Pause") : t("player.play", {}, "Play"),
    );
}

function renderPlayerQueue(queuePanel, queue, currentIndex, handlers = {}) {
    queuePanel.replaceChildren();
    queue.forEach((track, index) => {
        const item = document.createElement("div");
        item.className = `audio-player__queue-item${index === currentIndex ? " is-active" : ""}`;
        item.dataset.playerQueueItem = "true";

        const button = document.createElement("button");
        button.type = "button";
        button.className = "audio-player__queue-track";
        button.textContent = getPlayerLabel(track);
        button.addEventListener("click", () => handlers.onSelect?.(index));

        const actions = document.createElement("div");
        actions.className = "audio-player__queue-actions";

        const moveUp = document.createElement("button");
        moveUp.type = "button";
        moveUp.className = "icon-button icon-button--ghost audio-player__queue-action";
        moveUp.innerHTML = '<span aria-hidden="true">&#8593;</span>';
        moveUp.disabled = index === 0;
        moveUp.setAttribute("aria-label", t("player.queue_move_up", {}, "Move track earlier"));
        moveUp.addEventListener("click", () => handlers.onMove?.(index, -1));

        const moveDown = document.createElement("button");
        moveDown.type = "button";
        moveDown.className = "icon-button icon-button--ghost audio-player__queue-action";
        moveDown.innerHTML = '<span aria-hidden="true">&#8595;</span>';
        moveDown.disabled = index === queue.length - 1;
        moveDown.setAttribute("aria-label", t("player.queue_move_down", {}, "Move track later"));
        moveDown.addEventListener("click", () => handlers.onMove?.(index, 1));

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "icon-button icon-button--ghost audio-player__queue-action";
        remove.innerHTML = '<span aria-hidden="true">&#10005;</span>';
        remove.setAttribute("aria-label", t("player.remove_from_queue", {}, "Remove track from queue"));
        remove.addEventListener("click", () => handlers.onRemove?.(index));

        actions.append(moveUp, moveDown, remove);
        item.append(button, actions);
        queuePanel.append(item);
    });
}

function initRemotePlayerShell(shell, elements) {
    const {
        audio,
        stateLabel,
        title,
        artist,
        toggle,
        previous,
        next,
        loopToggle,
        progress,
        current,
        duration,
        queueToggle,
        queuePanel,
        panel,
        bubble,
        collapseToggle,
        dragHandle,
        settings,
        settingsToggle,
        opacityInput,
        resetSizeButton,
        resizeHandle,
    } = elements;
    if (
        !(audio instanceof HTMLAudioElement) ||
        !(stateLabel instanceof HTMLElement) ||
        !(title instanceof HTMLElement) ||
        !(artist instanceof HTMLElement) ||
        !(toggle instanceof HTMLButtonElement) ||
        !(previous instanceof HTMLButtonElement) ||
        !(next instanceof HTMLButtonElement) ||
        !(loopToggle instanceof HTMLButtonElement) ||
        !(progress instanceof HTMLInputElement) ||
        !(current instanceof HTMLElement) ||
        !(duration instanceof HTMLElement) ||
        !(queueToggle instanceof HTMLButtonElement) ||
        !(queuePanel instanceof HTMLElement) ||
        !(panel instanceof HTMLElement) ||
        !(bubble instanceof HTMLButtonElement) ||
        !(collapseToggle instanceof HTMLButtonElement) ||
        !(dragHandle instanceof HTMLButtonElement) ||
        !(settingsToggle instanceof HTMLButtonElement) ||
        !(settings instanceof HTMLElement) ||
        !(opacityInput instanceof HTMLInputElement) ||
        !(resetSizeButton instanceof HTMLButtonElement) ||
        !(resizeHandle instanceof HTMLButtonElement)
    ) {
        return;
    }

    if (shell.dataset.playerInitialized === "true") {
        return;
    }
    shell.dataset.playerInitialized = "true";

    const pageCatalog = readTrackCatalog();
    let playerState = readStoredPlayerState(pageCatalog);
    let queueOpen = false;
    let settingsOpen = false;
    let isCollapsed = readStoredJson(playerDockStateKey)?.collapsed;
    if (typeof isCollapsed !== "boolean") {
        isCollapsed = true;
    }
    let customPosition = readStoredJson(playerDockPositionKey);
    let dragState = null;
    let resizeState = null;
    let queueDragState = null;
    let suppressBubbleClick = false;
    let suppressPanelClick = false;
    let lastPersistAt = 0;
    let playerAppearance = applyPlayerAppearance(shell, readPlayerAppearance(), { opacityInput });
    let playerSize = applyPlayerSize(shell, readPlayerSize());
    let audioTransitionToken = 0;
    let pauseContext = "idle";
    let lifecyclePauseReason = "";
    let videoSuspension = {
        shouldResume: false,
    };
    const initialResumeIntent = readPlayerResumeIntent();

    const clearPendingResumeIntent = () => {
        lifecyclePauseReason = "";
        clearPlayerResumeIntent();
    };

    const rememberResumeIntent = (reason = "navigation") => {
        const currentTrack = playerState.queue[playerState.currentIndex];
        const shouldResume = Boolean(currentTrack) && (playerState.wasPlaying || !audio.paused);
        lifecyclePauseReason = shouldResume ? reason : "";

        if (!shouldResume || !currentTrack) {
            clearPlayerResumeIntent();
            return false;
        }

        writePlayerResumeIntent({
            shouldResume: true,
            reason,
            timestamp: Date.now(),
            currentIndex: playerState.currentIndex,
            currentTime: audio.currentTime || playerState.currentTime,
            duration: Number.isFinite(audio.duration) ? audio.duration : playerState.duration,
            trackSrc: currentTrack.src,
        });
        return true;
    };

    const resumeFromPendingIntent = async ({ finalizeOnFailure = false } = {}) => {
        const intent = readPlayerResumeIntent();
        const currentTrack = playerState.queue[playerState.currentIndex];
        if (!intent || !currentTrack) {
            return false;
        }

        if (
            (intent.currentIndex >= 0 && intent.currentIndex !== playerState.currentIndex) ||
            (intent.trackSrc && intent.trackSrc !== currentTrack.src)
        ) {
            clearPendingResumeIntent();
            return false;
        }

        if (hasActiveAudibleVideo()) {
            return false;
        }

        if (intent.currentTime > 0 && Math.abs((audio.currentTime || 0) - intent.currentTime) > 1) {
            audio.currentTime = intent.currentTime;
        }

        if (!audio.paused) {
            clearPendingResumeIntent();
            return true;
        }

        try {
            await audio.play();
            clearPendingResumeIntent();
            return true;
        } catch {
            if (finalizeOnFailure) {
                clearPendingResumeIntent();
                playerState.wasPlaying = false;
                renderShell();
                persistState({ force: true });
            }
            return false;
        }
    };

    const hasActiveAudibleVideo = () =>
        Array.from(document.querySelectorAll("video")).some(
            (video) => !video.muted && !video.paused && !video.ended
        );

    const suspendPlayerForVideo = async () => {
        if (!playerState.queue[playerState.currentIndex]) {
            videoSuspension = { shouldResume: false };
            return;
        }

        if (audio.paused) {
            if (videoSuspension.shouldResume) {
                return;
            }
            videoSuspension = { shouldResume: false };
            return;
        }

        videoSuspension = { shouldResume: true };
        const token = ++audioTransitionToken;
        const startingVolume = audio.volume || 1;
        await animateMediaVolume(audio, startingVolume, 0, 180);
        if (token !== audioTransitionToken) {
            return;
        }
        pauseContext = "video";
        audio.pause();
        audio.volume = 1;
        persistState({ force: true });
        renderShell();
    };

    const resumePlayerAfterVideo = async () => {
        if (!videoSuspension.shouldResume || hasActiveAudibleVideo()) {
            return;
        }

        const currentTrack = playerState.queue[playerState.currentIndex];
        videoSuspension = { shouldResume: false };
        if (!currentTrack) {
            return;
        }

        const token = ++audioTransitionToken;
        try {
            audio.volume = 0;
            await audio.play();
            if (token !== audioTransitionToken) {
                return;
            }
            await animateMediaVolume(audio, 0, 1, 260);
        } catch {
            audio.volume = 1;
        }

        persistState({ force: true });
        renderShell();
    };

    const persistState = ({ force = false, preservePlayback = false } = {}) => {
        const now = Date.now();
        if (!force && now - lastPersistAt < 500) {
            return;
        }

        lastPersistAt = now;
        const currentTrack = playerState.queue[playerState.currentIndex];
        playerState = writeStoredPlayerState(
            {
                ...playerState,
                currentTime: audio.currentTime || 0,
                duration: Number.isFinite(audio.duration) ? audio.duration : playerState.duration,
                wasPlaying: preservePlayback
                    ? Boolean(currentTrack) && (playerState.wasPlaying || !audio.paused)
                    : !audio.paused,
            },
            pageCatalog
        );
    };

    const persistDockState = () => {
        window.localStorage.setItem(
            playerDockStateKey,
            JSON.stringify({ collapsed: Boolean(isCollapsed) })
        );
    };

    const persistDockPosition = (position) => {
        customPosition = position;
        window.localStorage.setItem(playerDockPositionKey, JSON.stringify(position));
    };

    const clearDockPosition = () => {
        customPosition = null;
        window.localStorage.removeItem(playerDockPositionKey);
        shell.style.removeProperty("left");
        shell.style.removeProperty("top");
        shell.style.removeProperty("right");
        shell.style.removeProperty("bottom");
    };

    const clampDockPosition = (left, top) => {
        const margin = 12;
        const shellWidth = Math.max(shell.offsetWidth || 0, isCollapsed ? 68 : 280);
        const shellHeight = Math.max(shell.offsetHeight || 0, isCollapsed ? 68 : 180);
        return {
            left: Math.min(Math.max(left, margin), Math.max(margin, window.innerWidth - shellWidth - margin)),
            top: Math.min(Math.max(top, margin), Math.max(margin, window.innerHeight - shellHeight - margin)),
        };
    };

    const applyDockPosition = () => {
        if (
            !customPosition ||
            typeof customPosition.left !== "number" ||
            typeof customPosition.top !== "number"
        ) {
            clearDockPosition();
            return;
        }

        const nextPosition = clampDockPosition(customPosition.left, customPosition.top);
        shell.style.left = `${nextPosition.left}px`;
        shell.style.top = `${nextPosition.top}px`;
        shell.style.right = "auto";
        shell.style.bottom = "auto";
        customPosition = nextPosition;
    };

    const updateQueuePlacement = () => {
        const rect = shell.getBoundingClientRect();
        const preferredQueueWidth = 320;
        const preferredQueueHeight = 280;
        const rightSpace = window.innerWidth - rect.right - 12;
        const leftSpace = rect.left - 12;
        const bottomSpace = window.innerHeight - rect.bottom - 12;
        const topSpace = rect.top - 12;

        let placement = "bottom";
        if (window.innerWidth <= 720) {
            placement = "mobile";
        } else if (rightSpace >= preferredQueueWidth) {
            placement = "right";
        } else if (leftSpace >= preferredQueueWidth) {
            placement = "left";
        } else if (bottomSpace >= preferredQueueHeight || bottomSpace >= topSpace) {
            placement = "bottom";
        } else {
            placement = "top";
        }

        queuePanel.dataset.playerQueuePlacement = placement;
    };

    const pinShellToRect = (rect) => {
        const nextPosition = clampDockPosition(rect.left, rect.top);
        shell.style.left = `${nextPosition.left}px`;
        shell.style.top = `${nextPosition.top}px`;
        shell.style.right = "auto";
        shell.style.bottom = "auto";
        customPosition = nextPosition;
    };

    const syncQueueDragPreview = () => {
        queuePanel.querySelectorAll("[data-player-queue-item]").forEach((item) => {
            if (!(item instanceof HTMLElement)) {
                return;
            }

            const itemIndex = Number(item.dataset.playerQueueIndex);
            item.classList.toggle("is-drag-source", itemIndex === queueDragState?.fromIndex);
            item.classList.toggle(
                "is-drop-target",
                itemIndex === queueDragState?.targetIndex && itemIndex !== queueDragState?.fromIndex
            );
        });
    };

    const clearQueueDragState = () => {
        queueDragState = null;
        queuePanel.classList.remove("is-queue-dragging");
        queuePanel.querySelectorAll(".is-drag-source, .is-drop-target").forEach((node) => {
            node.classList.remove("is-drag-source", "is-drop-target");
        });
    };

    const reorderTrackInQueue = (fromIndex, toIndex) => {
        if (
            fromIndex < 0 ||
            toIndex < 0 ||
            fromIndex >= playerState.queue.length ||
            toIndex >= playerState.queue.length ||
            fromIndex === toIndex
        ) {
            return;
        }

        const nextQueue = [...playerState.queue];
        const [movedTrack] = nextQueue.splice(fromIndex, 1);
        nextQueue.splice(toIndex, 0, movedTrack);

        let nextCurrentIndex = playerState.currentIndex;
        if (playerState.currentIndex === fromIndex) {
            nextCurrentIndex = toIndex;
        } else if (
            fromIndex < toIndex &&
            playerState.currentIndex > fromIndex &&
            playerState.currentIndex <= toIndex
        ) {
            nextCurrentIndex -= 1;
        } else if (
            fromIndex > toIndex &&
            playerState.currentIndex >= toIndex &&
            playerState.currentIndex < fromIndex
        ) {
            nextCurrentIndex += 1;
        }

        playerState = writeStoredPlayerState(
            {
                ...playerState,
                queue: nextQueue,
                currentIndex: nextCurrentIndex,
            },
            pageCatalog
        );
        renderShell();
    };

    const updateQueueDragTarget = (clientX, clientY) => {
        if (!queueDragState) {
            return;
        }

        const target = document.elementFromPoint(clientX, clientY)?.closest("[data-player-queue-item]");
        if (!(target instanceof HTMLElement) || !queuePanel.contains(target)) {
            return;
        }

        const targetIndex = Number(target.dataset.playerQueueIndex);
        if (!Number.isInteger(targetIndex)) {
            return;
        }

        queueDragState.targetIndex = targetIndex;
        syncQueueDragPreview();
    };

    const beginQueueDrag = (event, index) => {
        if (!(event instanceof PointerEvent) || event.button !== 0 || !queueOpen) {
            return;
        }

        queueDragState = {
            pointerId: event.pointerId,
            fromIndex: index,
            targetIndex: index,
        };
        queuePanel.classList.add("is-queue-dragging");
        syncQueueDragPreview();
        event.currentTarget?.setPointerCapture?.(event.pointerId);
        event.preventDefault();
        event.stopPropagation();
    };

    const applyCollapsedState = () => {
        shell.classList.toggle("is-audio-player-collapsed", isCollapsed);
        bubble.setAttribute("aria-expanded", String(!isCollapsed));
        collapseToggle.setAttribute(
            "aria-label",
            isCollapsed
                ? t("player.open_mini_player", {}, "Open mini player")
                : t("player.collapse_mini_player", {}, "Collapse mini player")
        );
        resizeHandle.hidden = isCollapsed;
        if (isCollapsed) {
            queueOpen = false;
            queuePanel.hidden = true;
            clearQueueDragState();
            shell.style.removeProperty("--player-panel-width");
            shell.style.removeProperty("--player-panel-height");
        } else {
            playerSize = applyPlayerSize(shell, playerSize);
        }
        panel.hidden = isCollapsed;
        settings.hidden = isCollapsed || !settingsOpen;
        settingsToggle.setAttribute("aria-expanded", String(!isCollapsed && settingsOpen));
        if (!shell.hidden) {
            window.requestAnimationFrame(() => {
                if (!isCollapsed) {
                    playerSize = applyPlayerSize(shell, playerSize);
                }
                applyDockPosition();
            });
        }
        persistDockState();
    };

    const persistBeforeNavigation = (reason = "navigation", { armPauseContext = false } = {}) => {
        if (shell.hidden) {
            clearPendingResumeIntent();
            return;
        }
        if (armPauseContext) {
            pauseContext = "lifecycle";
        }
        const shouldResume = rememberResumeIntent(reason);
        persistState({ force: true, preservePlayback: shouldResume });
    };

    const beginDrag = (event, source) => {
        if (!(event instanceof PointerEvent) || event.button !== 0) {
            return;
        }

        const rect = shell.getBoundingClientRect();
        dragState = {
            pointerId: event.pointerId,
            source,
            startX: event.clientX,
            startY: event.clientY,
            originLeft: rect.left,
            originTop: rect.top,
            moved: false,
        };
        shell.classList.add("is-audio-player-dragging");
        event.currentTarget?.setPointerCapture?.(event.pointerId);
        event.preventDefault();
    };

    const beginResize = (event) => {
        if (!(event instanceof PointerEvent) || event.button !== 0 || isCollapsed || shell.hidden) {
            return;
        }

        const rect = shell.getBoundingClientRect();
        pinShellToRect(rect);
        resizeState = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            originWidth: rect.width,
            originHeight: rect.height,
        };
        shell.classList.add("is-audio-player-resizing");
        event.currentTarget?.setPointerCapture?.(event.pointerId);
        event.preventDefault();
    };

    const waitForAudioReady = () =>
        new Promise((resolve) => {
            if (audio.readyState >= 1) {
                resolve();
                return;
            }

            const finish = () => {
                audio.removeEventListener("loadedmetadata", finish);
                audio.removeEventListener("error", finish);
                resolve();
            };

            audio.addEventListener("loadedmetadata", finish);
            audio.addEventListener("error", finish);
        });

    const renderShell = () => {
        const track = playerState.queue[playerState.currentIndex];
        shell.hidden = !track;
        previous.disabled = playerState.currentIndex <= 0;
        next.disabled =
            playerState.currentIndex < 0 || playerState.currentIndex >= playerState.queue.length - 1;
        shell.classList.toggle("is-player-playing", Boolean(track) && playerState.wasPlaying);
        loopToggle.classList.toggle("is-active", playerState.repeatMode === "one");
        loopToggle.setAttribute("aria-pressed", playerState.repeatMode === "one" ? "true" : "false");

        if (!track) {
            queueOpen = false;
            stateLabel.textContent = t("player.ready", {}, "Ready");
            title.textContent = t("player.ready", {}, "Ready");
            artist.textContent = t("player.ready", {}, "Ready");
            setPlayerToggleIcon(toggle, false);
            progress.value = "0";
            current.textContent = "00:00";
            duration.textContent = "00:00";
            queuePanel.hidden = true;
            renderPlayerQueue(queuePanel, playerState.queue, playerState.currentIndex, {});
            updatePlayerArtwork(shell, null);
            return;
        }

        stateLabel.textContent = playerState.wasPlaying
            ? t("player.now_playing", {}, "Now playing")
            : t("player.paused", {}, "Paused");
        title.textContent = track.title;
        artist.textContent = track.artist || t("music.personal_library", {}, "Personal music library");
        setPlayerToggleIcon(toggle, playerState.wasPlaying);
        current.textContent = secondsToClock(playerState.currentTime);
        duration.textContent = secondsToClock(playerState.duration);
        progress.value =
            playerState.duration > 0
                ? String((playerState.currentTime / playerState.duration) * 100)
                : "0";
        queuePanel.hidden = !queueOpen;
        if (queueOpen) {
            updateQueuePlacement();
        } else {
            clearQueueDragState();
        }
        renderPlayerQueue(queuePanel, playerState.queue, playerState.currentIndex, {
            onClose() {
                queueOpen = false;
                renderShell();
            },
            onDragStart(event, index) {
                beginQueueDrag(event, index);
            },
            onReorder(fromIndex, toIndex) {
                reorderTrackInQueue(fromIndex, toIndex);
            },
            onSelect(index) {
                queueOpen = false;
                void loadTrack(index, true, 0);
                renderShell();
            },
            onRemove(index) {
                removeTrackFromQueue(index);
            },
        });
        updatePlayerArtwork(shell, track);
        applyCollapsedState();
    };

    const clearAudio = () => {
        clearPendingResumeIntent();
        pauseContext = "clear";
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
        playerState = writeStoredPlayerState(
            {
                ...playerState,
                currentIndex: -1,
                currentTime: 0,
                duration: 0,
                wasPlaying: false,
            },
            pageCatalog
        );
        renderShell();
    };

    const loadTrack = async (index, autoplay, time = 0) => {
        const track = playerState.queue[index];
        if (!track) {
            clearAudio();
            return;
        }

        playerState = {
            ...playerState,
            currentIndex: index,
            currentTime: Math.max(Number(time) || 0, 0),
        };

        pauseContext = "track-change";
        audio.pause();
        audio.src = track.src;
        audio.load();
        renderShell();

        await waitForAudioReady();
        if (playerState.currentTime > 0) {
            audio.currentTime = Math.min(playerState.currentTime, audio.duration || playerState.currentTime);
        }

        if (autoplay) {
            try {
                await audio.play();
            } catch {
                // Some browsers block autoplay after a navigation; keep the player state visible.
            }
        }

        playerState = writeStoredPlayerState(
            {
                ...playerState,
                currentTime: audio.currentTime || playerState.currentTime,
                duration: Number.isFinite(audio.duration) ? audio.duration : playerState.duration,
                wasPlaying: !audio.paused,
            },
            pageCatalog
        );
        renderShell();
    };

    const moveTrackInQueue = (index, delta) => {
        const targetIndex = index + delta;
        if (
            index < 0 ||
            targetIndex < 0 ||
            index >= playerState.queue.length ||
            targetIndex >= playerState.queue.length
        ) {
            return;
        }

        const nextQueue = [...playerState.queue];
        const [movedTrack] = nextQueue.splice(index, 1);
        nextQueue.splice(targetIndex, 0, movedTrack);

        let nextCurrentIndex = playerState.currentIndex;
        if (playerState.currentIndex === index) {
            nextCurrentIndex = targetIndex;
        } else if (
            playerState.currentIndex >= Math.min(index, targetIndex) &&
            playerState.currentIndex <= Math.max(index, targetIndex)
        ) {
            nextCurrentIndex += index < targetIndex ? -1 : 1;
        }

        playerState = writeStoredPlayerState(
            {
                ...playerState,
                queue: nextQueue,
                currentIndex: nextCurrentIndex,
            },
            pageCatalog
        );
        renderShell();
    };

    const removeTrackFromQueue = (index) => {
        if (index < 0 || index >= playerState.queue.length) {
            return;
        }

        const removingCurrent = index === playerState.currentIndex;
        const nextQueue = playerState.queue.filter((_track, queueIndex) => queueIndex !== index);
        let nextCurrentIndex = playerState.currentIndex;
        if (nextCurrentIndex > index) {
            nextCurrentIndex -= 1;
        } else if (removingCurrent) {
            nextCurrentIndex = Math.min(index, nextQueue.length - 1);
        }

        playerState = writeStoredPlayerState(
            {
                ...playerState,
                queue: nextQueue,
                currentIndex: nextQueue.length ? nextCurrentIndex : -1,
            },
            pageCatalog
        );

        if (!nextQueue.length) {
            clearAudio();
            return;
        }

        if (removingCurrent) {
            void loadTrack(playerState.currentIndex, playerState.wasPlaying, 0);
            return;
        }

        renderShell();
    };

    const playTrackFromCatalog = async (trackId, startTime = 0) => {
        const catalog = pageCatalog.length ? pageCatalog : playerState.queue;
        const trackIndex = catalog.findIndex((track) => track.id === trackId);
        if (trackIndex < 0) {
            return;
        }

        if (!playerState.queue[playerState.currentIndex]) {
            isCollapsed = false;
        }

        playerState = normalizePlayerState(
            {
                queue: catalog,
                currentIndex: trackIndex,
                currentTime: startTime,
                wasPlaying: true,
                duration: 0,
            },
            pageCatalog
        );
        await loadTrack(trackIndex, true, startTime);
    };

    const togglePlayback = async () => {
        const currentTrack = playerState.queue[playerState.currentIndex];
        if (!currentTrack) {
            if (!pageCatalog.length) {
                return;
            }

            isCollapsed = false;
            playerState = normalizePlayerState(
                {
                    queue: pageCatalog,
                    currentIndex: 0,
                    currentTime: 0,
                    wasPlaying: true,
                    duration: 0,
                },
                pageCatalog
            );
            await loadTrack(0, true, 0);
            return;
        }

        if (audio.paused) {
            try {
                await audio.play();
            } catch {
                return;
            }
        } else {
            clearPendingResumeIntent();
            pauseContext = "manual";
            audio.pause();
        }

        persistState({ force: true });
        renderShell();
    };

    const seekTo = async (seconds, { autoplay = !audio.paused } = {}) => {
        if (!Number.isFinite(seconds) || !playerState.queue[playerState.currentIndex]) {
            return;
        }

        audio.currentTime = Math.max(seconds, 0);
        if (autoplay && audio.paused) {
            try {
                await audio.play();
            } catch {
                // Keep the new position even if autoplay is blocked.
            }
        }

        persistState({ force: true });
        renderShell();
    };

    const resetPlayerSize = () => {
        playerSize = writePlayerSize({
            width: 360,
            height: 300,
        });
        playerSize = applyPlayerSize(shell, playerSize);
        if (customPosition) {
            applyDockPosition();
            persistDockPosition(customPosition);
        }
    };

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) {
            return;
        }

        const trigger = event.target.closest("[data-track-play]");
        if (!trigger) {
            return;
        }

        void playTrackFromCatalog(Number(trigger.getAttribute("data-track-id")));
    });

    bubble.addEventListener("pointerdown", (event) => {
        beginDrag(event, "bubble");
    });

    bubble.addEventListener("click", (event) => {
        if (suppressBubbleClick) {
            suppressBubbleClick = false;
            event.preventDefault();
            return;
        }

        isCollapsed = false;
        applyCollapsedState();
    });

    dragHandle.addEventListener("pointerdown", (event) => {
        beginDrag(event, "handle");
    });

    shell.addEventListener("pointerdown", (event) => {
        if (isCollapsed || !(event.target instanceof Element)) {
            return;
        }

        if (
            event.target.closest(
                "button, input, a, label, select, textarea, [role='button'], [data-player-queue], [data-player-queue-item]"
            )
        ) {
            return;
        }

        beginDrag(event, "panel");
    });

    shell.addEventListener("click", (event) => {
        if (isCollapsed || !(event.target instanceof Element)) {
            return;
        }

        if (suppressPanelClick) {
            suppressPanelClick = false;
            event.preventDefault();
            return;
        }

        if (
            event.target.closest(
                "button, input, a, label, select, textarea, [role='button'], [data-player-queue], [data-player-queue-item], [data-player-title], [data-player-artist], [data-player-state], [data-player-artwork]"
            )
        ) {
            return;
        }

        if (!shell.contains(event.target)) {
            return;
        }

        isCollapsed = true;
        settingsOpen = false;
        applyCollapsedState();
    });

    collapseToggle.addEventListener("click", () => {
        isCollapsed = !isCollapsed;
        applyCollapsedState();
    });

    settingsToggle.addEventListener("click", () => {
        settingsOpen = !settingsOpen;
        applyCollapsedState();
    });

    opacityInput.addEventListener("input", () => {
        playerAppearance = writePlayerAppearance({
            ...playerAppearance,
            opacity: Number(opacityInput.value),
        });
        applyPlayerAppearance(shell, playerAppearance, { opacityInput });
        applyCollapsedState();
    });

    resetSizeButton.addEventListener("click", () => {
        resetPlayerSize();
    });

    resizeHandle.addEventListener("pointerdown", (event) => {
        beginResize(event);
    });

    toggle.addEventListener("click", () => {
        void togglePlayback();
    });

    previous.addEventListener("click", () => {
        if (playerState.currentIndex <= 0) {
            return;
        }

        void loadTrack(playerState.currentIndex - 1, true, 0);
    });

    next.addEventListener("click", () => {
        if (
            playerState.currentIndex < 0 ||
            playerState.currentIndex >= playerState.queue.length - 1
        ) {
            return;
        }

        void loadTrack(playerState.currentIndex + 1, true, 0);
    });

    loopToggle.addEventListener("click", () => {
        playerState = writeStoredPlayerState(
            {
                ...playerState,
                repeatMode: playerState.repeatMode === "one" ? "off" : "one",
            },
            pageCatalog
        );
        renderShell();
    });

    queueToggle.addEventListener("click", () => {
        queueOpen = !queueOpen;
        renderShell();
    });

    document.addEventListener("click", (event) => {
        if (!queueOpen || !(event.target instanceof Node)) {
            return;
        }

        if (shell.contains(event.target)) {
            return;
        }

        queueOpen = false;
        renderShell();
    });

    progress.addEventListener("input", () => {
        if (playerState.duration <= 0 || !playerState.queue[playerState.currentIndex]) {
            return;
        }

        void seekTo((Number(progress.value) / 100) * playerState.duration, {
            autoplay: playerState.wasPlaying,
        });
    });

    document.addEventListener(
        "click",
        (event) => {
            if (!(event.target instanceof Element)) {
                return;
            }

            const link = event.target.closest("a[href]");
            if (!(link instanceof HTMLAnchorElement)) {
                return;
            }

            if (
                link.target === "_blank" ||
                link.hasAttribute("download") ||
                (event instanceof MouseEvent &&
                    (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey))
            ) {
                return;
            }

            persistBeforeNavigation("navigation");
        },
        true
    );

    document.addEventListener(
        "submit",
        () => {
            persistBeforeNavigation("navigation");
        },
        true
    );

    document.addEventListener(
        "play",
        (event) => {
            if (event.target instanceof HTMLVideoElement && !event.target.muted && playerState.wasPlaying) {
                void suspendPlayerForVideo();
            }
        },
        true
    );

    document.addEventListener(
        "pause",
        (event) => {
            if (event.target instanceof HTMLVideoElement && !event.target.muted) {
                void resumePlayerAfterVideo();
            }
        },
        true
    );

    document.addEventListener(
        "ended",
        (event) => {
            if (event.target instanceof HTMLVideoElement && !event.target.muted) {
                void resumePlayerAfterVideo();
            }
        },
        true
    );

    audio.addEventListener("timeupdate", () => {
        playerState.currentTime = audio.currentTime || 0;
        playerState.duration = Number.isFinite(audio.duration) ? audio.duration : playerState.duration;
        playerState.wasPlaying = !audio.paused;
        renderShell();
        persistState();
    });

    audio.addEventListener("play", () => {
        pauseContext = "idle";
        clearPendingResumeIntent();
        playerState.wasPlaying = true;
        renderShell();
        persistState({ force: true });
    });

    audio.addEventListener("pause", () => {
        const activePauseContext = pauseContext;
        pauseContext = "idle";
        const isHiddenLifecyclePause =
            document.visibilityState === "hidden" &&
            !["track-change", "clear", "manual", "video"].includes(activePauseContext);
        const shouldPreservePlayback =
            (activePauseContext === "lifecycle" || isHiddenLifecyclePause) &&
            rememberResumeIntent(lifecyclePauseReason || "hidden");

        playerState.currentTime = audio.currentTime || playerState.currentTime;
        playerState.duration = Number.isFinite(audio.duration) ? audio.duration : playerState.duration;
        if (shouldPreservePlayback) {
            persistState({ force: true, preservePlayback: true });
            return;
        }

        clearPendingResumeIntent();
        playerState.wasPlaying = false;
        renderShell();
        persistState({ force: true });
    });

    audio.addEventListener("ended", () => {
        clearPendingResumeIntent();
        if (playerState.repeatMode === "one" && playerState.currentIndex >= 0) {
            void loadTrack(playerState.currentIndex, true, 0);
            return;
        }

        if (playerState.currentIndex < playerState.queue.length - 1) {
            void loadTrack(playerState.currentIndex + 1, true, 0);
            return;
        }

        playerState = writeStoredPlayerState(
            {
                ...playerState,
                currentTime: 0,
                wasPlaying: false,
            },
            pageCatalog
        );
        renderShell();
    });

    window.addEventListener("storage", (event) => {
        if (event.key !== playerStorageKey || !event.newValue) {
            return;
        }

        playerState = normalizePlayerState(readStoredJson(playerStorageKey), pageCatalog);
        renderShell();
    });

    window.addEventListener("pagehide", () => {
        persistBeforeNavigation("navigation", { armPauseContext: true });
    });

    window.addEventListener("beforeunload", () => {
        persistBeforeNavigation("navigation", { armPauseContext: true });
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") {
            persistBeforeNavigation("hidden", { armPauseContext: true });
            return;
        }

        if (document.visibilityState === "visible" && readPlayerResumeIntent()?.reason === "hidden") {
            pauseContext = "idle";
            void resumeFromPendingIntent({ finalizeOnFailure: true });
        }
    });

    document.addEventListener("app:after-swap", () => {
        if (videoSuspension.shouldResume) {
            void resumePlayerAfterVideo();
        }
    });

    window.addEventListener("pointermove", (event) => {
        if (resizeState && event.pointerId === resizeState.pointerId) {
            const deltaX = event.clientX - resizeState.startX;
            const deltaY = event.clientY - resizeState.startY;
            playerSize = applyPlayerSize(shell, {
                width: resizeState.originWidth + deltaX,
                height: resizeState.originHeight + deltaY,
            });
            if (customPosition) {
                applyDockPosition();
            }
            if (queueOpen) {
                updateQueuePlacement();
            }
            return;
        }

        if (queueDragState && event.pointerId === queueDragState.pointerId) {
            updateQueueDragTarget(event.clientX, event.clientY);
            return;
        }

        if (!dragState || event.pointerId !== dragState.pointerId) {
            return;
        }

        const deltaX = event.clientX - dragState.startX;
        const deltaY = event.clientY - dragState.startY;
        if (!dragState.moved && (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3)) {
            dragState.moved = true;
        }
        if (!dragState.moved) {
            return;
        }

        const nextPosition = clampDockPosition(
            dragState.originLeft + deltaX,
            dragState.originTop + deltaY
        );
        shell.style.left = `${nextPosition.left}px`;
        shell.style.top = `${nextPosition.top}px`;
        shell.style.right = "auto";
        shell.style.bottom = "auto";
        customPosition = nextPosition;
        if (queueOpen) {
            updateQueuePlacement();
        }
    });

    window.addEventListener("pointerup", (event) => {
        if (resizeState && event.pointerId === resizeState.pointerId) {
            resizeState = null;
            shell.classList.remove("is-audio-player-resizing");
            playerSize = writePlayerSize(playerSize);
            if (customPosition) {
                persistDockPosition(customPosition);
            }
            return;
        }

        if (queueDragState && event.pointerId === queueDragState.pointerId) {
            const { fromIndex, targetIndex } = queueDragState;
            clearQueueDragState();
            reorderTrackInQueue(fromIndex, targetIndex);
            return;
        }

        if (!dragState || event.pointerId !== dragState.pointerId) {
            return;
        }

        const didMove = dragState.moved;
        const source = dragState.source;
        dragState = null;
        shell.classList.remove("is-audio-player-dragging");

        if (didMove && customPosition) {
            persistDockPosition(customPosition);
            suppressBubbleClick = source === "bubble";
            suppressPanelClick = source === "panel";
        }
    });

    window.addEventListener("resize", () => {
        playerSize = applyPlayerSize(shell, playerSize);
        if (!isCollapsed) {
            playerSize = writePlayerSize(playerSize);
        }
        if (!shell.hidden) {
            applyDockPosition();
            if (queueOpen) {
                updateQueuePlacement();
            }
        }
    });

    if (playerState.currentIndex >= 0 && playerState.queue[playerState.currentIndex]) {
        const resumeTime =
            initialResumeIntent &&
            initialResumeIntent.trackSrc === playerState.queue[playerState.currentIndex].src
                ? initialResumeIntent.currentTime
                : playerState.currentTime;
        void loadTrack(
            playerState.currentIndex,
            Boolean(initialResumeIntent?.shouldResume) || playerState.wasPlaying,
            resumeTime
        );
        return;
    }

    clearPendingResumeIntent();
    renderShell();
}

function initGlobalPlayer() {
    const shell = document.querySelector("[data-audio-player]");
    if (!shell) {
        return;
    }

    const elements = {
        audio: shell.querySelector("[data-player-audio]"),
        stateLabel: shell.querySelector("[data-player-state]"),
        title: shell.querySelector("[data-player-title]"),
        artist: shell.querySelector("[data-player-artist]"),
        toggle: shell.querySelector("[data-player-toggle]"),
        previous: shell.querySelector("[data-player-prev]"),
        next: shell.querySelector("[data-player-next]"),
        loopToggle: shell.querySelector("[data-player-loop-toggle]"),
        progress: shell.querySelector("[data-player-progress]"),
        current: shell.querySelector("[data-player-current]"),
        duration: shell.querySelector("[data-player-duration]"),
        queueToggle: shell.querySelector("[data-player-queue-toggle]"),
        queuePanel: shell.querySelector("[data-player-queue]"),
        panel: shell.querySelector("[data-player-panel]"),
        bubble: shell.querySelector("[data-player-bubble]"),
        collapseToggle: shell.querySelector("[data-player-collapse-toggle]"),
        dragHandle: shell.querySelector("[data-player-drag-handle]"),
        settings: shell.querySelector("[data-player-settings]"),
        settingsToggle: shell.querySelector("[data-player-settings-toggle]"),
        opacityInput: shell.querySelector("[data-player-opacity-input]"),
        resetSizeButton: shell.querySelector("[data-player-reset-size]"),
        resizeHandle: shell.querySelector("[data-player-resize-handle]"),
    };

    initRemotePlayerShell(shell, elements);
}

function inferTrackTitleFromFilename(filename) {
    const stem = String(filename || "").replace(/\.[^.]+$/, "").trim();
    if (!stem) {
        return "";
    }
    return stem.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
}

function initTrackCreateForm() {
    const form = document.querySelector("[data-track-create-form]");
    if (!(form instanceof HTMLFormElement) || form.dataset.trackCreateBound === "true") {
        return;
    }
    form.dataset.trackCreateBound = "true";

    const signal = getLibraryPageSignal();
    const titleInput = form.querySelector("[data-track-title-input]");
    const audioInput = form.querySelector("[data-track-audio-input]");
    const dropzone = form.querySelector("[data-track-upload-dropzone]");
    const status = form.querySelector("[data-track-upload-status]");
    const coverInput = form.querySelector("[data-track-cover-input]");
    const lyricsInput = form.querySelector("[data-track-lyrics-input]");

    if (
        !(titleInput instanceof HTMLInputElement) ||
        !(audioInput instanceof HTMLInputElement) ||
        !(dropzone instanceof HTMLElement) ||
        !(status instanceof HTMLElement)
    ) {
        return;
    }

    const desktopDragEnabled = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    const allowedAudioPattern = /\.(mp3|m4a|wav|ogg|webm|flac|mp4)$/i;
    let userEditedTitle = false;

    const updateSupplementalInputs = (enabled) => {
        [coverInput, lyricsInput].forEach((input) => {
            if (!(input instanceof HTMLInputElement)) {
                return;
            }
            input.disabled = !enabled;
            if (!enabled) {
                input.value = "";
            }
            input.closest(".tracks-create-field")?.classList.toggle("is-field-disabled", !enabled);
        });
    };

    const updateSelectionState = () => {
        const files = Array.from(audioInput.files || []);
        const count = files.length;
        const isSingle = count === 1;
        const isMultiple = count > 1;

        titleInput.disabled = isMultiple;
        titleInput.closest(".tracks-create-field")?.classList.toggle("is-field-disabled", isMultiple);
        dropzone.classList.toggle("has-files", count > 0);
        dropzone.classList.toggle("is-multiple-files", isMultiple);

        if (isSingle) {
            const inferredTitle = inferTrackTitleFromFilename(files[0].name);
            if (!userEditedTitle || titleInput.dataset.autofilled === "true" || !titleInput.value.trim()) {
                titleInput.value = inferredTitle;
                titleInput.dataset.autofilled = "true";
            }
            status.textContent = t(
                "music.bulk_upload_single",
                { count },
                `${count} file selected. Title defaults to the file name.`
            );
            status.hidden = false;
        } else if (isMultiple) {
            if (!userEditedTitle || titleInput.dataset.autofilled === "true") {
                titleInput.value = "";
                titleInput.dataset.autofilled = "true";
            }
            status.textContent = `${t(
                "music.bulk_upload_multiple",
                { count },
                `${count} files selected. Each track will use its file name.`
            )} · ${t(
                "music.bulk_upload_assets_single_only",
                {},
                "Cover and lyrics stay available for single-track uploads."
            )}`;
            status.hidden = false;
        } else {
            if (titleInput.dataset.autofilled === "true") {
                titleInput.value = "";
            }
            titleInput.dataset.autofilled = "false";
            status.hidden = true;
            status.textContent = "";
        }

        updateSupplementalInputs(!isMultiple);
    };

    titleInput.addEventListener("input", () => {
        userEditedTitle = Boolean(titleInput.value.trim());
        titleInput.dataset.autofilled = "false";
    }, { signal });

    audioInput.addEventListener("change", () => {
        updateSelectionState();
    }, { signal });

    form.addEventListener("reset", () => {
        window.setTimeout(() => {
            userEditedTitle = false;
            titleInput.disabled = false;
            titleInput.dataset.autofilled = "false";
            updateSupplementalInputs(true);
            dropzone.classList.remove("has-files", "is-multiple-files", "is-dragover");
            status.hidden = true;
            status.textContent = "";
        }, 0);
    }, { signal });

    if (desktopDragEnabled) {
        dropzone.addEventListener("dragenter", (event) => {
            event.preventDefault();
            dropzone.classList.add("is-dragover");
        }, { signal });

        dropzone.addEventListener("dragover", (event) => {
            event.preventDefault();
            dropzone.classList.add("is-dragover");
        }, { signal });

        dropzone.addEventListener("dragleave", (event) => {
            if (event.target === dropzone) {
                dropzone.classList.remove("is-dragover");
            }
        }, { signal });

        dropzone.addEventListener("drop", (event) => {
            event.preventDefault();
            dropzone.classList.remove("is-dragover");

            const acceptedFiles = Array.from(event.dataTransfer?.files || []).filter((file) =>
                allowedAudioPattern.test(file.name)
            );
            if (!acceptedFiles.length) {
                return;
            }

            const transfer = new DataTransfer();
            acceptedFiles.forEach((file) => transfer.items.add(file));
            audioInput.files = transfer.files;
            audioInput.dispatchEvent(new Event("change", { bubbles: true }));
        }, { signal });
    }

    updateSelectionState();
}

export function initLibraryFeatures() {
    initVideoCardPreviews();
    initVideoUploadForms();
    initImmersiveReaderShells();
    initBookReaderSelection();
    initDocxReaders();
    initLinearReaderProgress();
    initSectionReaders();
    initEpubReaders();
    initTimestampHelpers();
    initTrackLyrics();
    initTrackCreateForm();
    initGlobalPlayer();
}
