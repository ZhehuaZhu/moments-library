const has = (selector) => Boolean(document.querySelector(selector));

document.addEventListener("DOMContentLoaded", async () => {
    const { initBodyFade } = await import("./modules/ui.js");
    initBodyFade();

    const tasks = [];

    if (has("[data-toggle-sidebar]")) {
        tasks.push(import("./modules/navigation.js").then(({ initNavigation }) => initNavigation()));
    }

    if (has('[data-modal="composer"]')) {
        tasks.push(import("./modules/composer.js").then(({ initComposerModal }) => initComposerModal()));
    }

    if (has('[data-modal="media-viewer"], [data-inline-video-tile], [data-media-preview]')) {
        tasks.push(import("./modules/media-viewer.js").then(({ initMediaViewer }) => initMediaViewer()));
    }

    if (has("[data-menu-toggle]")) {
        tasks.push(import("./modules/moment-menu.js").then(({ initMomentMenus }) => initMomentMenus()));
    }

    if (
        has(
            "[data-action='delete-moment'], [data-action='restore-moment'], [data-folder-moment-count], [data-folder-moment-list], [data-cross-post-action], [data-copy-cross-post-caption]",
        )
    ) {
        tasks.push(import("./modules/feed.js").then(({ initFeedInteractions }) => initFeedInteractions()));
    }

    if (has("[data-action='resolve-location']")) {
        tasks.push(
            import("./modules/geolocation.js").then(({ bindLocationResolver }) => {
                document.querySelectorAll("form").forEach((form) => bindLocationResolver(form));
            }),
        );
    }

    if (has("[data-reader-shell], [data-track-catalog], [data-book-selection-source], [data-docx-reader], [data-video-card-preview], [data-audio-player]")) {
        tasks.push(import("./modules/library.js").then(({ initLibraryFeatures }) => initLibraryFeatures()));
    }

    if (has("[data-footprints-map], [data-footprints-shell]")) {
        tasks.push(import("./modules/footprints.js").then(({ initFootprintsMap }) => initFootprintsMap()));
    }

    await Promise.all(tasks);
});
