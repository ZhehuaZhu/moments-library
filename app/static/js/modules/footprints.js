import { t } from "./i18n.js";
import { ensureLeaflet } from "./vendor-loader.js";

function escapeHtml(value = "") {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function normalizeLookupValue(value = "") {
    return String(value)
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/['".,()/\-]+/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .toLowerCase();
}

function normalizeCountryCode(value = "") {
    const code = String(value || "").trim().toUpperCase();
    if (!code || code === "-99") {
        return "";
    }
    return code;
}

function getCountryFeatureLabel(feature) {
    const properties = feature?.properties || {};
    const isChinese = (document.documentElement.lang || "").toLowerCase().startsWith("zh");

    if (isChinese) {
        return properties.NAME_ZH || properties.NAME_EN || properties.NAME || properties.ADMIN || "";
    }

    return properties.NAME_EN || properties.NAME || properties.ADMIN || properties.NAME_LONG || "";
}

function getCountryFeatureKeys(feature) {
    const properties = feature?.properties || {};
    const codes = [
        normalizeCountryCode(properties.ISO_A2),
        normalizeCountryCode(properties.ISO_A2_EH),
        normalizeCountryCode(properties.WB_A2),
        normalizeCountryCode(properties.POSTAL),
    ].filter(Boolean);

    const names = [
        properties.NAME_EN,
        properties.NAME,
        properties.ADMIN,
        properties.NAME_LONG,
        properties.NAME_ZH,
    ]
        .map((value) => normalizeLookupValue(value))
        .filter(Boolean);

    return { codes, names };
}

function buildCountryLookup(places) {
    const byCode = new Map();
    const byName = new Map();

    places.forEach((place) => {
        const code = normalizeCountryCode(place.country_code);
        if (code && !byCode.has(code)) {
            byCode.set(code, place);
        }

        [place.country_name, place.name].forEach((value) => {
            const key = normalizeLookupValue(value);
            if (key && !byName.has(key)) {
                byName.set(key, place);
            }
        });
    });

    return { byCode, byName };
}

function findCountryPlaceByFeature(feature, lookup) {
    const keys = getCountryFeatureKeys(feature);

    for (const code of keys.codes) {
        const match = lookup.byCode.get(code);
        if (match) {
            return match;
        }
    }

    for (const name of keys.names) {
        const match = lookup.byName.get(name);
        if (match) {
            return match;
        }
    }

    return null;
}

function buildCountryTooltip(feature, place) {
    const label = getCountryFeatureLabel(feature) || t("footprints.unknown_place", {}, "Pinned Place");
    if (!place) {
        return label;
    }
    return `${label} | ${place.moment_count}`;
}

function buildCountryStyle({ visited, selected, contrastEnabled }) {
    if (!contrastEnabled) {
        return {
            color: "rgba(0, 0, 0, 0)",
            weight: 0.1,
            fillColor: "#dfe5e8",
            fillOpacity: 0,
        };
    }

    if (!visited) {
        return {
            color: "rgba(120, 133, 144, 0.42)",
            weight: 1,
            fillColor: "#d7dde2",
            fillOpacity: 0.52,
        };
    }

    if (selected) {
        return {
            color: "rgba(28, 56, 52, 0.94)",
            weight: 2.2,
            fillColor: "#5b897c",
            fillOpacity: 0.56,
        };
    }

    return {
        color: "rgba(63, 111, 100, 0.52)",
        weight: 1.3,
        fillColor: "#8fb6aa",
        fillOpacity: 0.38,
    };
}

function buildMarkerIcon(L, place, selected = false) {
    const momentCount = Math.max(1, Number(place.moment_count || 0));
    const countDigits = String(momentCount).length;
    const hasCount = momentCount > 1;
    const markerSize = hasCount
        ? Math.min(42, (selected ? 32 : 28) + countDigits * 4)
        : (selected ? 24 : 18);
    const markerClass = [
        "atlas-marker",
        selected ? "is-selected" : "",
        hasCount ? "has-count" : "",
    ].filter(Boolean).join(" ");
    const countMarkup = hasCount ? `<strong class="atlas-marker__count">${momentCount}</strong>` : "";

    return L.divIcon({
        className: "atlas-marker-wrap",
        html: `
            <span class="${markerClass}" style="--atlas-marker-size:${markerSize}px">
                <span class="atlas-marker__pulse"></span>
                <span class="atlas-marker__dot"></span>
                ${countMarkup}
            </span>
        `,
        iconSize: [markerSize, markerSize],
        iconAnchor: [markerSize / 2, markerSize / 2],
    });
}

function renderMomentMedia(moment, className) {
    if (!moment.media?.src) {
        return "";
    }

    if (moment.media.kind === "video") {
        return `
            <div class="${className}">
                <video muted loop playsinline preload="metadata">
                    <source src="${escapeHtml(moment.media.src)}">
                </video>
            </div>
        `;
    }

    return `
        <div class="${className}">
            <img src="${escapeHtml(moment.media.src)}" alt="${escapeHtml(moment.media.alt || "")}" loading="lazy">
        </div>
    `;
}

function truncateText(value = "", maxLength = 96) {
    const normalized = String(value || "").replace(/\s+/g, " ").trim();
    if (normalized.length <= maxLength) {
        return normalized;
    }
    return `${normalized.slice(0, maxLength - 3).trimEnd()}...`;
}

function renderMomentPeek(moment) {
    const excerpt = truncateText(moment.excerpt || "", 120);
    const excerptMarkup = excerpt ? `<p class="atlas-peek__excerpt">${escapeHtml(excerpt)}</p>` : "";
    const locationMarkup = moment.location_label
        ? `<span class="atlas-peek__location">${escapeHtml(moment.location_label)}</span>`
        : "";

    return `
        <article class="atlas-peek">
            <div class="atlas-peek__meta">
                <span>${escapeHtml(moment.created_at || "")}</span>
                ${locationMarkup}
            </div>
            ${excerptMarkup}
            <div class="atlas-peek__actions">
                <a class="button button--subtle button--compact" href="${escapeHtml(moment.href || "#")}">
                    ${escapeHtml(t("footprints.view_feed", {}, "View In Feed"))}
                </a>
            </div>
        </article>
    `;
}

function renderMomentCard(moment) {
    const excerpt = moment.excerpt ? `<p class="atlas-moment-card__excerpt">${escapeHtml(moment.excerpt)}</p>` : "";
    const location = moment.location_label
        ? `<span class="atlas-moment-card__location">${escapeHtml(moment.location_label)}</span>`
        : "";

    return `
        <article class="atlas-moment-card">
            ${renderMomentMedia(moment, "atlas-moment-card__media")}
            <div class="atlas-moment-card__body">
                <div class="atlas-moment-card__meta">
                    <span>${escapeHtml(moment.created_at || "")}</span>
                    ${location}
                </div>
                ${excerpt}
                <div class="atlas-moment-card__actions">
                    <a class="button button--subtle button--compact" href="${escapeHtml(moment.href || "#")}">
                        ${escapeHtml(t("footprints.view_feed", {}, "View In Feed"))}
                    </a>
                </div>
            </div>
        </article>
    `;
}

function renderTimelineItem(moment) {
    const excerpt = moment.excerpt ? `<p class="atlas-timeline__excerpt">${escapeHtml(moment.excerpt)}</p>` : "";
    const location = moment.location_label
        ? `<span class="atlas-timeline__location">${escapeHtml(moment.location_label)}</span>`
        : "";

    return `
        <article class="atlas-timeline__item">
            <span class="atlas-timeline__dot" aria-hidden="true"></span>
            <div class="atlas-timeline__card">
                <div class="atlas-timeline__content">
                    <span class="atlas-timeline__stamp">${escapeHtml(moment.created_at || "")}</span>
                    ${renderMomentMedia(moment, "atlas-timeline__media")}
                    <div class="atlas-timeline__meta">
                        ${location}
                    </div>
                    ${excerpt}
                    <div class="atlas-timeline__actions">
                        <a class="button button--subtle button--compact" href="${escapeHtml(moment.href || "#")}">
                            ${escapeHtml(t("footprints.view_feed", {}, "View In Feed"))}
                        </a>
                    </div>
                </div>
            </div>
        </article>
    `;
}

function renderPopup(place) {
    const previewItems = place.moments.slice(0, 3).map((moment) => `
        <div class="atlas-popup__item">
            <span class="atlas-popup__time">${escapeHtml(moment.created_at || "")}</span>
            <div class="atlas-popup__excerpt">${escapeHtml(moment.excerpt || "")}</div>
            <a class="button button--subtle button--compact" href="${escapeHtml(moment.href || "#")}">
                ${escapeHtml(t("footprints.view_feed", {}, "View In Feed"))}
            </a>
        </div>
    `).join("");

    return `
        <div class="atlas-popup">
            <div class="atlas-popup__header">
                <strong>${escapeHtml(place.name || t("footprints.unknown_place", {}, "Pinned Place"))}</strong>
                <span class="atlas-popup__meta">${escapeHtml(place.subtitle || "")}</span>
            </div>
            <div class="atlas-popup__list">${previewItems}</div>
        </div>
    `;
}

function renderEmptyState(message) {
    return `
        <div class="atlas-empty">
            <strong>${escapeHtml(message)}</strong>
        </div>
    `;
}

function sortPlaces(places, sortKey) {
    const sorted = [...places];

    if (sortKey === "count") {
        sorted.sort((left, right) => {
            return (
                Number(right.moment_count || 0) - Number(left.moment_count || 0) ||
                String(right.latest_created_at_sort || "").localeCompare(String(left.latest_created_at_sort || "")) ||
                String(left.name || "").localeCompare(String(right.name || ""))
            );
        });
        return sorted;
    }

    if (sortKey === "name") {
        sorted.sort((left, right) => {
            return (
                String(left.name || "").localeCompare(String(right.name || ""), undefined, { sensitivity: "base" }) ||
                String(right.latest_created_at_sort || "").localeCompare(String(left.latest_created_at_sort || ""))
            );
        });
        return sorted;
    }

    sorted.sort((left, right) => {
        return (
            String(right.latest_created_at_sort || "").localeCompare(String(left.latest_created_at_sort || "")) ||
            Number(right.moment_count || 0) - Number(left.moment_count || 0) ||
            String(left.name || "").localeCompare(String(right.name || ""))
        );
    });
    return sorted;
}

function sortMoments(moments) {
    const sorted = [...moments];
    sorted.sort((left, right) => {
        return (
            String(right.created_at_sort || "").localeCompare(String(left.created_at_sort || "")) ||
            Number(right.id || 0) - Number(left.id || 0)
        );
    });
    return sorted;
}

function filterPlaces(places, filterKey) {
    if (filterKey === "multiple") {
        return places.filter((place) => Number(place.moment_count || 0) > 1);
    }

    if (filterKey === "media") {
        return places.filter((place) => Number(place.media_moment_count || 0) > 0);
    }

    return places;
}

function buildTooltip(place) {
    return `${place.name || t("footprints.unknown_place", {}, "Pinned Place")} | ${place.moment_count}`;
}

function getSelectedOptionLabel(select) {
    return select.options[select.selectedIndex]?.textContent?.trim() || "";
}

function localizeUiText(english, chinese) {
    const language = (document.documentElement.lang || "").toLowerCase();
    return language.startsWith("zh") ? chinese : english;
}

async function loadCountryGeoJson(url) {
    if (!url) {
        return null;
    }

    try {
        const response = await fetch(url, {
            headers: {
                Accept: "application/geo+json, application/json",
            },
        });
        if (!response.ok) {
            return null;
        }
        return await response.json();
    } catch {
        return null;
    }
}

export async function initFootprintsMap() {
    const shell = document.querySelector("[data-footprints-shell]");
    const mapElement = document.querySelector("[data-footprints-map]");
    const payloadScript = document.querySelector("[data-footprints-payload]");

    if (!shell || !mapElement || !payloadScript) {
        return;
    }

    let payload = {};
    try {
        payload = JSON.parse(payloadScript.textContent || "{}");
    } catch {
        payload = {};
    }

    const views = payload && typeof payload.views === "object" ? payload.views : {};
    const defaultView = payload.default_view || "city";
    if (!views.city?.places?.length && !views.country?.places?.length) {
        return;
    }

    let L;
    try {
        L = await ensureLeaflet();
    } catch {
        mapElement.innerHTML = `<div class="atlas-map__fallback">${escapeHtml(t("footprints.map_failed", {}, "Map could not load."))}</div>`;
        return;
    }

    const panel = document.querySelector("[data-footprints-panel]");
    const nameElement = document.querySelector("[data-footprints-place-name]");
    const subtitleElement = document.querySelector("[data-footprints-place-subtitle]");
    const panelHintElement = document.querySelector("[data-footprints-panel-hint]");
    const countElement = document.querySelector("[data-footprints-place-count]");
    const momentsElement = document.querySelector("[data-footprints-moments]");
    const totalPlacesElement = document.querySelector("[data-footprints-total-places]");
    const totalMomentsElement = document.querySelector("[data-footprints-total-moments]");
    const viewSelect = document.querySelector("[data-footprints-view]");
    const filterSelect = document.querySelector("[data-footprints-filter]");
    const visitSelect = document.querySelector("[data-footprints-visit-mode]");
    const sortSelect = document.querySelector("[data-footprints-sort]");
    const controlsShell = document.querySelector("[data-footprints-controls]");
    const controlsSummaryElement = document.querySelector("[data-footprints-controls-summary]");
    const menuToggle = document.querySelector("[data-footprints-menu-toggle]");
    const menuPanel = document.querySelector("[data-footprints-menu-panel]");

    if (
        !panel ||
        !nameElement ||
        !subtitleElement ||
        !panelHintElement ||
        !countElement ||
        !momentsElement ||
        !totalPlacesElement ||
        !totalMomentsElement ||
        !(viewSelect instanceof HTMLSelectElement) ||
        !(filterSelect instanceof HTMLSelectElement) ||
        !(visitSelect instanceof HTMLSelectElement) ||
        !(sortSelect instanceof HTMLSelectElement)
    ) {
        return;
    }

    const state = {
        view: defaultView,
        filter: "all",
        visitMode: "visited",
        sort: "latest",
    };

    viewSelect.value = state.view;
    filterSelect.value = state.filter;
    visitSelect.value = state.visitMode;
    sortSelect.value = state.sort;

    const map = L.map(mapElement, {
        zoomControl: false,
        attributionControl: false,
        worldCopyJump: true,
        scrollWheelZoom: false,
        doubleClickZoom: false,
        zoomSnap: 0.5,
        zoomDelta: 0.5,
    });

    if (map.scrollWheelZoom) {
        map.scrollWheelZoom.disable();
    }

    L.control.zoom({ position: "topright" }).addTo(map);
    const attribution = L.control.attribution({ position: "bottomright", prefix: false });
    attribution.addTo(map);
    attribution.addAttribution('&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>');

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
    }).addTo(map);

    const markerLayer = L.layerGroup().addTo(map);
    const markers = new Map();
    let selectedPlaceId = null;
    let isMenuOpen = false;

    const allCountryPlaces = Array.isArray(views.country?.places) ? views.country.places : [];
    const allCountryLookup = buildCountryLookup(allCountryPlaces);
    const countryData = await loadCountryGeoJson(shell.dataset.footprintsCountryDataUrl || "");
    let countryLayer = null;

    function getActivePlaces() {
        const rawPlaces = Array.isArray(views[state.view]?.places) ? views[state.view].places : [];
        return sortPlaces(filterPlaces(rawPlaces, state.filter), state.sort);
    }

    function getActiveCountryPlaces() {
        const rawPlaces = Array.isArray(views.country?.places) ? views.country.places : [];
        return sortPlaces(filterPlaces(rawPlaces, state.filter), state.sort);
    }

    function findSelectedPlace(places) {
        return places.find((place) => place.id === selectedPlaceId) || null;
    }

    function setControlsSummary() {
        if (!(controlsSummaryElement instanceof HTMLElement)) {
            return;
        }

        const labels = [
            getSelectedOptionLabel(viewSelect),
            getSelectedOptionLabel(filterSelect),
            getSelectedOptionLabel(sortSelect),
        ].filter(Boolean);

        if (state.view === "country") {
            labels.push(getSelectedOptionLabel(visitSelect));
        }

        const preview = labels.slice(0, 3);
        const extraCount = labels.length - preview.length;
        const summary = extraCount > 0 ? `${preview.join(" / ")} +${extraCount}` : preview.join(" / ");

        controlsSummaryElement.textContent = summary;
        controlsSummaryElement.title = labels.join(" / ");
    }

    function setMenuOpen(nextOpen) {
        isMenuOpen = Boolean(nextOpen);

        if (controlsShell instanceof HTMLElement) {
            controlsShell.classList.toggle("is-menu-open", isMenuOpen);
        }

        if (menuPanel instanceof HTMLElement) {
            menuPanel.hidden = !isMenuOpen;
        }

        if (menuToggle instanceof HTMLButtonElement) {
            menuToggle.setAttribute("aria-expanded", String(isMenuOpen));
        }
    }

    function setHeaderTotals(places) {
        const visibleMomentCount = places.reduce((sum, place) => sum + Number(place.moment_count || 0), 0);
        totalPlacesElement.textContent = t("footprints.visited_places", { count: places.length }, `${places.length}`);
        totalMomentsElement.textContent = t("footprints.mapped_moments", { count: visibleMomentCount }, `${visibleMomentCount}`);
    }

    function renderInspector(place, { hasVisiblePlaces = true } = {}) {
        if (!place) {
            panel.classList.add("is-empty");
            nameElement.textContent = hasVisiblePlaces
                ? t(
                    "footprints.panel_idle_title",
                    {},
                    localizeUiText("Select a footprint", "\u70b9\u51fb\u5730\u56fe\u4e0a\u7684\u8db3\u8ff9")
                )
                : t("footprints.no_visible_places", {}, "No places matched the current filter.");
            countElement.hidden = true;
            countElement.textContent = "";
            subtitleElement.hidden = true;
            panelHintElement.textContent = hasVisiblePlaces
                ? t(
                    "footprints.panel_idle_text",
                    {},
                    localizeUiText(
                        "Tap a marker on the map to open a quick place summary.",
                        "\u70b9\u5f00\u5730\u56fe\u4e0a\u7684\u6807\u8bb0\u540e\uff0c\u518d\u67e5\u770b\u8fd9\u4e2a\u5730\u70b9\u7684\u7b80\u8981\u5185\u5bb9\u3002"
                    )
                )
                : t("footprints.no_visible_places", {}, "No places matched the current filter.");
            momentsElement.innerHTML = "";
            return;
        }

        panel.classList.remove("is-empty");
        nameElement.textContent = place.name || t("footprints.unknown_place", {}, "Pinned Place");
        countElement.hidden = false;
        countElement.textContent = t("footprints.mapped_moments", { count: place.moment_count }, `${place.moment_count}`);
        subtitleElement.hidden = !place.subtitle;
        subtitleElement.textContent = place.subtitle || "";
        panelHintElement.textContent = t(
            "footprints.panel_recent_label",
            {},
            localizeUiText("Recent mapped moments", "\u6700\u8fd1\u5b9a\u4f4d\u52a8\u6001")
        );

        const orderedMoments = sortMoments(place.moments || []);
        if (!orderedMoments.length) {
            momentsElement.innerHTML = renderEmptyState(t("footprints.no_visible_places", {}, "No places matched the current filter."));
            return;
        }

        const previewLimit = 3;
        const previewMoments = orderedMoments.slice(0, previewLimit);
        const hiddenCount = Math.max(0, orderedMoments.length - previewMoments.length);
        const moreNote = hiddenCount > 0
            ? `<p class="atlas-inspector__note">${escapeHtml(
                t(
                    "footprints.panel_preview_more",
                    { count: previewMoments.length, total: orderedMoments.length },
                    localizeUiText(
                        `Showing latest ${previewMoments.length} of ${orderedMoments.length} mapped moments.`,
                        `\u8fd9\u91cc\u53ea\u663e\u793a\u6700\u8fd1 ${previewMoments.length} \u6761\uff0c\u5171 ${orderedMoments.length} \u6761\u5b9a\u4f4d\u52a8\u6001\u3002`
                    )
                )
            )}</p>`
            : "";

        momentsElement.innerHTML = `
            <div class="atlas-inspector__quicklist">
                ${previewMoments.map((moment) => renderMomentPeek(moment)).join("")}
            </div>
            ${moreNote}
        `;
    }

    function closeAllPopups() {
        markers.forEach((marker) => marker.closePopup());
    }

    function openPopupForPlace(place) {
        const marker = markers.get(place.id);
        if (!marker) {
            return;
        }
        marker.bindPopup(renderPopup(place), {
            className: "atlas-popup-shell",
            closeButton: false,
            maxWidth: 320,
            offset: [0, -12],
        });
        marker.openPopup();
    }

    function syncControls() {
        const countryOnly = state.view === "country";
        visitSelect.disabled = !countryOnly;
        visitSelect.closest(".atlas-control")?.classList.toggle("is-disabled", !countryOnly);
        setControlsSummary();
    }

    function ensureCountryLayer() {
        if (!countryData || countryLayer) {
            return;
        }

        countryLayer = L.geoJSON(countryData, {
            style: () => buildCountryStyle({ visited: false, selected: false, contrastEnabled: false }),
            onEachFeature(feature, layer) {
                const initialLabel = getCountryFeatureLabel(feature) || t("footprints.unknown_place", {}, "Pinned Place");
                layer.bindTooltip(initialLabel, {
                    sticky: true,
                    direction: "auto",
                    opacity: 0.98,
                });

                layer.on("click", () => {
                    if (state.view !== "country" || state.visitMode !== "contrast") {
                        return;
                    }

                    const activeLookup = buildCountryLookup(getActiveCountryPlaces());
                    const place = findCountryPlaceByFeature(feature, activeLookup);
                    if (!place) {
                        return;
                    }

                    selectedPlaceId = place.id;
                    syncSelection(getActivePlaces(), { pan: true });
                });
            },
        });
    }

    function syncCountryLayer(activeCountryPlaces) {
        ensureCountryLayer();
        if (!countryLayer) {
            return;
        }

        const contrastEnabled = state.view === "country" && state.visitMode === "contrast";
        if (!contrastEnabled) {
            if (map.hasLayer(countryLayer)) {
                map.removeLayer(countryLayer);
            }
            return;
        }

        if (!map.hasLayer(countryLayer)) {
            countryLayer.addTo(map);
        }

        const activeLookup = buildCountryLookup(activeCountryPlaces);
        countryLayer.eachLayer((layer) => {
            const feature = layer.feature;
            const visitedPlace = findCountryPlaceByFeature(feature, allCountryLookup);
            const activePlace = findCountryPlaceByFeature(feature, activeLookup);
            const isSelected = activePlace ? activePlace.id === selectedPlaceId : false;

            layer.setStyle(
                buildCountryStyle({
                    visited: Boolean(visitedPlace),
                    selected: isSelected,
                    contrastEnabled: true,
                })
            );

            if (typeof layer.setTooltipContent === "function") {
                layer.setTooltipContent(buildCountryTooltip(feature, visitedPlace));
            }
        });

        countryLayer.bringToBack();
    }

    function syncSelection(places, { pan = false } = {}) {
        const place = findSelectedPlace(places);
        if (!place) {
            selectedPlaceId = null;
            renderInspector(null, { hasVisiblePlaces: places.length > 0 });
            closeAllPopups();
            syncCountryLayer(getActiveCountryPlaces());
            return;
        }

        selectedPlaceId = place.id;
        markers.forEach((marker, markerId) => {
            const markerPlace = places.find((item) => item.id === markerId);
            if (!markerPlace) {
                return;
            }
            marker.setIcon(buildMarkerIcon(L, markerPlace, markerId === selectedPlaceId));
        });

        renderInspector(place);
        syncCountryLayer(getActiveCountryPlaces());

        if (pan) {
            map.panTo([place.latitude, place.longitude], { animate: true, duration: 0.45 });
        }
        closeAllPopups();
    }

    function renderMarkers(places, { fit = false } = {}) {
        markerLayer.clearLayers();
        markers.clear();

        const contrastEnabled = state.view === "country" && state.visitMode === "contrast";
        const bounds = [];

        places.forEach((place) => {
            const marker = L.marker([place.latitude, place.longitude], {
                icon: buildMarkerIcon(L, place, place.id === selectedPlaceId),
                keyboard: true,
                title: place.name || t("footprints.unknown_place", {}, "Pinned Place"),
            });

            marker.on("click", () => {
                selectedPlaceId = place.id;
                syncSelection(places, { pan: true });
            });
            marker.bindTooltip(buildTooltip(place), {
                direction: "top",
                offset: [0, -12],
            });

            marker.addTo(markerLayer);
            markers.set(place.id, marker);
            bounds.push([place.latitude, place.longitude]);
        });

        if (!fit) {
            return;
        }

        if (contrastEnabled) {
            map.setView([20, 8], 2);
            return;
        }

        if (!bounds.length) {
            return;
        }

        if (bounds.length === 1) {
            map.setView(bounds[0], 12);
            return;
        }

        map.fitBounds(bounds, {
            padding: [44, 44],
            maxZoom: state.view === "country" ? 4 : 10,
        });
    }

    function syncLayout() {
        shell.classList.remove("atlas-layout--popup");
        panel.hidden = false;
    }

    function refresh({ fit = false } = {}) {
        const places = getActivePlaces();
        setHeaderTotals(places);
        syncControls();
        syncLayout();
        syncCountryLayer(getActiveCountryPlaces());
        renderMarkers(places, { fit });
        syncSelection(places, { pan: false });
        requestAnimationFrame(() => map.invalidateSize());
    }

    if (menuToggle instanceof HTMLButtonElement) {
        menuToggle.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            setMenuOpen(!isMenuOpen);
        });
    }

    if (menuPanel instanceof HTMLElement) {
        menuPanel.addEventListener("click", (event) => {
            event.stopPropagation();
        });
    }

    document.addEventListener("click", (event) => {
        if (!isMenuOpen || !(controlsShell instanceof HTMLElement)) {
            return;
        }

        if (event.target instanceof Node && controlsShell.contains(event.target)) {
            return;
        }

        setMenuOpen(false);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && isMenuOpen) {
            setMenuOpen(false);
        }
    });

    viewSelect.addEventListener("change", () => {
        state.view = viewSelect.value;
        refresh({ fit: true });
    });

    filterSelect.addEventListener("change", () => {
        state.filter = filterSelect.value;
        refresh({ fit: true });
    });

    visitSelect.addEventListener("change", () => {
        state.visitMode = visitSelect.value;
        refresh({ fit: true });
    });

    sortSelect.addEventListener("change", () => {
        state.sort = sortSelect.value;
        refresh();
    });

    setMenuOpen(false);
    refresh({ fit: true });
    window.addEventListener("resize", () => map.invalidateSize());
}
