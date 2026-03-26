let csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";

export function refreshCsrfToken(root = document) {
    csrfToken =
        root.querySelector?.('meta[name="csrf-token"]')?.content ||
        document.querySelector('meta[name="csrf-token"]')?.content ||
        "";
}

function withCsrf(headers = {}) {
    return csrfToken ? { "X-CSRFToken": csrfToken, ...headers } : headers;
}

export async function requestJson(url, options = {}) {
    const response = await fetch(url, {
        credentials: "same-origin",
        ...options,
        headers: withCsrf(options.headers || {})
    });

    const text = await response.text();
    let payload = {};

    if (text) {
        try {
            payload = JSON.parse(text);
        } catch (_error) {
            payload = {};
        }
    }

    if (!response.ok) {
        throw new Error(payload.error || `Request failed (${response.status})`);
    }

    return payload;
}
