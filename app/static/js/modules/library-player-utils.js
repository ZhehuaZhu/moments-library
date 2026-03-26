import { t } from "./i18n.js";

export const playerStorageKey = "moments-global-player";
export const playerDockStateKey = "moments-global-player-dock-state";
export const playerDockPositionKey = "moments-global-player-dock-position";
export const playerAppearanceKey = "moments-global-player-appearance";
export const playerSizeKey = "moments-global-player-size";

export function readTrackCatalog() {
    const script = document.querySelector("[data-track-catalog]");
    if (!script) {
        return [];
    }

    try {
        const payload = JSON.parse(script.textContent || "[]");
        return Array.isArray(payload) ? payload : [];
    } catch {
        return [];
    }
}

export function readStoredJson(key) {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
        return null;
    }

    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

function normalizePlayerQueue(rawQueue, fallbackQueue = []) {
    const source = Array.isArray(rawQueue) && rawQueue.length ? rawQueue : fallbackQueue;
    return source.filter(
        (track) =>
            track &&
            typeof track === "object" &&
            typeof track.title === "string" &&
            typeof track.src === "string"
    );
}

export function normalizePlayerState(rawState, fallbackQueue = []) {
    const queue = normalizePlayerQueue(rawState?.queue, fallbackQueue);
    let currentIndex = Number.isInteger(rawState?.currentIndex) ? rawState.currentIndex : -1;
    if (currentIndex >= queue.length) {
        currentIndex = queue.length - 1;
    }
    if (currentIndex < -1) {
        currentIndex = -1;
    }

    const currentTime = Number(rawState?.currentTime);
    const duration = Number(rawState?.duration);

    return {
        queue,
        currentIndex,
        currentTime: Number.isFinite(currentTime) ? Math.max(currentTime, 0) : 0,
        duration: Number.isFinite(duration) ? Math.max(duration, 0) : 0,
        wasPlaying: Boolean(rawState?.wasPlaying),
    };
}

export function readStoredPlayerState(fallbackQueue = []) {
    return normalizePlayerState(readStoredJson(playerStorageKey), fallbackQueue);
}

export function writeStoredPlayerState(state, fallbackQueue = []) {
    const normalized = normalizePlayerState(state, fallbackQueue);
    window.localStorage.setItem(playerStorageKey, JSON.stringify(normalized));
    return normalized;
}

function normalizePlayerAppearance(rawAppearance) {
    const opacity = Number(rawAppearance?.opacity);
    return {
        opacity: Number.isFinite(opacity) ? Math.min(Math.max(opacity, 70), 100) : 92,
    };
}

export function readPlayerAppearance() {
    return normalizePlayerAppearance(readStoredJson(playerAppearanceKey));
}

export function writePlayerAppearance(appearance) {
    const normalized = normalizePlayerAppearance(appearance);
    window.localStorage.setItem(playerAppearanceKey, JSON.stringify(normalized));
    return normalized;
}

export function applyPlayerAppearance(shell, appearance, controls = {}) {
    if (!(shell instanceof HTMLElement)) {
        return appearance;
    }

    const normalized = normalizePlayerAppearance(appearance);
    shell.style.setProperty("--player-panel-opacity", `${normalized.opacity / 100}`);

    if (controls.opacityInput instanceof HTMLInputElement) {
        controls.opacityInput.value = String(normalized.opacity);
    }
    return normalized;
}

function getPlayerSizeBounds() {
    return {
        minWidth: 320,
        minHeight: 250,
        maxWidth: Math.max(320, window.innerWidth - 24),
        maxHeight: Math.max(250, window.innerHeight - 24),
    };
}

function normalizePlayerSize(rawSize) {
    const width = Number(rawSize?.width);
    const height = Number(rawSize?.height);
    const bounds = getPlayerSizeBounds();
    return {
        width: Number.isFinite(width)
            ? Math.min(Math.max(Math.round(width), bounds.minWidth), bounds.maxWidth)
            : Math.min(392, bounds.maxWidth),
        height: Number.isFinite(height)
            ? Math.min(Math.max(Math.round(height), bounds.minHeight), bounds.maxHeight)
            : Math.min(332, bounds.maxHeight),
    };
}

