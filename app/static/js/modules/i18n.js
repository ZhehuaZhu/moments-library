const translationScript = document.querySelector("[data-ui-translations]");

let translations = {};

if (translationScript) {
    try {
        const payload = JSON.parse(translationScript.textContent || "{}");
        if (payload && typeof payload === "object") {
            translations = payload;
        }
    } catch {
        translations = {};
    }
}

export function t(key, values = {}, fallback = key) {
    const template = typeof translations[key] === "string" ? translations[key] : fallback;
    return template.replace(/\{(\w+)\}/g, (match, token) => {
        if (Object.prototype.hasOwnProperty.call(values, token)) {
            return String(values[token]);
        }
        return match;
    });
}
