from __future__ import annotations

from typing import Any

import requests

NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"


class GeocodingError(RuntimeError):
    pass


def reverse_geocode(lat: float, lon: float, user_agent: str) -> dict[str, Any]:
    headers = {
        "Accept-Language": "zh-CN,zh;q=0.9",
        "User-Agent": user_agent,
    }
    params = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "addressdetails": 1,
    }

    try:
        response = requests.get(
            NOMINATIM_REVERSE_URL,
            headers=headers,
            params=params,
            timeout=8,
        )
        if response.status_code == 429:
            raise GeocodingError("Geocoding service is busy. Please try again later.")
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        raise GeocodingError("Reverse geocoding failed. Please try again later.") from error
    except ValueError as error:
        raise GeocodingError("Geocoding service returned invalid data.") from error

    address = payload.get("address", {})
    province = address.get("state") or address.get("province") or address.get("region") or ""
    city = (
        address.get("city")
        or address.get("town")
        or address.get("municipality")
        or address.get("county")
        or ""
    )
    district = (
        address.get("city_district")
        or address.get("district")
        or address.get("suburb")
        or address.get("county")
        or ""
    )
    road = (
        address.get("road")
        or address.get("pedestrian")
        or address.get("residential")
        or address.get("neighbourhood")
        or ""
    )

    parts: list[str] = []
    for item in (province, city, district, road):
        if item and item not in parts:
            parts.append(item)

    formatted_address = " ".join(parts) or payload.get("display_name") or "Unknown location"

    return {
        "formatted_address": formatted_address,
        "province": province,
        "city": city,
        "district": district,
        "road": road,
        "latitude": lat,
        "longitude": lon,
    }
