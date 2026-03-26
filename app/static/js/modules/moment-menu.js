function closeAllSharePanels(scope = document) {
    scope.querySelectorAll("[data-share-platforms]").forEach((panel) => {
        panel.hidden = true;
    });

    scope.querySelectorAll("[data-toggle-share-platforms]").forEach((button) => {
        button.setAttribute("aria-expanded", "false");
    });
}

function closeAllMenus(except = null) {
    document.querySelectorAll("[data-card-menu]").forEach((menu) => {
        if (menu === except) {
            return;
        }
        menu.hidden = true;
        closeAllSharePanels(menu);
    });

    document.querySelectorAll("[data-menu-toggle]").forEach((button) => {
        const expanded = except && button.nextElementSibling === except;
        button.setAttribute("aria-expanded", expanded ? "true" : "false");
    });
}

export function initMomentMenus() {
    const toggles = document.querySelectorAll("[data-menu-toggle]");
    if (!toggles.length) {
        return;
    }

    toggles.forEach((button) => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            const menu = button.parentElement?.querySelector("[data-card-menu]");
            if (!menu) {
                return;
            }

            const willOpen = menu.hidden;
            closeAllMenus();
            menu.hidden = !willOpen;
            if (willOpen) {
                closeAllSharePanels(menu);
            }
            button.setAttribute("aria-expanded", willOpen ? "true" : "false");
        });
    });

    document.querySelectorAll("[data-toggle-share-platforms]").forEach((button) => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            const menu = button.closest("[data-card-menu]");
            const panel = menu?.querySelector("[data-share-platforms]");
            if (!menu || !panel) {
                return;
            }

            const willOpen = panel.hidden;
            closeAllSharePanels(menu);
            panel.hidden = !willOpen;
            button.setAttribute("aria-expanded", willOpen ? "true" : "false");
        });
    });

    document.addEventListener("click", (event) => {
        if (event.target instanceof Element && event.target.closest("[data-menu-root]")) {
            return;
        }
        closeAllMenus();
    });
}
