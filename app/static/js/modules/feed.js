import { requestJson } from "./http.js";

function collectCheckedFolderIds(form) {
    return Array.from(form.querySelectorAll('input[name="folder_ids"]:checked')).map((input) =>
        Number(input.value)
    );
}

function initFolderUpdates() {
    document.querySelectorAll("[data-folder-form]").forEach((form) => {
        if (form.dataset.folderBound === "true") {
            return;
        }

        form.dataset.folderBound = "true";
        form.addEventListener("submit", async (event) => {
            event.preventDefault();

            const card = form.closest("[data-moment-card]");
            if (!card) {
                return;
            }

            try {
                await requestJson(`/api/moments/${card.dataset.momentId}/folders`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        folder_ids: collectCheckedFolderIds(form),
                    }),
                });
                window.location.reload();
            } catch (error) {
                window.alert(error.message);
            }
        });
    });
}

function initDeleteMoments() {
    document.querySelectorAll("[data-delete-moment]").forEach((button) => {
        button.addEventListener("click", async () => {
            const card = button.closest("[data-moment-card]");
            if (!card) {
                return;
            }

            const confirmed = window.confirm("Move this moment into the recycle bin?");
            if (!confirmed) {
                return;
            }

            try {
                await requestJson(`/api/moments/${card.dataset.momentId}`, {
                    method: "DELETE",
                });
                window.location.reload();
            } catch (error) {
                window.alert(error.message);
            }
        });
    });
}

function initRestoreMoments() {
    document.querySelectorAll("[data-restore-moment]").forEach((button) => {
        button.addEventListener("click", async () => {
            const card = button.closest("[data-moment-card]");
            if (!card) {
                return;
            }

            try {
                await requestJson(`/api/moments/${card.dataset.momentId}/restore`, {
                    method: "POST",
                });
                window.location.reload();
            } catch (error) {
                window.alert(error.message);
            }
        });
    });
}

async function copyText(text) {
    if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return;
    }

    const field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.append(field);
    field.select();
    document.execCommand("copy");
    field.remove();
}

function setShareFeedback(row, message = "", isVisible = true) {
    const feedback = row.querySelector("[data-share-feedback]");
    if (!(feedback instanceof HTMLElement)) {
        return;
    }

    feedback.textContent = message;
    feedback.hidden = !isVisible || !message;
}

function initCrossPostCopy() {
    document.querySelectorAll("[data-copy-cross-post-caption]").forEach((button) => {
        if (button.dataset.crossPostCopyBound === "true") {
            return;
        }

        button.dataset.crossPostCopyBound = "true";
        button.addEventListener("click", async () => {
            const card = button.closest("[data-cross-post-card]");
            const captionField = card?.querySelector("[data-cross-post-caption]");
            if (!(captionField instanceof HTMLTextAreaElement)) {
                return;
            }

            try {
                await copyText(captionField.value);
                const copiedLabel = button.dataset.copiedLabel || "Copied";
                const copyLabel = button.dataset.copyLabel || "Copy Caption";
                button.textContent = copiedLabel;
                window.setTimeout(() => {
                    button.textContent = copyLabel;
                }, 1200);
            } catch (error) {
                window.alert(error instanceof Error ? error.message : "Copy failed.");
            }
        });
    });
}

function initCrossPostActions() {
    document.querySelectorAll("[data-cross-post-action]").forEach((button) => {
        if (button.dataset.crossPostBound === "true") {
            return;
        }

        button.dataset.crossPostBound = "true";
        button.addEventListener("click", async () => {
            const card = button.closest("[data-moment-card]");
            if (!card) {
                return;
            }

            try {
                await requestJson(
                    `/api/moments/${card.dataset.momentId}/cross-post/${button.dataset.crossPostPlatform}`,
                    {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            action: button.dataset.crossPostAction,
                        }),
                    },
                );
                window.location.reload();
            } catch (error) {
                window.alert(error.message);
            }
        });
    });
}

function initMomentShare() {
    document.querySelectorAll("[data-share-platform]").forEach((button) => {
        if (button.dataset.shareBound === "true") {
            return;
        }

        button.dataset.shareBound = "true";
        button.addEventListener("click", () => {
            const row = button.closest("[data-share-platform-row]");
            if (!row) {
                return;
            }

            const placeholderLabel =
                button.dataset.sharePlaceholderLabel ||
                "Jump window placeholder is reserved here for the next step.";

            setShareFeedback(row, placeholderLabel);
        });
    });
}

export function initFeedInteractions() {
    initFolderUpdates();
    initDeleteMoments();
    initRestoreMoments();
    initCrossPostCopy();
    initCrossPostActions();
    initMomentShare();
}
