import { t } from "./i18n.js";

function buildCitationCover(item, className) {
    const cover = document.createElement("span");
    cover.className = className;

    if (item.cover) {
        const image = document.createElement("img");
        image.src = item.cover;
        image.alt = item.title || item.label || t("composer.citation_default", {}, "Citation");
        image.loading = "lazy";
        cover.append(image);
        return cover;
    }

    const fallback = document.createElement("span");
    fallback.textContent = (
        item.label || t("composer.citation_default", {}, "Citation")
    ).slice(0, 2);
    cover.append(fallback);
    return cover;
}

function resolveCitationDetail(item) {
    const prefersExcerpt = ["book_annotation", "track_comment", "video_comment"].includes(item.kind);
    if (prefersExcerpt) {
        return item.excerpt || item.subtitle || "";
    }
    return item.subtitle || item.excerpt || "";
}

function buildCitationCopy(item) {
    const copy = document.createElement("div");
    copy.className = "composer-citation-card__copy";

    const title = document.createElement("strong");
    title.className = "composer-citation-card__title";
    title.textContent = item.title || t("composer.untitled", {}, "Untitled");
    copy.append(title);

    const metaRow = document.createElement("div");
    metaRow.className = "composer-citation-card__meta-line";

    const label = document.createElement("span");
    label.className = "composer-citation-card__label";
    label.textContent = item.label || t("composer.citation_default", {}, "Citation");
    metaRow.append(label);

    const detailText = resolveCitationDetail(item);
    if (detailText) {
        const detail = document.createElement("span");
        detail.className = "composer-citation-card__detail";
        detail.textContent = detailText;
        metaRow.append(detail);
    }

    copy.append(metaRow);
    return copy;
}

function buildCitationBody(item) {
    const body = document.createElement("div");
    body.className = "composer-citation-card__body";
    body.append(buildCitationCover(item, "composer-citation-card__cover"));
    body.append(buildCitationCopy(item));
    return body;
}

