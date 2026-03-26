const moduleLoaders = {
    ui: () => import("./modules/ui.js"),
    navigation: () => import("./modules/navigation.js"),
    composer: () => import("./modules/composer.js"),
    mediaViewer: () => import("./modules/media-viewer.js"),
    momentMenu: () => import("./modules/moment-menu.js"),
    feed: () => import("./modules/feed.js"),
    geolocation: () => import("./modules/geolocation.js"),
    library: () => import("./modules/library.js"),
    footprints: () => import("./modules/footprints.js"),
    pjax: () => import("./modules/pjax.js"),
};

const moduleCache = new Map();

function has(selector) {
    return Boolean(document.querySelector(selector));
}

async function loadModule(name) {
    if (!moduleCache.has(name)) {
        moduleCache.set(name, moduleLoaders[name]());
    }
    return moduleCache.get(name);
}

async function bootstrapPage() {
    const tasks = [];

    if (has("[data-toggle-sidebar]")) {
        tasks.push(loadModule("navigation").then(({ initNavigation }) => initNavigation()));
    }

    if (has('[data-modal="composer"]')) {
        tasks.push(loadModule("composer").then(({ initComposerModal }) => initComposerModal()));
    }

    if (has('[data-modal="media-viewer"], [data-inline-video-tile], [data-media-preview]')) {
        tasks.push(loadModule("mediaViewer").then(({ initMediaViewer }) => initMediaViewer()));
    }

    if (has("[data-menu-toggle]")) {
        tasks.push(loadModule("momentMenu").then(({ initMomentMenus }) => initMomentMenus()));
    }

    if (
        has(
            "[data-action='delete-moment'], [data-action='restore-moment'], [data-folder-moment-count], [data-folder-moment-list], [data-cross-post-action], [data-copy-cross-post-caption]",
        )
    ) {
        tasks.push(loadModule("feed").then(({ initFeedInteractions }) => initFeedInteractions()));
    }

    if (has("[data-action='resolve-location']")) {
        tasks.push(
            loadModule("geolocation").then(({ bindLocationResolver }) => {
                document.querySelectorAll("form").forEach((form) => bindLocationResolver(form));
            }),
        );
    }

    if (has("[data-reader-shell], [data-track-catalog], [data-book-selection-source], [data-docx-reader], [data-video-card-preview], [data-audio-player]")) {
        tasks.push(loadModule("library").then(({ initLibraryFeatures }) => initLibraryFeatures()));
    }

    if (has("[data-footprints-map], [data-footprints-shell]")) {
        tasks.push(loadModule("footprints").then(({ initFootprintsMap }) => initFootprintsMap()));
    }

    await Promise.all(tasks);
}

document.addEventListener("DOMContentLoaded", async () => {
    const { initBodyFade } = await loadModule("ui");
    initBodyFade();

    await bootstrapPage();

    if (has("[data-app-shell]") && has("[data-audio-player]")) {
        const { initPjax } = await loadModule("pjax");
        initPjax({ bootstrapPage });
    }
});
