const vendorPromises = new Map();

function loadScriptOnce(src, globalName) {
    if (globalName && window[globalName]) {
        return Promise.resolve(window[globalName]);
    }

    const cacheKey = `${globalName || "script"}::${src}`;
    if (vendorPromises.has(cacheKey)) {
        return vendorPromises.get(cacheKey);
    }

    const promise = new Promise((resolve, reject) => {
        const existing = document.querySelector(`script[data-vendor-src="${src}"]`);
        if (existing) {
            existing.addEventListener("load", () => resolve(globalName ? window[globalName] : undefined), {
                once: true,
            });
            existing.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)), {
                once: true,
            });
            return;
        }

        const script = document.createElement("script");
        script.src = src;
        script.async = true;
        script.dataset.vendorSrc = src;
        script.addEventListener(
            "load",
            () => {
                if (globalName && !window[globalName]) {
                    reject(new Error(`Vendor ${globalName} did not initialize.`));
                    return;
                }
                resolve(globalName ? window[globalName] : undefined);
            },
            { once: true }
        );
        script.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)), {
            once: true,
        });
        document.head.append(script);
    });

    vendorPromises.set(cacheKey, promise);
    return promise;
}

export function ensureMammoth() {
    return loadScriptOnce("/static/vendor/mammoth.browser.min.js", "mammoth");
}

export function ensureEpubJs() {
    return loadScriptOnce("/static/vendor/epub.min.js", "ePub");
}

export function ensureLeaflet() {
    return loadScriptOnce("/static/vendor/leaflet/leaflet.js", "L");
}
