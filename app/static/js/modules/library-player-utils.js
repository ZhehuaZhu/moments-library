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
    const repeatMode = rawState?.repeatMode === "one" ? "one" : "off";

    return {
        queue,
        currentIndex,
        currentTime: Number.isFinite(currentTime) ? Math.max(currentTime, 0) : 0,
        duration: Number.isFinite(duration) ? Math.max(duration, 0) : 0,
        wasPlaying: Boolean(rawState?.wasPlaying),
        repeatMode,
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
    shell.style.setProperty(
        "--player-ui-scale",
        `${Math.min(normalized.width / 392, normalized.height / 332).toFixed(3)}`
    );
    return normalized;
}

export function animateMediaVolume(media, from, to, duration = 220) {
    if (!(media instanceof HTMLMediaElement)) {
        return Promise.resolve();
    }

    media.volume = Math.min(Math.max(from, 0), 1);
    if (duration <= 0) {
        media.volume = Math.min(Math.max(to, 0), 1);
        return Promise.resolve();
    }

    return new Promise((resolve) => {
        const startTime = performance.now();
        const tick = (now) => {
            const progress = Math.min((now - startTime) / duration, 1);
            media.volume = from + (to - from) * progress;
            if (progress >= 1) {
                resolve();
                return;
            }
            window.requestAnimationFrame(tick);
        };

        window.requestAnimationFrame(tick);
    });
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

export function renderPlayerQueue(queuePanel, queue, currentIndex, handlers = {}) {
    queuePanel.replaceChildren();
    queue.forEach((track, index) => {
        const item = document.createElement("div");
        item.className = `audio-player__queue-item${index === currentIndex ? " is-active" : ""}`;
        item.dataset.playerQueueItem = "true";

        const button = document.createElement("button");
        button.type = "button";
        button.className = "audio-player__queue-track";
        button.textContent = getPlayerLabel(track);
        button.addEventListener("click", () => handlers.onSelect?.(index));

        const actions = document.createElement("div");
        actions.className = "audio-player__queue-actions";

        const moveUp = document.createElement("button");
        moveUp.type = "button";
        moveUp.className = "icon-button icon-button--ghost audio-player__queue-action";
        moveUp.innerHTML = '<span aria-hidden="true">&#8593;</span>';
        moveUp.disabled = index === 0;
        moveUp.setAttribute("aria-label", t("player.queue_move_up", {}, "Move track earlier"));
        moveUp.addEventListener("click", () => handlers.onMove?.(index, -1));

        const moveDown = document.createElement("button");
        moveDown.type = "button";
        moveDown.className = "icon-button icon-button--ghost audio-player__queue-action";
        moveDown.innerHTML = '<span aria-hidden="true">&#8595;</span>';
        moveDown.disabled = index === queue.length - 1;
        moveDown.setAttribute("aria-label", t("player.queue_move_down", {}, "Move track later"));
        moveDown.addEventListener("click", () => handlers.onMove?.(index, 1));

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "icon-button icon-button--ghost audio-player__queue-action";
        remove.innerHTML = '<span aria-hidden="true">&#10005;</span>';
        remove.setAttribute("aria-label", t("player.remove_from_queue", {}, "Remove track from queue"));
        remove.addEventListener("click", () => handlers.onRemove?.(index));

        actions.append(moveUp, moveDown, remove);
        item.append(button, actions);
        queuePanel.append(item);
    });
}
