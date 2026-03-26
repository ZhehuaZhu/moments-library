import { refreshCsrfToken } from "./http.js";
import { refreshTranslations } from "./i18n.js";

let pjaxInitialized = false;
let navigationToken = 0;

function isModifiedEvent(event) {
    return event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
}

function isNavigableLink(link) {
    if (!(link instanceof HTMLAnchorElement)) {
        return false;
    }

    if (
        link.target === "_blank" ||
        link.hasAttribute("download") ||
        link.getAttribute("rel") === "external" ||
        link.dataset.noPjax === "true"
    ) {
        return false;
    }

    const href = link.href;
    if (!href) {
        return false;
    }

    const url = new URL(href, window.location.href);
    if (url.origin !== window.location.origin) {
        return false;
    }

    if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) {
        return false;
    }

    return true;
}

function isNavigableForm(form) {
    if (!(form instanceof HTMLFormElement) || form.dataset.noPjax === "true") {
        return false;
    }

    const method = (form.getAttribute("method") || "get").toLowerCase();
    if (method !== "get") {
        return false;
    }

    if (form.enctype === "multipart/form-data") {
        return false;
    }

    const action = new URL(form.action || window.location.href, window.location.href);
    return action.origin === window.location.origin;
}

function serializeForm(form) {
    const url = new URL(form.action || window.location.href, window.location.href);
    const formData = new FormData(form);
    const params = new URLSearchParams();

    formData.forEach((value, key) => {
        if (typeof value === "string") {
            params.append(key, value);
        }
    });

    url.search = params.toString();
    return url;
}

function closeTransientUi() {
    document.body.classList.remove("is-sidebar-open", "has-folder-panel-open", "is-modal-open");
    const backdrop = document.querySelector("[data-folder-panel-backdrop]");
    if (backdrop instanceof HTMLElement) {
        backdrop.hidden = true;
    }

    document.querySelectorAll("[data-folder-panel]").forEach((panel) => {
        if (panel instanceof HTMLElement) {
            panel.hidden = true;
        }
    });

    document.querySelectorAll("[data-modal]").forEach((modal) => {
        if (modal instanceof HTMLElement) {
            modal.hidden = true;
        }
    });
}

function syncHeadStyles(nextDocument) {
    const currentHead = document.head;
    const nextStylesheets = Array.from(
        nextDocument.querySelectorAll('head link[rel="stylesheet"][href]')
    );
    const currentStylesheets = new Map(
        Array.from(currentHead.querySelectorAll('link[rel="stylesheet"][href]')).map((link) => [
            link.getAttribute("href"),
            link,
        ])
    );

    nextStylesheets.forEach((link) => {
        const href = link.getAttribute("href");
        if (!href || currentStylesheets.has(href)) {
            return;
        }
        currentHead.append(link.cloneNode(true));
    });
}

function updateHeadAndBody(nextDocument) {
    document.title = nextDocument.title || document.title;
    if (nextDocument.documentElement.lang) {
        document.documentElement.lang = nextDocument.documentElement.lang;
    }

    syncHeadStyles(nextDocument);

    const currentCsrf = document.querySelector('meta[name="csrf-token"]');
    const nextCsrf = nextDocument.querySelector('meta[name="csrf-token"]');
    if (currentCsrf instanceof HTMLMetaElement && nextCsrf instanceof HTMLMetaElement) {
        currentCsrf.content = nextCsrf.content;
    }
    refreshCsrfToken();

    const currentTranslations = document.querySelector("[data-ui-translations]");
    const nextTranslations = nextDocument.querySelector("[data-ui-translations]");
    if (currentTranslations instanceof HTMLScriptElement && nextTranslations instanceof HTMLScriptElement) {
        currentTranslations.textContent = nextTranslations.textContent;
    }
    refreshTranslations();

    const nextBodyClass = nextDocument.body?.className || "app-body";
    const keepReady = document.body.classList.contains("is-ready");
    document.body.className = nextBodyClass;
    if (keepReady) {
        document.body.classList.add("is-ready");
    }
}

function swapAppShell(nextDocument) {
    const currentShell = document.querySelector("[data-app-shell]");
    const nextShell = nextDocument.querySelector("[data-app-shell]");
    if (!(currentShell instanceof HTMLElement) || !(nextShell instanceof HTMLElement)) {
        return false;
    }

    currentShell.replaceWith(nextShell);
    return true;
}

function restoreScroll(url, { preserveScroll = false } = {}) {
    if (preserveScroll) {
        return;
    }

    if (url.hash) {
        const target = document.getElementById(url.hash.slice(1));
        if (target instanceof HTMLElement) {
            target.scrollIntoView();
            return;
        }
    }

    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
}

async function fetchDocument(url) {
    const response = await fetch(url, {
        credentials: "same-origin",
        headers: {
            "X-Requested-With": "fetch",
        },
    });

    if (!response.ok) {
        throw new Error(`Navigation failed with status ${response.status}`);
    }

    const text = await response.text();
    return new DOMParser().parseFromString(text, "text/html");
}

export function initPjax({ bootstrapPage }) {
    if (pjaxInitialized) {
        return;
    }
    pjaxInitialized = true;

    const navigate = async (targetUrl, { replace = false, preserveScroll = false } = {}) => {
        const url = targetUrl instanceof URL ? targetUrl : new URL(targetUrl, window.location.href);
        const nextToken = navigationToken + 1;
        navigationToken = nextToken;

        closeTransientUi();
        document.dispatchEvent(new CustomEvent("app:before-swap"));

        try {
            const nextDocument = await fetchDocument(url);
            if (navigationToken !== nextToken) {
                return;
            }

            if (!swapAppShell(nextDocument)) {
                window.location.href = url.toString();
                return;
            }

            updateHeadAndBody(nextDocument);

            if (replace) {
                window.history.replaceState({ pjax: true, href: url.toString() }, "", url);
            } else {
                window.history.pushState({ pjax: true, href: url.toString() }, "", url);
            }

            await bootstrapPage();
            document.dispatchEvent(new CustomEvent("app:after-swap"));
            restoreScroll(url, { preserveScroll });
        } catch {
            window.location.href = url.toString();
        }
    };

    window.history.replaceState({ pjax: true, href: window.location.href }, "", window.location.href);

    document.addEventListener("click", (event) => {
        if (
            event.defaultPrevented ||
            !(event.target instanceof Element) ||
            (event instanceof MouseEvent && event.button !== 0) ||
            isModifiedEvent(event) ||
            !document.querySelector("[data-audio-player]")
        ) {
            return;
        }

        const link = event.target.closest("a[href]");
        if (!isNavigableLink(link) || !(link instanceof HTMLAnchorElement)) {
            return;
        }

        event.preventDefault();
        void navigate(link.href);
    });

    document.addEventListener("submit", (event) => {
        if (
            !(event.target instanceof HTMLFormElement) ||
            !isNavigableForm(event.target) ||
            !document.querySelector("[data-audio-player]")
        ) {
            return;
        }

        event.preventDefault();
        void navigate(serializeForm(event.target));
    });

    window.addEventListener("popstate", () => {
        if (!document.querySelector("[data-audio-player]")) {
            window.location.reload();
            return;
        }
        void navigate(window.location.href, { replace: true, preserveScroll: true });
    });
}