export function createComposerCitationController({
    signal,
    citationToggle,
    citationPanel,
    citationSearch,
    citationResults,
    citationFooter,
    citationLoadMore,
    selectedCitationShell,
    citationKindField,
    citationTargetIdField,
    citationScopeButtons,
    onSelectionChange,
}) {
    let selectedCitation = null;
    let citationScope = "all";
    let citationSearchTimer = null;
    let citationRequestToken = 0;
    let citationOffset = 0;
    let citationHasMore = false;
    const citationPageSize = 8;

    const hasToggleButton = citationToggle instanceof HTMLButtonElement;

    function syncCitationFooter(isLoadingMore = false) {
        if (!(citationFooter instanceof HTMLElement) || !(citationLoadMore instanceof HTMLButtonElement)) {
            return;
        }

        citationFooter.hidden = !citationHasMore && !isLoadingMore;
        citationLoadMore.disabled = isLoadingMore;
        citationLoadMore.textContent = isLoadingMore
            ? t("composer.loading", {}, "Loading...")
            : t("composer.load_more", {}, "Load more");
    }

    function syncCitationFields() {
        if (
            !(citationKindField instanceof HTMLInputElement) ||
            !(citationTargetIdField instanceof HTMLInputElement)
        ) {
            return;
        }

        citationKindField.value = selectedCitation?.kind || "";
        citationTargetIdField.value = selectedCitation?.id ? String(selectedCitation.id) : "";
    }

    function renderSelectedCitation() {
        if (!(selectedCitationShell instanceof HTMLElement)) {
            return;
        }

        selectedCitationShell.replaceChildren();
        syncCitationFields();

        if (!selectedCitation) {
            selectedCitationShell.hidden = true;
            return;
        }

        selectedCitationShell.hidden = false;

        const article = document.createElement("article");
        article.className = "composer-citation-card composer-citation-card--selected";
        article.title = [
            selectedCitation.title,
            resolveCitationDetail(selectedCitation),
        ].filter(Boolean).join(" · ");
        article.append(buildCitationBody(selectedCitation));

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "composer-citation-card__remove";
        remove.textContent = "\u00d7";
        remove.setAttribute("aria-label", t("composer.remove", {}, "Remove"));
        remove.title = t("composer.remove", {}, "Remove");
        remove.addEventListener("click", () => {
            selectedCitation = null;
            renderSelectedCitation();
            onSelectionChange();
        }, { signal });
        article.append(remove);

        selectedCitationShell.append(article);
    }

    function renderCitationResults(items, query = "", { append = false } = {}) {
        if (!(citationResults instanceof HTMLElement)) {
            return;
        }

        if (!append) {
            citationResults.replaceChildren();
        }

        if (!items.length) {
            if (append) {
                return;
            }
            const empty = document.createElement("div");
            empty.className = "empty-state empty-state--compact";
            const message = document.createElement("p");
            message.textContent = query
                ? t("composer.no_results", {}, "Nothing matched that search yet.")
                : t("composer.search_prompt", {}, "Search once, then pick one item to cite.");
            empty.append(message);
            citationResults.append(empty);
            return;
        }

        items.forEach((item) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "composer-citation-card";
            button.title = [
                item.title,
                resolveCitationDetail(item),
            ].filter(Boolean).join(" · ");
            button.append(buildCitationBody(item));

            button.addEventListener("click", () => {
                selectedCitation = item;
                renderSelectedCitation();
                onSelectionChange();
                if (hasToggleButton && citationPanel instanceof HTMLElement) {
                    citationPanel.hidden = true;
                }
                if (hasToggleButton && citationToggle instanceof HTMLButtonElement) {
                    citationToggle.setAttribute("aria-expanded", "false");
                }
            }, { signal });

            citationResults.append(button);
        });
    }

    async function loadCitationResults({ append = false } = {}) {
        if (!(citationResults instanceof HTMLElement)) {
            return;
        }

        citationRequestToken += 1;
        const token = citationRequestToken;
        const query = citationSearch instanceof HTMLInputElement ? citationSearch.value.trim() : "";
        const offset = append ? citationOffset : 0;

        if (!append) {
            citationOffset = 0;
            citationHasMore = false;
            citationResults.replaceChildren();
            syncCitationFooter(false);

            const loading = document.createElement("div");
            loading.className = "empty-state empty-state--compact";
            loading.innerHTML = `<p>${t("composer.loading", {}, "Loading...")}</p>`;
            citationResults.append(loading);
        } else {
            syncCitationFooter(true);
        }

        try {
            const params = new URLSearchParams({
                q: query,
                scope: citationScope,
                offset: String(offset),
                limit: String(citationPageSize),
            });
            const response = await fetch(`/api/citations/search?${params.toString()}`);
            if (!response.ok) {
                throw new Error("Citation search failed");
            }
            const payload = await response.json();
            if (token !== citationRequestToken) {
                return;
            }
            const items = Array.isArray(payload.items) ? payload.items : [];
            citationOffset = offset + items.length;
            citationHasMore = Boolean(payload.has_more);
            renderCitationResults(items, query, { append });
            syncCitationFooter(false);
        } catch {
            if (token !== citationRequestToken) {
                return;
            }
            citationHasMore = false;
            syncCitationFooter(false);
            if (!append) {
                citationResults.replaceChildren();
                const empty = document.createElement("div");
                empty.className = "empty-state empty-state--compact";
                empty.innerHTML = `<p>${t(
                    "composer.load_error",
                    {},
                    "Library citations could not be loaded right now.",
                )}</p>`;
                citationResults.append(empty);
            }
        }
    }

    function setCitationPanelOpen(isOpen) {
        if (!(citationPanel instanceof HTMLElement) || !(citationToggle instanceof HTMLButtonElement)) {
            return;
        }

        citationPanel.hidden = !isOpen;
        citationToggle.setAttribute("aria-expanded", String(isOpen));
        citationToggle.textContent = isOpen
            ? t("composer.hide_citation", {}, "Hide Citation")
            : t("composer.add_citation", {}, "Add Citation");

        if (isOpen) {
            void loadCitationResults();
            if (citationSearch instanceof HTMLInputElement) {
                citationSearch.focus();
            }
        }
    }

    citationToggle?.addEventListener("click", () => {
        setCitationPanelOpen(citationPanel?.hidden === true);
    }, { signal });

    citationScopeButtons.forEach((button) => {
        button.addEventListener("click", () => {
            citationScope = button.dataset.citationScope || "all";
            citationScopeButtons.forEach((entry) =>
                entry.classList.toggle("is-active", entry === button),
            );
            void loadCitationResults();
        }, { signal });
    });

    citationSearch?.addEventListener("input", () => {
        if (citationSearchTimer) {
            window.clearTimeout(citationSearchTimer);
        }
        citationSearchTimer = window.setTimeout(() => {
            void loadCitationResults();
        }, 180);
    }, { signal });

    citationLoadMore?.addEventListener("click", () => {
        if (citationHasMore) {
            void loadCitationResults({ append: true });
        }
    }, { signal });

    signal.addEventListener("abort", () => {
        if (citationSearchTimer) {
            window.clearTimeout(citationSearchTimer);
        }
    }, { once: true });

    if (!hasToggleButton && citationPanel instanceof HTMLElement) {
        citationPanel.hidden = false;
    }
    void loadCitationResults();

    return {
        getSelectedCitation: () => selectedCitation,
        renderSelectedCitation,
        syncCitationFields,
        loadCitationResults,
    };
}
