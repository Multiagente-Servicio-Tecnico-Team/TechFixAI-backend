from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs/migrations/007-sale-test-fixture-cleanup.md"


def test_one_off_cleanup_report_is_historical_and_not_replayable():
    report = REPORT.read_text(encoding="utf-8").lower()
    assert "reporte historico" in report
    assert "no estan en el repositorio" in report
    assert "volver a borrar" in report
    assert not (ROOT / "sql/operations/cleanup_sale_test_fixture.py").exists()
    assert not (ROOT / "sql/operations/sale-test-fixture-2026-11-03.json").exists()
