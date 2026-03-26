import { requestJson } from "./http.js";

export function bindLocationResolver(container) {
    const button = container.querySelector('[data-action="resolve-location"]');
    const status = container.querySelector("[data-location-status]");
    const latitudeInput = container.querySelector("[data-location-latitude]");
    const longitudeInput = container.querySelector("[data-location-longitude]");
    const labelInput = container.querySelector("[data-location-label]");
    const countryCodeInput = container.querySelector("[data-location-country-code]");
    const countryNameInput = container.querySelector("[data-location-country-name]");
    const adminAreaInput = container.querySelector("[data-location-admin-area]");
    const cityNameInput = container.querySelector("[data-location-city-name]");
    const districtNameInput = container.querySelector("[data-location-district-name]");
    const placeKeyInput = container.querySelector("[data-location-place-key]");
    const sourceInput = container.querySelector("[data-location-source]");

    if (!button || !status || !latitudeInput || !longitudeInput || !labelInput) {
        return;
    }

    if (button.dataset.locationBound === "true") {
        return;
    }

    button.dataset.locationBound = "true";
    let applyingResolvedLocation = false;

    const setStatus = (message = "") => {
        status.textContent = message;
        status.hidden = !message;
    };

    const assignStructuredFields = (result = {}) => {
        if (countryCodeInput) {
            countryCodeInput.value = result.country_code || "";
        }
        if (countryNameInput) {
            countryNameInput.value = result.country || "";
        }
        if (adminAreaInput) {
            adminAreaInput.value = result.province || "";
        }
        if (cityNameInput) {
            cityNameInput.value = result.city || "";
        }
        if (districtNameInput) {
            districtNameInput.value = result.district || "";
        }
        if (placeKeyInput) {
            placeKeyInput.value = result.place_key || "";
        }
        if (sourceInput) {
            sourceInput.value = result.location_source || "browser";
        }
    };

    const clearStructuredFields = (source = "") => {
        assignStructuredFields({});
        if (sourceInput) {
            sourceInput.value = source;
        }
    };

    setStatus(status.textContent.trim());

    [latitudeInput, longitudeInput, labelInput].forEach((input) => {
        input.addEventListener("input", () => {
            if (applyingResolvedLocation) {
                return;
            }
            const hasTypedLocation = Boolean(
                latitudeInput.value.trim() || longitudeInput.value.trim() || labelInput.value.trim(),
            );
            clearStructuredFields(hasTypedLocation ? "manual" : "");
        });
    });

    button.addEventListener("click", () => {
        if (!navigator.geolocation) {
            setStatus("Current browser does not support geolocation.");
            return;
        }

        button.disabled = true;
        setStatus("Fetching your current location...");

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

                    applyingResolvedLocation = true;
                    latitudeInput.value = String(result.latitude);
                    longitudeInput.value = String(result.longitude);
                    labelInput.value = result.formatted_address || "";
                    assignStructuredFields(result);
                    setStatus(result.formatted_address || "Location loaded.");
                } catch (error) {
                    setStatus(error.message);
                } finally {
                    applyingResolvedLocation = false;
                    button.disabled = false;
                }
            },
            (error) => {
                if (error.code === error.PERMISSION_DENIED) {
                    setStatus("Location permission was denied. You can still publish without it.");
                } else {
                    setStatus("Unable to fetch location right now.");
                }
                button.disabled = false;
            },
            { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
        );
    });
}
