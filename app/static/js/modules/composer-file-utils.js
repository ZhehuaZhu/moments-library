import { t } from "./i18n.js";

const previewableExtensions = {
    image: new Set(["jpg", "jpeg", "png", "gif", "webp"]),
    video: new Set(["mp4", "mov", "webm"]),
    pdf: new Set(["pdf"]),
    docx: new Set(["docx"]),
    doc: new Set(["doc"]),
    text: new Set(["txt"]),
};

export function extensionForFile(file) {
    const parts = file.name.toLowerCase().split(".");
    return parts.length > 1 ? parts.at(-1) || "" : "";
}

export function previewKindForFile(file) {
    const extension = extensionForFile(file);

    if (previewableExtensions.image.has(extension)) {
        return "image";
    }
    if (previewableExtensions.video.has(extension)) {
        return "video";
    }
    if (previewableExtensions.pdf.has(extension)) {
        return "pdf";
    }
    if (previewableExtensions.docx.has(extension)) {
        return "docx";
    }
    if (previewableExtensions.doc.has(extension)) {
        return "doc";
    }
    if (previewableExtensions.text.has(extension)) {
        return "text";
    }
    return "document";
}

export function fileSignature(file) {
    return `${file.name}::${file.size}::${file.lastModified}`;
}

export function buildFileList(fileInput, selectedFiles) {
    const transfer = new DataTransfer();
    selectedFiles.forEach((entry) => transfer.items.add(entry.file));
    fileInput.files = transfer.files;
}

export function updateFileSummary(modal, countOverride = null) {
    const fileInput = modal.querySelector("[data-file-input]");
    const summary = modal.querySelector("[data-file-summary]");
    if (!fileInput || !summary) {
        return;
    }

    const count =
        typeof countOverride === "number"
            ? countOverride
            : (fileInput.files ? fileInput.files.length : 0);
    summary.hidden = count === 0;
    summary.textContent = count
        ? t("composer.attachments_selected", { count }, `${count} attachment(s) selected.`)
        : "";
}

export function reorderEntries(entries, fromIndex, toIndex) {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) {
        return entries;
    }

    const next = [...entries];
    const [moved] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, moved);
    return next;
}
