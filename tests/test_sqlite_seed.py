import gzip
import sqlite3
from contextlib import closing

import pytest

from app.services.sqlite_seed import export_seed, restore_seed, split_seed


def test_export_removes_accounts_keeps_pending_and_preserves_original(tmp_path):
    original = tmp_path / 'original.sqlite'
    with sqlite3.connect(original) as db:
        for table in ('user', 'favorite_movie', 'favorite_series'):
            db.execute(f'CREATE TABLE {table} (id INTEGER)')
            db.execute(f'INSERT INTO {table} VALUES (1)')  # noqa: S608 - fixed table names
        db.execute('CREATE TABLE media_source (id INTEGER, match_status TEXT)')
        db.execute("INSERT INTO media_source VALUES (1, 'matched'), (2, 'pending')")
    archive = tmp_path / 'catalog.gz'
    assert export_seed(original, archive) == 2
    restored = tmp_path / 'restored.sqlite'
    assert restore_seed(archive, restored)
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT count(*) FROM user').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM media_source').fetchone()[0] == 2
        db.execute("INSERT INTO media_source VALUES (3,'matched')")
    assert not restore_seed(archive, restored)
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT count(*) FROM media_source').fetchone()[0] == 3
    with sqlite3.connect(original) as db:
        assert db.execute('SELECT count(*) FROM user').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM media_source').fetchone()[0] == 2


def test_absent_seed_does_not_create_database(tmp_path):
    destination = tmp_path / 'absent.sqlite'
    assert not restore_seed(tmp_path / 'missing.gz', destination)
    assert not destination.exists()


def test_split_catalog_restores_and_rejects_corrupt_or_missing_parts(tmp_path):
    original = tmp_path / 'original.sqlite'
    with closing(sqlite3.connect(original)) as db:
        db.execute('CREATE TABLE example (value TEXT)')
        db.execute("INSERT INTO example VALUES ('all data preserved')")
        db.commit()
    seed = tmp_path / 'seed.gz'
    with gzip.open(seed, 'wb') as stream:
        stream.write(original.read_bytes())
    split_seed(seed, chunk_size=30)
    seed.unlink()
    destination = tmp_path / 'restored.sqlite'
    assert restore_seed(seed, destination)
    with closing(sqlite3.connect(destination)) as db:
        assert db.execute('SELECT value FROM example').fetchone()[0] == 'all data preserved'
    first = tmp_path / 'seed.gz.part001'
    first.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='corrompida'):
        restore_seed(seed, tmp_path / 'broken.sqlite')
    assert not (tmp_path / 'broken.sqlite').exists()
    first.unlink()
    with pytest.raises(ValueError, match='ausente'):
        restore_seed(seed, tmp_path / 'missing.sqlite')
