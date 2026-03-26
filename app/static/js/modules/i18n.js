let translations = {};

export function refreshTranslations(root = document) {
    const translationScript =
        root.querySelector?.("[data-ui-translations]") ||
        document.querySelector("[data-ui-translations]");

    if (!translationScript) {
        translations = {};
        return;
    }

    try {
        const payload = JSON.parse(translationScript.textContent || "{}");
        translations = payload && typeof payload === "object" ? payload : {};
    } catch {
        translations = {};
    }
}

refreshTranslations();

export function t(key, values = {}, fallback = key) {
    const template = typeof translations[key] === "string" ? translations[key] : fallback;
    return template.replace(/\{(\w+)\}/g, (match, token) => {
        if (Object.prototype.hasOwnProperty.call(values, token)) {
            return String(values[token]);
        }
        return match;
    });
}
