import json
from datetime import datetime, timedelta, timezone

import requests

import macro_fetcher


def test_normalize_rate_accepts_decimal_and_percentage():
    assert macro_fetcher._normalize_rate(0.0808) == 0.0808
    assert macro_fetcher._normalize_rate(8.08) == 0.0808
    assert macro_fetcher._normalize_rate(None) is None


def test_ipca_trend_uses_weekly_observations():
    assert macro_fetcher._calc_ipca_trend([0.060, 0.058, 0.056, 0.054]) == "alta"
    assert macro_fetcher._calc_ipca_trend([0.050, 0.052, 0.054, 0.056]) == "baixa"
    assert macro_fetcher._calc_ipca_trend([0.050]) == "estavel"


def test_sample_focus_weekly_uses_latest_and_four_weeks_ago():
    items = [
        {"DataReferencia": "2026", "Data": "2026-07-10", "Mediana": 5.16},
        {"DataReferencia": "2026", "Data": "2026-07-03", "Mediana": 5.30},
        {"DataReferencia": "2026", "Data": "2026-06-26", "Mediana": 5.30},
        {"DataReferencia": "2026", "Data": "2026-06-19", "Mediana": 5.30},
        {"DataReferencia": "2026", "Data": "2026-06-12", "Mediana": 5.30},
        {"DataReferencia": "2027", "Data": "2026-07-10", "Mediana": 4.20},
    ]

    sampled = macro_fetcher._sample_focus_weekly(items, 2026)

    assert sampled[0] == {"date": "2026-07-10", "value": 0.0516, "weeks_ago": 0}
    assert sampled[-1] == {"date": "2026-06-12", "value": 0.053, "weeks_ago": 4}


def test_fetch_focus_uses_official_annual_schema(monkeypatch):
    values = {
        "IPCA": {2026: 5.16, 2027: 4.20, 2028: 3.70, 2029: 3.50},
        "Selic": {2026: 14.00, 2027: 12.00, 2028: 10.50, 2029: 10.00},
        "Câmbio": {2026: 5.20, 2027: 5.28, 2028: 5.34, 2029: 5.40},
        "PIB Total": {2026: 1.99, 2027: 1.65, 2028: 2.00, 2029: 2.00},
    }

    def fake_get(_url, params=None):
        assert "DataReferencia eq '2026'" in params["$filter"]
        assert params["$orderby"] == "Data desc"
        indicator = next(name for name in values if name in params["$filter"])
        return {"value": [
            {
                "Indicador": indicator,
                "Data": "2026-07-10",
                "DataReferencia": str(year),
                "Mediana": value,
                "baseCalculo": 0,
            }
            for year, value in values[indicator].items()
        ]}

    monkeypatch.setattr(macro_fetcher, "_get", fake_get)
    result = macro_fetcher.fetch_focus()

    assert result["FOCUS_IPCA"] == [0.0516, 0.042, 0.037, 0.035]
    assert result["FOCUS_SELIC"] == [0.14, 0.12, 0.105, 0.10]
    assert result["FOCUS_CAMBIO"] == [5.20, 5.28, 5.34, 5.40]
    assert result["FOCUS_PIB"] == [0.0199, 0.0165, 0.02, 0.02]
    assert result["FOCUS_DATA_SOURCE"] == "bcb_expectativas_odata"


def test_tesouro_snapshot_keeps_real_data_and_scores(tmp_path, monkeypatch):
    history_file = tmp_path / "tesouro_history.json"
    monkeypatch.setattr(macro_fetcher, "TESOURO_HISTORY_FILE", str(history_file))
    bonds = [{
        "name": "Tesouro IPCA+ 2035",
        "buy_yield": 0.068,
        "buy_price": 1200.0,
        "is_demo": False,
    }]

    macro_fetcher.record_tesouro_snapshot(bonds, "2026-07-13T12:00:00+00:00")
    macro_fetcher.record_tesouro_scores(
        [{"name": "Tesouro IPCA+ 2035", "score": 8.5}],
        "2026-07-13T12:00:00+00:00",
    )

    saved = json.loads(history_file.read_text(encoding="utf-8"))
    point = saved["Tesouro IPCA+ 2035"][0]
    assert point == {
        "date": "2026-07-13", "buy_yield": 0.068, "buy_price": 1200.0,
        "source": "tesouro_direto_snapshot", "score": 8.5,
    }


