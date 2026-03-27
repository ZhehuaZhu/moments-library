import { initApp } from "./modules/app-bootstrap.js";
import { registerPwa } from "./modules/pwa.js";

document.addEventListener("DOMContentLoaded", () => {
    registerPwa();
    void initApp();
});
