import { requestJson } from "./http.js";

export function bindLocationResolver(container) {
    const button = container.querySelector('[data-action="resolve-location"]');
    const status = container.querySelector("[data-location-status]");
    const latitudeInput = container.querySelector("[data-location-latitude]");
    const longitudeInput = container.querySelector("[data-location-longitude]");
    const labelInput = container.querySelector("[data-location-label]");

    if (!button || !status || !latitudeInput || !longitudeInput || !labelInput) {
        return;
    }

    if (button.dataset.locationBound === "true") {
        return;
    }

    button.dataset.locationBound = "true";

    button.addEventListener("click", () => {
        if (!navigator.geolocation) {
            status.textContent = "Current browser does not support geolocation.";
            return;
        }

        button.disabled = true;
        status.textContent = "Fetching your current location...";

        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const lat = Number(position.coords.latitude.toFixed(6));
                const lon = Number(position.coords.longitude.toFixed(6));

                try {
                    const result = await requestJson("/api/geocode", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ lat, lon })
                    });

                    latitudeInput.value = String(result.latitude);
                    longitudeInput.value = String(result.longitude);
                    labelInput.value = result.formatted_address || "";
                    status.textContent = result.formatted_address || "Location loaded.";
                } catch (error) {
                    status.textContent = error.message;
                } finally {
                    button.disabled = false;
                }
            },
            (error) => {
                if (error.code === error.PERMISSION_DENIED) {
                    status.textContent = "Location permission was denied. You can still publish without it.";
                } else {
                    status.textContent = "Unable to fetch location right now.";
                }
                button.disabled = false;
            },
            { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
        );
    });
}
