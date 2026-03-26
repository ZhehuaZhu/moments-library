import { initComposerModal } from "./modules/composer.js";
import { initFeedInteractions } from "./modules/feed.js";
import { initBodyFade } from "./modules/ui.js";
import { initMomentMenus } from "./modules/moment-menu.js";
import { initNavigation } from "./modules/navigation.js";
import { bindLocationResolver } from "./modules/geolocation.js";
import { initMediaViewer } from "./modules/media-viewer.js";
import { initLibraryFeatures } from "./modules/library.js";
import { initFootprintsMap } from "./modules/footprints.js";

document.addEventListener("DOMContentLoaded", () => {
    initBodyFade();
    initNavigation();
    initComposerModal();
    initMediaViewer();
    initMomentMenus();
    initFeedInteractions();
    initLibraryFeatures();
    initFootprintsMap();
    document.querySelectorAll("form").forEach((form) => bindLocationResolver(form));
});
