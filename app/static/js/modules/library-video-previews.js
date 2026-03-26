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
