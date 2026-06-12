"""
Tests for sub-flow A — drug catalog validation + medication voice extraction.

The catalog validates an extracted drug name against Colombia (INVIMA CUM)
first, falling back to Spain (CIMA). HTTP is mocked via _http_get_json so the
tests are offline and deterministic.
"""
import pytest
import httpx

from src.domains.medications.drug_catalog import DrugCatalogService, _norm


def test_norm_strips_accents_and_case():
    assert _norm("Losartán  POTÁSICO") == "losartan potasico"


@pytest.mark.asyncio
async def test_validate_uses_colombia_and_dedupes(monkeypatch):
    svc = DrugCatalogService()

    async def fake_get(url, params):
        if "datos.gov.co" in url:
            return [
                {"producto": "COZAAR 100 MG", "principioactivo": "LOSARTAN POTASICO", "estadoregistro": "Vigente"},
                {"producto": "COZAAR 100 MG", "principioactivo": "LOSARTAN POTASICO", "estadoregistro": "Vigente"},  # dup
                {"producto": "VENCIDO", "principioactivo": "X", "estadoregistro": "Cancelado"},  # filtered out
            ]
        return {"resultados": []}

    monkeypatch.setattr(svc, "_http_get_json", fake_get)
    res = await svc.validate("losartan")
    assert res["matched"] is True
    assert res["source"] == "co"
    assert res["canonical_name"] == "COZAAR 100 MG"
    assert res["active_ingredient"] == "LOSARTAN POTASICO"
    assert len(res["candidates"]) == 1  # deduped + only "Vigente"


@pytest.mark.asyncio
async def test_validate_falls_back_to_spain_when_colombia_empty(monkeypatch):
    svc = DrugCatalogService()

    async def fake_get(url, params):
        if "datos.gov.co" in url:
            return []
        return {"resultados": [{"nombre": "Losartan Cinfa 100 mg", "pactivos": "LOSARTAN POTASICO"}]}

    monkeypatch.setattr(svc, "_http_get_json", fake_get)
    res = await svc.validate("losartan")
    assert res["matched"] is True
    assert res["source"] == "es"
    assert res["canonical_name"] == "Losartan Cinfa 100 mg"


@pytest.mark.asyncio
async def test_validate_falls_back_when_colombia_errors(monkeypatch):
    svc = DrugCatalogService()

    async def fake_get(url, params):
        if "datos.gov.co" in url:
            raise httpx.ConnectError("boom")
        return {"resultados": [{"nombre": "Losartan Cinfa", "pactivos": "LOSARTAN"}]}

    monkeypatch.setattr(svc, "_http_get_json", fake_get)
    res = await svc.validate("losartan")
    assert res["source"] == "es"
    assert res["matched"] is True


@pytest.mark.asyncio
async def test_validate_no_match(monkeypatch):
    svc = DrugCatalogService()

    async def fake_get(url, params):
        return [] if "datos.gov.co" in url else {"resultados": []}

    monkeypatch.setattr(svc, "_http_get_json", fake_get)
    res = await svc.validate("xyzzy-not-a-drug")
    assert res["matched"] is False
    assert res["candidates"] == []
    assert res["source"] is None


@pytest.mark.asyncio
async def test_validate_empty_name_makes_no_request():
    # Blank name short-circuits before any HTTP call.
    res = await DrugCatalogService().validate("   ")
    assert res["matched"] is False


@pytest.mark.asyncio
async def test_parse_medication_intent_fallback_without_llm():
    # Without an OpenAI client, a drug name cannot be safely extracted.
    from src.domains.health.voice_parsing import VoiceParsingService
    svc = VoiceParsingService()
    svc.client = None
    res = await svc.parse_medication_intent("quiero registrar losartan 50 mg cada 12 horas")
    assert res["name"] is None
    assert res["confidence"] == "low"
