import { secondsToClock } from "./library-time-utils.js";

let timestampHelpersInitialized = false;

export function initTimestampHelpers() {
    if (timestampHelpersInitialized) {
        return;
    }
    timestampHelpersInitialized = true;
    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) {
            return;
        }

        const useCurrentTime = event.target.closest("[data-use-current-time]");
        if (useCurrentTime) {
            const scope =
                useCurrentTime.closest(".detail-card") ||
                useCurrentTime.closest(".library-detail-grid") ||
                document;
            const media = scope.querySelector("[data-timestamp-media]");
            const input = scope.querySelector("[data-timestamp-input]");
            if (media instanceof HTMLMediaElement && input instanceof HTMLInputElement) {
                input.value = secondsToClock(media.currentTime);
            }
            return;
        }

        const seekButton = event.target.closest("[data-seek-to]");
        if (!seekButton) {
            return;
        }

        const scope =
            seekButton.closest(".library-detail-grid") ||
            seekButton.closest(".detail-card") ||
            document;
        const media = scope.querySelector("[data-timestamp-media]");
        const seconds = Number(seekButton.getAttribute("data-seek-to"));
        if (media instanceof HTMLMediaElement && !Number.isNaN(seconds)) {
            media.currentTime = seconds;
            media.play().catch(() => {});
        }
    });
}

export function initTrackLyrics() {
    const shells = document.querySelectorAll("[data-lyrics-shell]");
    if (!shells.length) {
        return;
    }

    shells.forEach((shell) => {
        if (!(shell instanceof HTMLElement) || shell.dataset.lyricsBound === "true") {
            return;
        }
        shell.dataset.lyricsBound = "true";

        const scope = shell.closest(".library-detail-grid") || shell;
        const media = scope.querySelector("[data-timestamp-media]");
        const lines = Array.from(shell.querySelectorAll("[data-lyrics-line]")).filter(
            (line) => line instanceof HTMLButtonElement
        );
        if (!(media instanceof HTMLMediaElement) || !lines.length) {
            return;
        }

        let activeLine = null;

        const setActiveLine = (nextLine) => {
            if (activeLine === nextLine) {
                return;
            }

            if (activeLine instanceof HTMLElement) {
                activeLine.classList.remove("is-active");
            }

            activeLine = nextLine instanceof HTMLElement ? nextLine : null;
            if (!(activeLine instanceof HTMLElement)) {
                return;
            }

            activeLine.classList.add("is-active");
            activeLine.scrollIntoView({
                behavior: "smooth",
                block: "nearest",
            });
        };

        const syncLyrics = () => {
            const currentTime = media.currentTime;
            let matchedLine = null;

            lines.forEach((line) => {
                const start = Number(line.getAttribute("data-lyrics-start"));
                const next = Number(line.getAttribute("data-lyrics-next"));
                if (!Number.isFinite(start) || currentTime < start) {
                    return;
                }

                if (!Number.isFinite(next) || currentTime < next) {
                    matchedLine = line;
                }
            });

            setActiveLine(matchedLine);
        };

        media.addEventListener("loadedmetadata", syncLyrics);
        media.addEventListener("timeupdate", syncLyrics);
        media.addEventListener("seeked", syncLyrics);
        media.addEventListener("emptied", () => {
            setActiveLine(null);
        });

        syncLyrics();
    });
}