export function readPlayerSize() {
    return normalizePlayerSize(readStoredJson(playerSizeKey));
}

export function writePlayerSize(size) {
    const normalized = normalizePlayerSize(size);
    window.localStorage.setItem(playerSizeKey, JSON.stringify(normalized));
    return normalized;
}

export function applyPlayerSize(shell, size) {
    if (!(shell instanceof HTMLElement)) {
        return size;
    }

    const normalized = normalizePlayerSize(size);
    shell.style.setProperty("--player-panel-width", `${normalized.width}px`);
    shell.style.setProperty("--player-panel-height", `${normalized.height}px`);
    return normalized;
}

export function getPlayerLabel(track) {
    return track?.artist ? `${track.title} - ${track.artist}` : track?.title || "";
}

function hashPlayerSeed(seed) {
    let hash = 0;
    const text = String(seed || "");
    for (let index = 0; index < text.length; index += 1) {
        hash = (hash << 5) - hash + text.charCodeAt(index);
        hash |= 0;
    }
    return Math.abs(hash);
}

function getTrackArtworkLabel(track) {
    const source = `${track?.title || ""}${track?.artist || ""}`.replace(/\s+/g, "");
    if (!source) {
        return "♪";
    }

    const glyphs = Array.from(source);
    const ascii = source
        .replace(/[^a-z0-9]/gi, "")
        .slice(0, 2)
        .toUpperCase();
    if (ascii) {
        return ascii;
    }
    return glyphs.slice(0, Math.min(2, glyphs.length)).join("");
}

function buildTrackArtwork(track) {
    const seed = `${track?.title || "track"}|${track?.artist || ""}`;
    const hue = hashPlayerSeed(seed) % 360;
    const accentHue = (hue + 46) % 360;
    return {
        label: getTrackArtworkLabel(track),
        start: `hsl(${hue} 42% 58%)`,
        end: `hsl(${accentHue} 45% 28%)`,
    };
}

export function updatePlayerArtwork(scope, track) {
    if (!(scope instanceof Element)) {
        return;
    }

    const artwork = buildTrackArtwork(track);
    scope.querySelectorAll("[data-player-artwork]").forEach((node) => {
        if (!(node instanceof HTMLElement)) {
            return;
        }

        node.style.setProperty("--player-art-start", artwork.start);
        node.style.setProperty("--player-art-end", artwork.end);
        node.style.backgroundImage = track?.cover
            ? `linear-gradient(180deg, rgba(16, 22, 24, 0.08), rgba(16, 22, 24, 0.14)), url("${track.cover}")`
            : "";
        node.style.backgroundSize = track?.cover ? "cover" : "";
        node.style.backgroundPosition = track?.cover ? "center" : "";
        const label = node.querySelector("[data-player-artwork-label]");
        if (label instanceof HTMLElement) {
            label.textContent = artwork.label;
            label.hidden = Boolean(track?.cover);
        }
    });

    const bubble = scope.querySelector("[data-player-bubble]");
    if (bubble instanceof HTMLButtonElement) {
        bubble.setAttribute(
            "aria-label",
            track
                ? t(
                    "player.open_mini_player_for",
                    { label: getPlayerLabel(track) },
                    `Open mini player for ${getPlayerLabel(track)}`
                )
                : t("player.open_mini_player", {}, "Open mini player")
        );
    }
}

export function setPlayerToggleIcon(button, isPlaying) {
    if (!(button instanceof HTMLButtonElement)) {
        return;
    }

    button.innerHTML = isPlaying
        ? '<span aria-hidden="true">&#10074;&#10074;</span>'
        : '<span aria-hidden="true">&#9654;</span>';
    button.setAttribute(
        "aria-label",
        isPlaying ? t("player.pause", {}, "Pause") : t("player.play", {}, "Play")
    );
}

export function renderPlayerQueue(queuePanel, queue, currentIndex, onSelect) {
    queuePanel.replaceChildren();
    queue.forEach((track, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `audio-player__queue-item${index === currentIndex ? " is-active" : ""}`;
        button.textContent = getPlayerLabel(track);
        button.addEventListener("click", () => onSelect(index));
        queuePanel.append(button);
    });
}
