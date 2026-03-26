const mobileQuery = window.matchMedia("(max-width: 1080px)");
const collapsedKey = "moments-sidebar-collapsed";

function closeLanguageSwitches(except = null) {
    document.querySelectorAll("[data-language-switch]").forEach((switcher) => {
        if (switcher === except) {
            return;
        }
        switcher.removeAttribute("open");
    });
}

function syncFolderPanelState(activeName = null) {
    document.querySelectorAll("[data-open-folder-panel]").forEach((button) => {
        const expanded = button.dataset.openFolderPanel === activeName;
        button.setAttribute("aria-expanded", expanded ? "true" : "false");
    });
}

function closeFolderPanels() {
    document.body.classList.remove("has-folder-panel-open");
    const backdrop = document.querySelector("[data-folder-panel-backdrop]");
    if (backdrop) {
        backdrop.hidden = true;
    }

    document.querySelectorAll("[data-folder-panel]").forEach((panel) => {
        panel.hidden = true;
    });

    syncFolderPanelState();
}

function openFolderPanel(name) {
    const target = document.querySelector(`[data-folder-panel="${name}"]`);
    if (!target) {
        return;
    }

    if (mobileQuery.matches) {
        closeMobileSidebar();
    }

    document.body.classList.add("has-folder-panel-open");
    const backdrop = document.querySelector("[data-folder-panel-backdrop]");
    if (backdrop) {
        backdrop.hidden = false;
    }

    document.querySelectorAll("[data-folder-panel]").forEach((panel) => {
        panel.hidden = panel !== target;
    });

    syncFolderPanelState(name);

    const autofocusTarget = target.querySelector(
        "input:not([type='hidden']):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])",
    );
    if (autofocusTarget) {
        autofocusTarget.focus();
    }
}

function syncFolderParentField() {
    const parentField = document.querySelector("[data-folder-parent-field]");
    const parentSelect = document.querySelector("[data-folder-parent-select]");
    const selectedMode = document.querySelector("[data-folder-parent-mode]:checked")?.value;
    const shouldShowParent = selectedMode === "child";

    if (parentField) {
        parentField.hidden = !shouldShowParent;
    }

    if (parentSelect) {
        parentSelect.disabled = !shouldShowParent;
        if (!shouldShowParent) {
            parentSelect.value = "";
        }
    }
}

function getFolderBranchChildren(branch) {
    return (
        Array.from(branch.children).find((child) => child.matches("[data-folder-branch-children]")) ?? null
    );
}

function getFolderBranchToggle(branch) {
    const row = Array.from(branch.children).find((child) => child.classList.contains("folder-map__row"));
    return row ? row.querySelector("[data-folder-branch-toggle]") : null;
}

function setFolderBranchExpanded(branch, expanded) {
    const children = getFolderBranchChildren(branch);
    const toggle = getFolderBranchToggle(branch);

    if (!children || !toggle) {
        return;
    }

    branch.dataset.folderBranchState = expanded ? "expanded" : "collapsed";
    children.hidden = !expanded;
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");

    const label = expanded ? toggle.dataset.folderCollapseLabel : toggle.dataset.folderExpandLabel;
    if (label) {
        toggle.setAttribute("aria-label", label);
    }
}

function expandFolderBranchPath(activeLink) {
    let currentBranch = activeLink.closest("[data-folder-branch]");

    while (currentBranch) {
        setFolderBranchExpanded(currentBranch, true);
        currentBranch = currentBranch.parentElement?.closest("[data-folder-branch]") ?? null;
    }
}

function initFolderTree() {
    const branches = document.querySelectorAll("[data-folder-branch]");
    if (!branches.length) {
        return;
    }

    branches.forEach((branch) => {
        const toggle = getFolderBranchToggle(branch);
        const children = getFolderBranchChildren(branch);

        if (!toggle || !children) {
            return;
        }

        const initiallyExpanded = branch.dataset.folderBranchInitiallyExpanded === "true";
        setFolderBranchExpanded(branch, initiallyExpanded);

        toggle.addEventListener("click", () => {
            const expanded = toggle.getAttribute("aria-expanded") === "true";
            setFolderBranchExpanded(branch, !expanded);
        });
    });

    document.querySelectorAll(".folder-map__node.is-active").forEach((link) => {
        expandFolderBranchPath(link);
    });
}

