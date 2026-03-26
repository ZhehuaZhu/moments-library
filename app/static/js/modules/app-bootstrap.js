const moduleLoaders = {
    ui: () => import("./ui.js"),
    navigation: () => import("./navigation.js"),
    composer: () => import("./composer.js"),
    mediaViewer: () => import("./media-viewer.js"),
    momentMenu: () => import("./moment-menu.js"),
    feed: () => import("./feed.js"),
    geolocation: () => import("./geolocation.js"),
    library: () => import("./library.js"),
    footprints: () => import("./footprints.js"),
    pjax: () => import("./pjax.js"),
};

const bootstrapEntries = [
    {
        selector: "[data-toggle-sidebar]",
        module: "navigation",
        init: "initNavigation",
    },
    {
        selector: '[data-modal="composer"]',
        module: "composer",
        init: "initComposerModal",
    },
    {
        selector: '[data-modal="media-viewer"], [data-inline-video-tile], [data-media-preview]',
        module: "mediaViewer",
        init: "initMediaViewer",
    },
    {
        selector: "[data-menu-toggle]",
        module: "momentMenu",
        init: "initMomentMenus",
    },
    {
        selector:
            "[data-action='delete-moment'], [data-action='restore-moment'], [data-folder-moment-count], [data-folder-moment-list], [data-cross-post-action], [data-copy-cross-post-caption], [data-share-platform], [data-toggle-share-platforms]",
        module: "feed",
        init: "initFeedInteractions",
    },
    {
        selector:
            "[data-reader-shell], [data-track-catalog], [data-book-selection-source], [data-docx-reader], [data-video-card-preview], [data-audio-player]",
        module: "library",
        init: "initLibraryFeatures",
    },
    {
        selector: "[data-footprints-map], [data-footprints-shell]",
        module: "footprints",
        init: "initFootprintsMap",
    },
];

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

function queueModuleInit(tasks, entry) {
    if (!has(entry.selector)) {
        return;
    }

    tasks.push(
        loadModule(entry.module).then((loaded) => {
            const initializer = loaded[entry.init];
            if (typeof initializer === "function") {
                return initializer();
            }
            return undefined;
        }),
    );
}

function queueLocationResolvers(tasks) {
    if (!has("[data-action='resolve-location']")) {
        return;
    }

    tasks.push(
        loadModule("geolocation").then(({ bindLocationResolver }) => {
            document.querySelectorAll("form").forEach((form) => bindLocationResolver(form));
        }),
    );
}

export async function bootstrapPage() {
    const tasks = [];

    bootstrapEntries.forEach((entry) => queueModuleInit(tasks, entry));
    queueLocationResolvers(tasks);

    await Promise.all(tasks);
}

export async function initApp() {
    const { initBodyFade } = await loadModule("ui");
    initBodyFade();

    await bootstrapPage();

    if (has("[data-app-shell]") && has("[data-audio-player]")) {
        const { initPjax } = await loadModule("pjax");
        initPjax({ bootstrapPage });
    }
}
