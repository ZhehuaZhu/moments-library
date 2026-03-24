const mobileQuery = window.matchMedia("(max-width: 1080px)");
const collapsedKey = "moments-sidebar-collapsed";

function applyOverlayState() {
    const overlay = document.querySelector("[data-sidebar-overlay]");
    if (!overlay) {
        return;
    }

    const isOpen = document.body.classList.contains("is-sidebar-open");
    overlay.hidden = !isOpen;
}

function closeMobileSidebar() {
    document.body.classList.remove("is-sidebar-open");
    applyOverlayState();
}

function toggleSidebar() {
    if (mobileQuery.matches) {
        document.body.classList.toggle("is-sidebar-open");
        applyOverlayState();
        return;
    }

    document.body.classList.toggle("is-sidebar-collapsed");
    const collapsed = document.body.classList.contains("is-sidebar-collapsed");
    window.localStorage.setItem(collapsedKey, collapsed ? "true" : "false");
}

function restoreDesktopState() {
    if (mobileQuery.matches) {
        document.body.classList.remove("is-sidebar-collapsed");
        return;
    }

    const collapsed = window.localStorage.getItem(collapsedKey) === "true";
    document.body.classList.toggle("is-sidebar-collapsed", collapsed);
}

export function initNavigation() {
    const toggleButtons = document.querySelectorAll("[data-toggle-sidebar]");
    if (!toggleButtons.length) {
        return;
    }

    restoreDesktopState();
    applyOverlayState();

    toggleButtons.forEach((button) => {
        button.addEventListener("click", toggleSidebar);
    });

    document.querySelectorAll("[data-close-sidebar]").forEach((button) => {
        button.addEventListener("click", closeMobileSidebar);
    });

    document.querySelectorAll(".sidebar a").forEach((link) => {
        link.addEventListener("click", () => {
            if (mobileQuery.matches) {
                closeMobileSidebar();
            }
        });
    });

    const overlay = document.querySelector("[data-sidebar-overlay]");
    if (overlay) {
        overlay.addEventListener("click", closeMobileSidebar);
    }

    mobileQuery.addEventListener("change", () => {
        if (!mobileQuery.matches) {
            document.body.classList.remove("is-sidebar-open");
        }
        restoreDesktopState();
        applyOverlayState();
    });
}
