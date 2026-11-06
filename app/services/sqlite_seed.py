"""Cópia inicial do catálogo para testes em armazenamento temporário."""
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path


def split_seed(seed, chunk_size=20_000_000):
    """Partes menores que o limite de upload web, com manifesto de integridade."""
    seed = Path(seed)
    parts = []
    with seed.open('rb') as source:
        while block := source.read(chunk_size):
            name = f'{seed.name}.part{len(parts) + 1:03d}'
            path = seed.with_name(name)
            path.write_bytes(block)
            parts.append({'name': name, 'size': len(block), 'sha256': hashlib.sha256(block).hexdigest()})
    manifest = seed.with_name(seed.name + '.manifest.json')
    manifest.write_text(json.dumps({'version': 1, 'parts': parts}, indent=2), encoding='utf-8')
    return manifest


@contextmanager
def compressed_seed(seed):
    manifest = seed.with_name(seed.name + '.manifest.json')
    if manifest.is_file():
        info = json.loads(manifest.read_text(encoding='utf-8'))
        if info.get('version') != 1 or not info.get('parts'):
            raise ValueError('Manifesto do catálogo inválido.')
        with tempfile.TemporaryFile() as assembled:
            for part in info['parts']:
                name = part['name']
                path = seed.with_name(name) if Path(name).name == name else None
                if path is None or path.resolve().parent != seed.parent.resolve() or not path.is_file():
                    raise ValueError('Uma parte do catálogo está ausente ou tem nome inválido.')
                digest, size = hashlib.sha256(), 0
                with path.open('rb') as stream:
                    while block := stream.read(1024 * 1024):
                        digest.update(block)
                        size += len(block)
                        assembled.write(block)
                if size != part['size'] or digest.hexdigest() != part['sha256']:
                    raise ValueError('Uma parte do catálogo está incompleta ou corrompida.')
            assembled.seek(0)
            with gzip.GzipFile(fileobj=assembled, mode='rb') as source:
                yield source
    else:
        with gzip.open(seed, 'rb') as source:
            yield source


def restore_seed(seed, destination):
    seed, destination = Path(seed), Path(destination)
    if destination.exists() or not (seed.is_file() or seed.with_name(seed.name + '.manifest.json').is_file()):
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=destination.parent, suffix='.sqlite')
    try:
        with os.fdopen(fd, 'wb') as target, compressed_seed(seed) as source:
            shutil.copyfileobj(source, target)
        with closing(sqlite3.connect(temporary)) as connection:
            if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('Cópia inicial SQLite inválida.')
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


def export_seed(database, output):
    """Snapshot consistente de todo o catálogo, sem contas de usuários."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        snapshot = Path(directory) / 'catalog.sqlite'
        source = sqlite3.connect(f'{Path(database).as_uri()}?mode=ro', uri=True)
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
            target.execute('DELETE FROM favorite_movie')
            target.execute('DELETE FROM favorite_series')
            target.execute('DELETE FROM user')
            target.commit()
            target.execute('VACUUM')
            count = target.execute('SELECT count(*) FROM media_source').fetchone()[0]
        finally:
            source.close()
            target.close()
        with snapshot.open('rb') as data, gzip.open(output, 'wb') as compressed:
            shutil.copyfileobj(data, compressed)
    return count
