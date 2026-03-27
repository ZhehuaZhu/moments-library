export function initVideoCardPreviews() {
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const previewVideos = document.querySelectorAll("[data-video-card-preview]");
    if (!previewVideos.length) {
        return;
    }

    previewVideos.forEach((video) => {
        if (!(video instanceof HTMLVideoElement) || video.dataset.previewBound === "true") {
            return;
        }

        const shell = video.closest("[data-video-card-link]");
        if (!(shell instanceof HTMLElement)) {
            return;
        }

        video.dataset.previewBound = "true";
        video.muted = true;
        video.loop = true;
        video.playsInline = true;

        const playPreview = () => {
            if (prefersReducedMotion) {
                return;
            }
            void video.play().catch(() => {});
        };

        const pausePreview = () => {
            video.pause();
            if (video.currentTime > 0) {
                video.currentTime = 0;
            }
        };

        shell.addEventListener("mouseenter", playPreview);
        shell.addEventListener("mouseleave", pausePreview);
        shell.addEventListener("focusin", playPreview);
        shell.addEventListener("focusout", pausePreview);
    });
}

export function initVideoUploadForms() {
    const uploadForms = document.querySelectorAll("[data-video-create-form]");
    if (!uploadForms.length) {
        return;
    }

    uploadForms.forEach((form) => {
        if (!(form instanceof HTMLFormElement) || form.dataset.uploadBound === "true") {
            return;
        }

        const fileInput = form.querySelector("[data-video-upload-input]");
        const submitButton = form.querySelector("[data-video-upload-submit]");
        const status = form.querySelector("[data-video-upload-status]");
        const uploadLimit = Number(form.dataset.uploadLimitBytes || "0");
        const idleMessage = form.dataset.uploadIdleMessage || "";
        const tooLargeMessage = form.dataset.uploadTooLargeMessage || "";
        const uploadingMessage = form.dataset.uploadingMessage || "";
        const uploadingButtonLabel = form.dataset.uploadingButtonLabel || "";
        const defaultSubmitLabel =
            submitButton instanceof HTMLButtonElement ? submitButton.textContent || "" : "";

        form.dataset.uploadBound = "true";

        const setStatus = (message, state = "") => {
            if (!(status instanceof HTMLElement)) {
                return;
            }
            status.textContent = message;
            status.dataset.state = state;
        };

        const setSubmitState = ({ disabled, label } = {}) => {
            if (!(submitButton instanceof HTMLButtonElement)) {
                return;
            }
            submitButton.disabled = Boolean(disabled);
            if (typeof label === "string") {
                submitButton.textContent = label;
            }
        };

        const validateFileSize = () => {
            if (!(fileInput instanceof HTMLInputElement) || !fileInput.files?.length || uploadLimit <= 0) {
                setStatus(idleMessage);
                setSubmitState({ disabled: false, label: defaultSubmitLabel });
                return true;
            }

            const [file] = fileInput.files;
            if (file.size > uploadLimit) {
                setStatus(tooLargeMessage, "error");
                setSubmitState({ disabled: true, label: defaultSubmitLabel });
                return false;
            }

            setStatus(idleMessage);
            setSubmitState({ disabled: false, label: defaultSubmitLabel });
            return true;
        };

        if (fileInput instanceof HTMLInputElement) {
            fileInput.addEventListener("change", validateFileSize);
        }

        form.addEventListener("submit", (event) => {
            if (!validateFileSize()) {
                event.preventDefault();
                return;
            }

            setStatus(uploadingMessage, "busy");
            setSubmitState({
                disabled: true,
                label: uploadingButtonLabel || defaultSubmitLabel,
            });
        });
    });
}
