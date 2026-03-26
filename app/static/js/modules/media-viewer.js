import { ensureMammoth } from "./vendor-loader.js";

let mediaViewerController = null;

function getMediaViewerSignal() {
    if (!(mediaViewerController instanceof AbortController) || mediaViewerController.signal.aborted) {
        mediaViewerController = new AbortController();
    }
    return mediaViewerController.signal;
}

document.addEventListener("app:before-swap", () => {
    mediaViewerController?.abort();
    mediaViewerController = null;
});

function syncBodyModalState() {
    const hasVisibleModal = Array.from(document.querySelectorAll(".modal-shell")).some(
        (modal) => !modal.hidden
    );
    document.body.classList.toggle("is-modal-open", hasVisibleModal);
}

async function buildViewerContent(kind, src, title, mimeType, payload = {}) {
    if (kind === "image") {
        const image = document.createElement("img");
        image.className = "media-viewer__image";
        image.src = src;
        image.alt = title;
        image.loading = "eager";
        return image;
    }

    if (kind === "video") {
        const video = document.createElement("video");
        video.className = "media-viewer__video";
        video.src = src;
        video.controls = true;
        video.playsInline = true;
        video.preload = "metadata";
        if (mimeType) {
            video.setAttribute("type", mimeType);
        }
        return video;
    }

    if (kind === "pdf") {
        const embed = document.createElement("embed");
        embed.className = "media-viewer__pdf";
        embed.src = src;
        embed.type = mimeType || "application/pdf";
        return embed;
    }

    if (kind === "docx") {
        if (!payload.file) {
            throw new Error("Missing DOCX file for preview.");
        }

        const mammoth = await ensureMammoth();

        const arrayBuffer = await payload.file.arrayBuffer();
        const result = await mammoth.convertToHtml({ arrayBuffer });

        const wrapper = document.createElement("article");
        wrapper.className = "media-viewer__docx";
        wrapper.innerHTML = result.value;

        if (result.messages?.length) {
            const notes = document.createElement("div");
            notes.className = "media-viewer__docx-notes";
            result.messages.forEach((message) => {
                const line = document.createElement("p");
                line.textContent = message.message;
                notes.append(line);
            });
            wrapper.append(notes);
        }

        return wrapper;
    }

    if (kind === "text") {
        if (!payload.file) {
            throw new Error("Missing text file for preview.");
        }

        const pre = document.createElement("pre");
        pre.className = "media-viewer__text";
        pre.textContent = await payload.file.text();
        return pre;
    }

    const fallback = document.createElement("div");
    fallback.className = "media-viewer__fallback";
    fallback.textContent =
        kind === "doc"
            ? "Legacy .doc files cannot be reliably previewed in the browser. Converting to PDF or DOCX is recommended."
            : "Preview is not available for this file type.";
    return fallback;
}

