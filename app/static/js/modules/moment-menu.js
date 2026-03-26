function closeAllMenus(except = null) {
    document.querySelectorAll("[data-card-menu]").forEach((menu) => {
        if (menu === except) {
            return;
        }
        menu.hidden = true;
    });

    document.querySelectorAll("[data-menu-toggle]").forEach((button) => {
        const expanded = except && button.nextElementSibling === except;
        button.setAttribute("aria-expanded", expanded ? "true" : "false");
    });
}

let menuGlobalsBound = false;

export function initMomentMenus() {
    const toggles = document.querySelectorAll("[data-menu-toggle]");
    if (!toggles.length) {
        return;
    }

    toggles.forEach((button) => {
        if (button.dataset.menuBound === "true") {
            return;
        }
        button.dataset.menuBound = "true";
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            const menu = button.parentElement?.querySelector("[data-card-menu]");
            if (!menu) {
                return;
            }

            const willOpen = menu.hidden;
            closeAllMenus();
            menu.hidden = !willOpen;
            button.setAttribute("aria-expanded", willOpen ? "true" : "false");
        });
    });

    if (!menuGlobalsBound) {
        menuGlobalsBound = true;
        document.addEventListener("click", (event) => {
            if (event.target instanceof Element && event.target.closest("[data-menu-root]")) {
                return;
            }
            closeAllMenus();
        });
    }
}
