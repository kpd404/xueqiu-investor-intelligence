from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def read(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8").lower()


def test_backup_contract():
    text = read("backup-database.ps1")
    assert "pg_dump" in text
    assert "--format=custom" in text
    assert ".local" in text and "backups" in text
    assert "get-filehash" in text
    assert "pgpassword" in text
    assert "postgresql+psycopg://" not in text


def test_restore_contract():
    text = read("restore-database.ps1")
    assert "pg_restore" in text
    assert "snowball_restore_verify_" in text
    assert "live_database_refusal" in text
    assert "createdb" in text
    assert "--host=$($c.host)" in text
    assert "restore_target_probe_failed" in text
    assert "dropdb" not in text


def test_verifier_contract():
    text = read("verify_database_restore.py")
    assert "critical_tables" in text
    assert "integrity_queries" in text
    assert "get_asset_intelligence_product_service" in text
    assert "get_investor_intelligence_product_service" in text
    assert "operational_status" in text


def test_no_secret_output_contract():
    for name in ("backup-database.ps1", "restore-database.ps1"):
        text = read(name)
        assert "write-output $databaseurl" not in text
        assert "write-output $password" not in text
    assert "convertto-json" in read("backup-database.ps1")