def test_tesouro_snapshot_keeps_only_five_years(tmp_path, monkeypatch):
    history_file = tmp_path / "tesouro_history.json"
    history_file.write_text(
        '{"Tesouro IPCA+ 2035": [{"date": "2020-07-12", "buy_yield": 0.06}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(macro_fetcher, "TESOURO_HISTORY_FILE", str(history_file))

    macro_fetcher.record_tesouro_snapshot(
        [{"name": "Tesouro IPCA+ 2035", "buy_yield": 0.068, "buy_price": 1200.0, "is_demo": False}],
        "2026-07-13T12:00:00+00:00",
    )

    saved = json.loads(history_file.read_text(encoding="utf-8"))
    assert [point["date"] for point in saved["Tesouro IPCA+ 2035"]] == ["2026-07-13"]


def test_demo_bonds_are_not_added_to_history(tmp_path, monkeypatch):
    history_file = tmp_path / "tesouro_history.json"
    monkeypatch.setattr(macro_fetcher, "TESOURO_HISTORY_FILE", str(history_file))

    macro_fetcher.record_tesouro_snapshot(
        [{"name": "Demo", "buy_yield": 0.1, "buy_price": 100.0, "is_demo": True}],
        "2026-07-13T12:00:00+00:00",
    )

    assert macro_fetcher.get_tesouro_history("Demo") == []


def test_parse_tesouro_csv_builds_current_bond_with_real_history():
    content = """Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;PU Compra Manha;PU Venda Manha;PU Base Manha
Tesouro IPCA+;15/08/2032;10/07/2026;8,09;8,21;2957,70;2936,49;2936,49
Tesouro IPCA+;15/08/2032;09/07/2026;8,23;8,35;2937,35;2916,43;2916,43
Tesouro Prefixado;01/01/2029;10/07/2026;14,04;14,16;724,55;722,31;722,31
"""

    bonds = macro_fetcher._parse_tesouro_csv(content)
    ipca = next(bond for bond in bonds if bond["name"] == "Tesouro IPCA+ 2032")

    assert ipca["buy_yield"] == 0.0809
    assert ipca["sell_yield"] == 0.0821
    assert ipca["buy_price"] == 2957.70
    assert ipca["sell_price"] == 2936.49
    assert ipca["market_date"] == "2026-07-10"
    assert ipca["data_source"] == "tesouro_transparente_csv"
    assert [point["date"] for point in ipca["history"]] == ["2026-07-09", "2026-07-10"]
    assert {point["source"] for point in ipca["history"]} == {"tesouro_transparente_csv"}


def test_tesouro_csv_retries_transient_failure(monkeypatch):
    content = """Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;PU Compra Manha;PU Venda Manha
Tesouro Selic;01/03/2031;10/07/2026;10,00;10,10;19000,00;18990,00
"""

    class Response:
        def __init__(self, status_code, body=b""):
            self.status_code = status_code
            self.content = body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"HTTP {self.status_code}")

    responses = [Response(503), Response(200, content.encode("latin-1"))]
    monkeypatch.setattr(macro_fetcher.SESSION, "get", lambda *_args, **_kwargs: responses.pop(0))
    monkeypatch.setattr(macro_fetcher.time, "sleep", lambda _seconds: None)

    bonds = macro_fetcher._fetch_tesouro_transparente_csv()

    assert len(bonds) == 1
    assert bonds[0]["data_source"] == "tesouro_transparente_csv"


def test_demo_tesouro_cache_expires_after_one_hour():
    now = datetime.now(timezone.utc)
    demo_state = {
        "fetched_at": (now - timedelta(hours=1, minutes=1)).isoformat(),
        "TESOURO_DIRETO_BONDS": [{"is_demo": True}],
    }
    official_state = {
        "fetched_at": (now - timedelta(hours=2)).isoformat(),
        "TESOURO_DIRETO_BONDS": [{"is_demo": False}],
    }

    assert macro_fetcher._is_stale(demo_state) is True
    assert macro_fetcher._is_stale(official_state) is False
