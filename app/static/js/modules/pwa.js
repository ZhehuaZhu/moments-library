export function registerPwa() {
    if (!("serviceWorker" in navigator)) {
        return;
    }

    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/service-worker.js").catch(() => {
            // Keep the app usable even if PWA registration fails.
        });
    });
}
