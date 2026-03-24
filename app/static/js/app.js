import { initComposerModal } from "./modules/composer.js";
import { initFeedInteractions } from "./modules/feed.js";
import { initBodyFade } from "./modules/ui.js";
import { initMomentMenus } from "./modules/moment-menu.js";
import { initNavigation } from "./modules/navigation.js";
import { bindLocationResolver } from "./modules/geolocation.js";

document.addEventListener("DOMContentLoaded", () => {
    initBodyFade();
    initNavigation();
    initComposerModal();
    initMomentMenus();
    initFeedInteractions();
    document.querySelectorAll("form").forEach((form) => bindLocationResolver(form));
});
