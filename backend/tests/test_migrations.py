import os
import subprocess
import sys

from sqlalchemy import create_engine, text


def test_upgrade_old_database_with_existing_rows(tmp_path):
    path = tmp_path / "old.db"
    env = {**os.environ, "ADMIN_TOKEN": "a" * 32, "ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
           "DATABASE_URL": f"sqlite:///{path}"}
    cmd = [sys.executable, "-m", "flask", "--app", "wsgi", "db"]
    subprocess.run([*cmd, "upgrade", "519aaa5d88d4"], env=env, check=True, capture_output=True)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO accounts (region,name,identifier,credential_encrypted,enabled,health,created_at) "
                          "VALUES ('cn','a','a',:credential,1,'unknown',CURRENT_TIMESTAMP)"), {"credential": b"cipher"})
        conn.execute(text("INSERT INTO api_keys (name,prefix,key_hash,enabled,created_at) "
                          "VALUES ('key','prefix','hash',1,CURRENT_TIMESTAMP)"))
    subprocess.run([*cmd, "upgrade"], env=env, check=True, capture_output=True)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT session_id, note, health FROM accounts")).one()
        assert len(row.session_id) == 36 and row.note == "" and row.health == "unknown"
        assert conn.execute(text("SELECT request_count FROM api_keys")).scalar_one() == 0
        schema = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='accounts'")).scalar_one()
        assert "region in ('cn', 'global')" in schema
    subprocess.run([*cmd, "downgrade", "519aaa5d88d4"], env=env, check=True, capture_output=True)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT identifier FROM accounts")).scalar_one() == "a"
        assert conn.execute(text("SELECT key_hash FROM api_keys")).scalar_one() == "hash"
    engine.dispose()
