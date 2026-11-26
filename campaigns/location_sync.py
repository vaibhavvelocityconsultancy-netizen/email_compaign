"""On-demand CountryStateCity imports into the existing location masters."""

import os

import requests
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import City, Country, State


BASE_URL = "https://api.countrystatecity.in/v1"


class LocationSyncError(Exception):
    pass


def _api_get(path):
    api_key = os.getenv("CSC_API_KEY", "").strip()
    if not api_key:
        raise LocationSyncError("CountryStateCity API is not configured (CSC_API_KEY is missing).")
    try:
        response = requests.get(
            f"{BASE_URL}{path}",
            headers={"X-CSCAPI-KEY": api_key},
            timeout=(3.05, 20),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise LocationSyncError("Could not retrieve locations from CountryStateCity.") from exc
    if not isinstance(payload, list):
        raise LocationSyncError("CountryStateCity returned an invalid location response.")
    return payload


def _name(item):
    value = item.get("name") if isinstance(item, dict) else None
    return value.strip()[:100] if isinstance(value, str) and value.strip() else None


def _country_code(item):
    code = item.get("iso2") if isinstance(item, dict) else None
    return code.strip().upper()[:10] if isinstance(code, str) and code.strip() else None


def _cached_country(tenant_id, item):
    name, code = _name(item), _country_code(item)
    if not name or not code:
        return None
    country = Country.objects.filter(tenant_id=tenant_id, code__iexact=code).first()
    if country is None:
        country = Country.objects.filter(tenant_id=tenant_id, name__iexact=name).first()
    if country:
        if len((country.code or "").strip()) != 2:
            country.code = code
            country.save(update_fields=["code", "updated_at"])
        return country
    try:
        with transaction.atomic():
            country, _ = Country.objects.get_or_create(
                tenant_id=tenant_id,
                name=name,
                defaults={"code": code},
            )
            if len((country.code or "").strip()) != 2:
                country.code = code
                country.save(update_fields=["code", "updated_at"])
            return country
    except IntegrityError:
        return Country.objects.filter(tenant_id=tenant_id, code__iexact=code).first()


def search_and_cache_countries(tenant_id, query):
    normalized_query = query.strip().casefold()
    if len(normalized_query) < 2:
        return Country.objects.none()

    matching_ids = []
    for item in _api_get("/countries"):
        name = _name(item)
        if name and normalized_query in name.casefold():
            country = _cached_country(tenant_id, item)
            if country:
                matching_ids.append(country.pk)
    return Country.objects.filter(
        tenant_id=tenant_id,
        pk__in=matching_ids,
        is_active=True,
    )


def sync_states(country):
    states = State.objects.filter(tenant_id=country.tenant_id, country=country)
    if country.states_synced_at:
        return states.filter(is_active=True)

    code = (country.code or "").strip().upper()
    if len(code) != 2:
        raise LocationSyncError("This country has no valid ISO2 code for state lookup.")
    tenant_id = country.tenant_id
    for item in _api_get(f"/countries/{code}/states"):
        name, iso_code = _name(item), _country_code(item)
        if not name:
            continue
        existing = None
        if iso_code:
            existing = State.objects.filter(
                tenant_id=tenant_id, country=country, iso_code__iexact=iso_code
            ).first()
        if existing is None:
            existing = State.objects.filter(
                tenant_id=tenant_id, country=country, name__iexact=name
            ).first()
        if existing:
            if not existing.iso_code and iso_code:
                existing.iso_code = iso_code
                existing.save(update_fields=["iso_code", "updated_at"])
            continue
        try:
            with transaction.atomic():
                state, _ = State.objects.get_or_create(
                    tenant_id=tenant_id,
                    country=country,
                    name=name,
                    defaults={"iso_code": iso_code},
                )
                if not state.iso_code and iso_code:
                    state.iso_code = iso_code
                    state.save(update_fields=["iso_code", "updated_at"])
        except IntegrityError:
            # A parallel request may have inserted this ISO code after our lookup.
            if not iso_code or not State.objects.filter(
                tenant_id=tenant_id, country=country, iso_code__iexact=iso_code
            ).exists():
                raise
    country.states_synced_at = timezone.now()
    country.save(update_fields=["states_synced_at", "updated_at"])
    return State.objects.filter(tenant_id=tenant_id, country=country, is_active=True)


def sync_cities(state):
    cities = City.objects.filter(tenant_id=state.tenant_id, state=state)
    if state.cities_synced_at:
        return cities.filter(is_active=True)

    country = state.country
    country_code = (country.code or "").strip().upper()
    state_code = (state.iso_code or "").strip().upper()
    if len(country_code) != 2:
        raise LocationSyncError("This country has no valid ISO2 code for city lookup.")
    if not state_code:
        # States created manually before ISO codes were added still need to
        # resolve to the upstream code before city lookup can work.
        match = next(
            (
                item
                for item in _api_get(f"/countries/{country_code}/states")
                if (_name(item) or "").casefold() == state.name.casefold()
            ),
            None,
        )
        state_code = _country_code(match) if match else None
        if not state_code:
            raise LocationSyncError("Could not match this state to a CountryStateCity ISO code.")
        state.iso_code = state_code
        state.save(update_fields=["iso_code", "updated_at"])
    for item in _api_get(f"/countries/{country_code}/states/{state_code}/cities"):
        name = _name(item)
        if not name:
            continue
        if City.objects.filter(
            tenant_id=state.tenant_id, state=state, name__iexact=name
        ).exists():
            continue
        try:
            with transaction.atomic():
                City.objects.get_or_create(
                    tenant_id=state.tenant_id,
                    state=state,
                    name=name,
                )
        except IntegrityError:
            # A concurrent request created the same tenant/state/name row.
            if not City.objects.filter(
                tenant_id=state.tenant_id, state=state, name__iexact=name
            ).exists():
                raise
    state.cities_synced_at = timezone.now()
    state.save(update_fields=["cities_synced_at", "updated_at"])
    return City.objects.filter(tenant_id=state.tenant_id, state=state, is_active=True)
