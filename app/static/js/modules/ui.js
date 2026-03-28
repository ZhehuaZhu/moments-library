export function initBodyFade() {
    requestAnimationFrame(() => {
        document.body.classList.add("is-ready");
    });
}

function isStandaloneLaunchMode() {
    return (
        window.matchMedia("(display-mode: standalone)").matches ||
        window.matchMedia("(display-mode: fullscreen)").matches ||
        window.navigator.standalone === true
    );
}

export function initLaunchScreen() {
    const launchScreen = document.querySelector("[data-launch-screen]");
    if (!(launchScreen instanceof HTMLElement)) {
        return;
    }

    if (!isStandaloneLaunchMode()) {
        launchScreen.remove();
        return;
    }

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const visibleDuration = prefersReducedMotion ? 220 : 1450;
    const exitDuration = prefersReducedMotion ? 180 : 620;

    document.body.classList.add("has-launch-screen");
    launchScreen.setAttribute("aria-hidden", "false");
    launchScreen.classList.add("is-visible");

    window.setTimeout(() => {
        launchScreen.classList.add("is-exiting");
        launchScreen.setAttribute("aria-hidden", "true");
    }, visibleDuration);

    window.setTimeout(() => {
        document.body.classList.remove("has-launch-screen");
        launchScreen.remove();
    }, visibleDuration + exitDuration);
}

export function syncEmptyState() {
    const feed = document.querySelector("#moments-feed");
    if (!feed) {
        return;
    }

    const cards = feed.querySelectorAll("[data-moment-card]");
    const emptyState = feed.querySelector("[data-empty-state]");
    if (emptyState) {
        emptyState.hidden = cards.length > 0;
    }
}

export function shouldRemoveCardForFilter(feed, categoryId) {
    const filterMode = feed.dataset.filterMode;
    const filterKey = feed.dataset.filterKey;

    if (filterMode === "all" || filterMode === "recycle") {
        return false;
    }

    if (filterMode === "uncategorized") {
        return categoryId !== null;
    }

    if (filterMode === "category") {
        return String(categoryId || "") !== String(filterKey);
    }

    return false;
}