export function initMediaViewer() {
    const modal = document.querySelector('[data-modal="media-viewer"]');
    if (!modal || modal.dataset.viewerInitialized === "true") {
        return;
    }
    modal.dataset.viewerInitialized = "true";
    const signal = getMediaViewerSignal();

    const body = modal.querySelector("[data-media-viewer-body]");
    const previousButton = modal.querySelector("[data-media-viewer-prev]");
    const nextButton = modal.querySelector("[data-media-viewer-next]");
    const counter = modal.querySelector("[data-media-viewer-counter]");

    if (!body || !previousButton || !nextButton || !counter) {
        return;
    }

    let activeItems = [];
    let activeIndex = -1;
    let renderToken = 0;
    const prefersCoarsePointer = window.matchMedia("(pointer: coarse)").matches;

    const syncInlineVideoButton = (tile, isPlaying) => {
        const toggle = tile?.querySelector("[data-inline-video-toggle]");
        const label = tile?.querySelector("[data-inline-video-label]");
        if (!toggle || !label) {
            return;
        }

        const playLabel = toggle.dataset.playLabel || "Play";
        const pauseLabel = toggle.dataset.pauseLabel || "Pause";
        const nextLabel = isPlaying ? pauseLabel : playLabel;

        label.textContent = nextLabel;
        toggle.setAttribute("aria-pressed", isPlaying ? "true" : "false");
        toggle.setAttribute("aria-label", nextLabel);
    };

    const pauseInlineVideoTile = (tile) => {
        const video = tile?.querySelector("[data-inline-video]");
        if (!video) {
            return;
        }

        video.pause();
        tile.classList.remove("is-playing");
        syncInlineVideoButton(tile, false);
    };

    const pauseOtherInlineVideos = (activeTile = null) => {
        document.querySelectorAll("[data-inline-video-tile]").forEach((tile) => {
            if (tile === activeTile) {
                return;
            }
            pauseInlineVideoTile(tile);
        });
    };

    const toggleInlineVideoTile = (tile) => {
        const video = tile?.querySelector("[data-inline-video]");
        if (!video) {
            return;
        }

        if (!video.paused && !video.ended) {
            pauseInlineVideoTile(tile);
            return;
        }

        pauseOtherInlineVideos(tile);
        tile.classList.add("is-playing");
        syncInlineVideoButton(tile, true);
        video.muted = true;
        video.loop = true;
        video.playsInline = true;
        void video.play().catch(() => {
            tile.classList.remove("is-playing");
            syncInlineVideoButton(tile, false);
        });
    };

    document.querySelectorAll("[data-inline-video-tile]").forEach((tile) => {
        const video = tile.querySelector("[data-inline-video]");
        if (!video) {
            return;
        }

        syncInlineVideoButton(tile, false);

        if (prefersCoarsePointer) {
            video.preload = "none";
        }

        video.addEventListener("play", () => {
            pauseOtherInlineVideos(tile);
            tile.classList.add("is-playing");
            syncInlineVideoButton(tile, true);
        }, { signal });

        video.addEventListener("pause", () => {
            tile.classList.remove("is-playing");
            syncInlineVideoButton(tile, false);
        }, { signal });

        if (!prefersCoarsePointer && video.readyState === 0) {
            video.load();
        }
    });

    const closeModal = () => {
        body.querySelectorAll("video").forEach((video) => {
            video.pause();
            video.currentTime = 0;
        });
        body.replaceChildren();
        modal.hidden = true;
        delete modal.dataset.viewerKind;
        activeItems = [];
        activeIndex = -1;
        syncBodyModalState();
    };

    const renderActiveItem = async () => {
        const trigger = activeItems[activeIndex];
        if (!trigger) {
            return;
        }

        const kind = trigger.dataset.previewKind || "";
        const src = trigger.dataset.previewSrc || "";
        const fileTitle = trigger.dataset.previewTitle || "Attachment Preview";
        const mimeType = trigger.dataset.previewMime || "";
        const payload = trigger.previewPayload || {};

        if (!kind || !src) {
            return;
        }

        const currentToken = ++renderToken;
        body.replaceChildren();
        modal.dataset.viewerKind = kind;
        counter.textContent = `${activeIndex + 1} / ${activeItems.length}`;
        previousButton.disabled = activeIndex <= 0;
        nextButton.disabled = activeIndex >= activeItems.length - 1;

        const loading = document.createElement("div");
        loading.className = "media-viewer__loading";
        loading.textContent = kind === "docx" ? "Preparing DOCX preview..." : "Preparing preview...";
        body.append(loading);

        try {
            const content = await buildViewerContent(kind, src, fileTitle, mimeType, payload);
            if (currentToken !== renderToken) {
                return;
            }
            body.replaceChildren(content);
        } catch (error) {
            if (currentToken !== renderToken) {
                return;
            }
            const fallback = document.createElement("div");
            fallback.className = "media-viewer__fallback";
            fallback.textContent =
                error instanceof Error ? error.message : "Preview could not be generated.";
            body.replaceChildren(fallback);
        }

        const video = body.querySelector("video");
        if (video) {
            void video.play().catch(() => {});
        }
    };

    const collectGroupItems = (trigger) => {
        const group = trigger.dataset.previewGroup;
        if (group) {
            return Array.from(
                document.querySelectorAll(`[data-media-preview][data-preview-group="${group}"]`)
            );
        }

        const card = trigger.closest("[data-moment-card]");
        if (!card) {
            return [trigger];
        }

        return Array.from(card.querySelectorAll("[data-media-preview]"));
    };

    const openModal = (trigger) => {
        pauseOtherInlineVideos();
        activeItems = collectGroupItems(trigger);
        activeIndex = activeItems.indexOf(trigger);

        if (activeIndex < 0) {
            activeItems = [trigger];
            activeIndex = 0;
        }

        renderActiveItem();
        modal.hidden = false;
        syncBodyModalState();
    };

    const step = (direction) => {
        if (!activeItems.length) {
            return;
        }

        const nextIndex = activeIndex + direction;
        if (nextIndex < 0 || nextIndex >= activeItems.length) {
            return;
        }

        activeIndex = nextIndex;
        renderActiveItem();
    };

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) {
            return;
        }

        const inlineToggle = event.target.closest("[data-inline-video-toggle]");
        if (inlineToggle) {
            const tile = inlineToggle.closest("[data-inline-video-tile]");
            if (tile) {
                toggleInlineVideoTile(tile);
            }
            return;
        }

        const trigger = event.target.closest("[data-media-preview]");
        if (!trigger) {
            return;
        }

        const inlineTile = trigger.closest("[data-inline-video-tile]");
        if (inlineTile) {
            pauseInlineVideoTile(inlineTile);
        }

        openModal(trigger);
    }, { signal });

    modal.querySelectorAll("[data-close-media-viewer]").forEach((button) => {
        button.addEventListener("click", closeModal, { signal });
    });

    body.addEventListener("click", (event) => {
        if (event.target === body) {
            closeModal();
        }
    }, { signal });

    previousButton.addEventListener("click", () => step(-1), { signal });
    nextButton.addEventListener("click", () => step(1), { signal });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) {
            closeModal();
            return;
        }

        if (modal.hidden) {
            return;
        }

        if (event.key === "ArrowLeft") {
            event.preventDefault();
            step(-1);
        } else if (event.key === "ArrowRight") {
            event.preventDefault();
            step(1);
        }
    }, { signal });
}
