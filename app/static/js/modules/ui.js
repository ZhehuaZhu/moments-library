export function initBodyFade() {
    requestAnimationFrame(() => {
        document.body.classList.add("is-ready");
    });
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
