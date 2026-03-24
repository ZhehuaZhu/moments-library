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

export function initFeedInteractions() {
    initFolderUpdates();
    initDeleteMoments();
    initRestoreMoments();
}