function syncToggleState() {
    const isOpen = document.body.classList.contains("is-sidebar-open");
    document.querySelectorAll("[data-toggle-sidebar]").forEach((button) => {
        button.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });
}

function closeMobileSidebar() {
    document.body.classList.remove("is-sidebar-open");
    syncToggleState();
}

function openMobileSidebar() {
    document.body.classList.add("is-sidebar-open");
    syncToggleState();
}

function toggleSidebar() {
    if (mobileQuery.matches) {
        if (document.body.classList.contains("is-sidebar-open")) {
            closeMobileSidebar();
        } else {
            openMobileSidebar();
        }
        return;
    }

    document.body.classList.toggle("is-sidebar-collapsed");
    const collapsed = document.body.classList.contains("is-sidebar-collapsed");
    window.localStorage.setItem(collapsedKey, collapsed ? "true" : "false");
}

function goBack(button) {
    const fallbackHref = button?.dataset.backHref || "/";
    const sameOriginReferrer =
        document.referrer && document.referrer.startsWith(window.location.origin);

    if (sameOriginReferrer && window.history.length > 1) {
        window.history.back();
        return;
    }

    window.location.href = fallbackHref;
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
    syncToggleState();

    toggleButtons.forEach((button) => {
        button.addEventListener("click", toggleSidebar);
    });

    document.querySelectorAll("[data-close-sidebar]").forEach((button) => {
        button.addEventListener("click", closeMobileSidebar);
    });

    document.querySelectorAll("[data-history-back]").forEach((button) => {
        button.addEventListener("click", () => {
            goBack(button);
        });
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

    document.querySelectorAll("[data-open-folder-panel]").forEach((button) => {
        button.addEventListener("click", () => {
            openFolderPanel(button.dataset.openFolderPanel);
        });
    });

    document.querySelectorAll("[data-close-folder-panel]").forEach((button) => {
        button.addEventListener("click", closeFolderPanels);
    });

    const folderBackdrop = document.querySelector("[data-folder-panel-backdrop]");
    if (folderBackdrop) {
        folderBackdrop.addEventListener("click", closeFolderPanels);
    }

    document.querySelectorAll("[data-folder-jump]").forEach((link) => {
        link.addEventListener("click", closeFolderPanels);
    });

    document.querySelectorAll("[data-folder-parent-mode]").forEach((input) => {
        input.addEventListener("change", syncFolderParentField);
    });
    syncFolderParentField();
    syncFolderPanelState();
    initFolderTree();

    document.querySelectorAll("[data-language-switch]").forEach((switcher) => {
        const trigger = switcher.querySelector(".language-switch__trigger");
        if (!trigger) {
            return;
        }

        trigger.addEventListener("click", () => {
            if (!switcher.hasAttribute("open")) {
                closeLanguageSwitches(switcher);
            }
        });
    });

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element) || event.target.closest("[data-language-switch]")) {
            return;
        }
        closeLanguageSwitches();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") {
            return;
        }

        const hasOpenLanguageSwitch = Array.from(document.querySelectorAll("[data-language-switch]")).some((switcher) =>
            switcher.hasAttribute("open"),
        );
        if (hasOpenLanguageSwitch) {
            closeLanguageSwitches();
            return;
        }

        if (document.body.classList.contains("has-folder-panel-open")) {
            closeFolderPanels();
            return;
        }

        if (document.body.classList.contains("is-sidebar-open")) {
            closeMobileSidebar();
        }
    });

    mobileQuery.addEventListener("change", () => {
        if (!mobileQuery.matches) {
            document.body.classList.remove("is-sidebar-open");
        }
        restoreDesktopState();
        syncToggleState();
        syncFolderPanelState();
    });
}
