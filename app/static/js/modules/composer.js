import { bindLocationResolver } from "./geolocation.js";

function updateFileSummary(modal) {
    const fileInput = modal.querySelector("[data-file-input]");
    const summary = modal.querySelector("[data-file-summary]");
    if (!fileInput || !summary) {
        return;
    }

    const count = fileInput.files ? fileInput.files.length : 0;
    summary.textContent = count
        ? `${count} attachment(s) selected.`
        : "Mixed uploads are supported for images, videos, PDFs, and documents.";
}

export function initComposerModal() {
    const modal = document.querySelector('[data-modal="composer"]');
    if (!modal) {
        return;
    }

    const openButtons = document.querySelectorAll("[data-open-composer]");
    const closeButtons = modal.querySelectorAll("[data-close-composer]");
    const fileInput = modal.querySelector("[data-file-input]");

    const openModal = () => {
        document.body.classList.remove("is-sidebar-open");
        modal.hidden = false;
        document.body.classList.add("is-modal-open");
        modal.querySelector("textarea")?.focus();
    };

    const closeModal = () => {
        modal.hidden = true;
        document.body.classList.remove("is-modal-open");
    };

    openButtons.forEach((button) => button.addEventListener("click", openModal));
    closeButtons.forEach((button) => button.addEventListener("click", closeModal));

    if (fileInput) {
        fileInput.addEventListener("change", () => updateFileSummary(modal));
        updateFileSummary(modal);
    }

    bindLocationResolver(modal);

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) {
            closeModal();
        }
    });
}
