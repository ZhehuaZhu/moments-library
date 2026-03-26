import { bindLocationResolver } from "./geolocation.js";
import { createComposerCitationController } from "./composer-citation-controller.js";
import { createComposerCrossPostController } from "./composer-cross-post-controller.js";
import { createComposerFileController } from "./composer-file-controller.js";

let composerController = null;

function getComposerSignal() {
    if (!(composerController instanceof AbortController) || composerController.signal.aborted) {
        composerController = new AbortController();
    }
    return composerController.signal;
}

document.addEventListener("app:before-swap", () => {
    composerController?.abort();
    composerController = null;
});

export function initComposerModal() {
    const modal = document.querySelector('[data-modal="composer"]');
    if (!modal || modal.dataset.composerInitialized === "true") {
        return;
    }
    modal.dataset.composerInitialized = "true";

    const signal = getComposerSignal();
    const openButtons = document.querySelectorAll("[data-open-composer]");
    const closeButtons = modal.querySelectorAll("[data-close-composer]");
    const fileInput = modal.querySelector("[data-file-input]");
    const libraryInput = modal.querySelector("[data-library-input]");
    const cameraInput = modal.querySelector("[data-camera-input]");
    const form = modal.querySelector("[data-composer-form]");
    const previewSection = modal.querySelector("[data-composer-preview]");
    const previewList = modal.querySelector("[data-composer-file-list]");
    const citationToggle = modal.querySelector("[data-citation-toggle]");
    const citationPanel = modal.querySelector("[data-citation-panel]");
    const citationSearch = modal.querySelector("[data-citation-search]");
    const citationResults = modal.querySelector("[data-citation-results]");
    const selectedCitationShell = modal.querySelector("[data-selected-citation]");
    const citationKindField = modal.querySelector("[data-citation-kind]");
    const citationTargetIdField = modal.querySelector("[data-citation-target-id]");
    const citationScopeButtons = modal.querySelectorAll("[data-citation-scope]");
    const contentField = form?.querySelector('textarea[name="content"]');
    const crossPostShell = modal.querySelector("[data-cross-post-shell]");
    const crossPostOptions = modal.querySelectorAll("[data-cross-post-option]");
    const disclosureSections = modal.querySelectorAll("[data-composer-disclosure]");

    let fileController;
    let citationController;

    const crossPostController = createComposerCrossPostController({
        crossPostShell,
        crossPostOptions,
        contentField,
        signal,
        getSelectedFiles: () => fileController?.getSelectedFiles() || [],
        getSelectedCitation: () => citationController?.getSelectedCitation() || null,
    });

    fileController = createComposerFileController({
        modal,
        fileInput,
        libraryInput,
        cameraInput,
        previewSection,
        previewList,
        signal,
        onFilesChange: () => crossPostController.render(),
    });

    citationController = createComposerCitationController({
        signal,
        citationToggle,
        citationPanel,
        citationSearch,
        citationResults,
        selectedCitationShell,
        citationKindField,
        citationTargetIdField,
        citationScopeButtons,
        onSelectionChange: () => crossPostController.render(),
    });

    const openModal = () => {
        document.body.classList.remove("is-sidebar-open");
        if (window.matchMedia("(max-width: 720px)").matches) {
            disclosureSections.forEach((section) => {
                section.removeAttribute("open");
            });
        }
        modal.hidden = false;
        document.body.classList.add("is-modal-open");
        modal.querySelector("textarea")?.focus();
    };

    const closeModal = () => {
        modal.hidden = true;
        document.body.classList.remove("is-modal-open");
    };

    async function submitComposerForm(event) {
        if (!(form instanceof HTMLFormElement)) {
            return;
        }

        event.preventDefault();
        fileController?.syncInputFiles();
        citationController?.syncCitationFields();

        const submitButton =
            form.querySelector('.composer-actions [type="submit"]');
        if (submitButton instanceof HTMLButtonElement) {
            submitButton.disabled = true;
        }

        try {
            const formData = new FormData(form);
            formData.delete("files");
            for (const entry of fileController?.getSelectedFiles() || []) {
                formData.append("files", entry.file, entry.file.name);
            }

            const response = await fetch(form.action, {
                method: form.method || "POST",
                body: formData,
                credentials: "same-origin",
                redirect: "follow",
            });

            window.location.href = response.url || window.location.href;
        } catch (_error) {
            if (submitButton instanceof HTMLButtonElement) {
                submitButton.disabled = false;
            }
            window.alert("Publishing failed. Please try again.");
        }
    }

    openButtons.forEach((button) => button.addEventListener("click", openModal, { signal }));
    closeButtons.forEach((button) => button.addEventListener("click", closeModal, { signal }));

    form?.addEventListener("submit", submitComposerForm, { signal });

    bindLocationResolver(modal);
    citationController.renderSelectedCitation();
    crossPostController.render();

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) {
            closeModal();
        }
    }, { signal });
}
