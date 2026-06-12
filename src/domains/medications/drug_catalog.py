"""
Drug catalog validation for the voice medication-registration flow (sub-flow A).

A drug name extracted from speech is validated against a verified registry so we
never store a hallucinated medication. Source order:
  1. Colombia - INVIMA CUM dataset (datos.gov.co Socrata, full-text $q).
  2. Spain    - CIMA / AEMPS REST API (fallback when Colombia has no match).

Validation is done live over HTTP (httpx). It degrades gracefully: on any
network error the next source is tried, and if all fail the caller gets
matched=False (the app then asks the patient to repeat / pick a candidate).
"""
import unicodedata
from typing import Any, Dict, List

import httpx

from src._config.logger import get_logger

logger = get_logger(__name__)

_CO_URL = "https://www.datos.gov.co/resource/i7cb-raxc.json"
_CIMA_URL = "https://cima.aemps.es/cima/rest/medicamentos"
_TIMEOUT = 6.0
_MAX_CANDIDATES = 5


def _norm(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace - for de-duplication."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


class DrugCatalogService:
    """Validates a drug name against the Colombian CUM registry, then CIMA."""

    async def _http_get_json(self, url: str, params: dict) -> Any:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers={"Accept": "application/json"})
            resp.raise_for_status()
            return resp.json()

    async def _search_colombia(self, name: str) -> List[Dict[str, str]]:
        rows = await self._http_get_json(_CO_URL, {"$q": name, "$limit": 20})
        out: List[Dict[str, str]] = []
        seen = set()
        for row in rows or []:
            if str(row.get("estadoregistro", "")).strip().lower() != "vigente":
                continue
            prod = (row.get("producto") or "").strip()
            ai = (row.get("principioactivo") or "").strip()
            key = _norm(prod)
            if prod and key and key not in seen:
                seen.add(key)
                out.append({"name": prod, "active_ingredient": ai, "source": "co"})
        return out

    async def _search_spain(self, name: str) -> List[Dict[str, str]]:
        data = await self._http_get_json(_CIMA_URL, {"nombre": name})
        rows = (data.get("resultados") if isinstance(data, dict) else None) or []
        out: List[Dict[str, str]] = []
        seen = set()
        for row in rows:
            prod = (row.get("nombre") or "").strip()
            ai = (row.get("pactivos") or "").strip()
            key = _norm(prod)
            if prod and key and key not in seen:
                seen.add(key)
                out.append({"name": prod, "active_ingredient": ai, "source": "es"})
        return out

    async def validate(self, name: str) -> Dict[str, Any]:
        """
        Validate a drug name against the registries.

        Returns: {matched, canonical_name, active_ingredient, candidates, source}.
        Colombia is tried first; Spain (CIMA) is the fallback.
        """
        result: Dict[str, Any] = {
            "matched": False,
            "canonical_name": None,
            "active_ingredient": None,
            "candidates": [],
            "source": None,
        }
        if not name or not name.strip():
            return result

        candidates: List[Dict[str, str]] = []
        try:
            candidates = await self._search_colombia(name)
        except Exception as e:
            logger.warning(f"drug catalog: Colombia (CUM) lookup failed for '{name}': {e}")

        if not candidates:
            try:
                candidates = await self._search_spain(name)
            except Exception as e:
                logger.warning(f"drug catalog: Spain (CIMA) lookup failed for '{name}': {e}")

        if candidates:
            best = candidates[0]
            result.update(
                matched=True,
                canonical_name=best["name"],
                active_ingredient=best["active_ingredient"],
                candidates=candidates[:_MAX_CANDIDATES],
                source=best["source"],
            )
        return result
