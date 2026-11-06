"""Processa o catálogo completo e publica snapshots ao terminar cada etapa."""
import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def run_pipeline(env_file, publish=False):
    root = Path(__file__).resolve().parents[1]
    status_path = root / 'instance' / 'catalog-job.json'
    status_path.parent.mkdir(exist_ok=True)
    base = [sys.executable, '-u', '-m', 'flask', '--env-file', str(env_file), '--app', 'run']
    git = shutil.which('git')
    if publish and not git:
        raise RuntimeError('Git não foi encontrado.')

    def status(stage, state, **extra):
        data = {'stage': stage, 'state': state, 'updated_at': datetime.now(UTC).isoformat(), **extra}
        status_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
        print(json.dumps(data), flush=True)

    def execute(args):
        for attempt in range(3):
            result = subprocess.run(args, cwd=root, check=False)  # noqa: S603 - fixed commands, no shell
            if result.returncode == 0:
                return
            if attempt < 2:
                print('Etapa interrompida; retomando em 30 segundos.', flush=True)
                time.sleep(30)
        raise RuntimeError('A etapa falhou após três tentativas; consulte catalog-complete.log.')

    stages = [
        ('series_titles', ['sources', 'sync-all', '--series-titles-first']),
        ('movies', ['sources', 'sync-all', '--kind', 'movie']),
        ('episodes', ['sources', 'sync-all', '--kind', 'series']),
    ]
    stage = 'starting'
    try:
        for stage, command in stages:
            status(stage, 'running')
            execute(base + command)
            status(stage, 'exporting')
            execute(base + ['sources', 'export-sqlite', 'deploy/catalog.sqlite.gz', '--split'])
            if publish:
                status(stage, 'publishing')
                manifest = root / 'deploy' / 'catalog.sqlite.gz.manifest.json'
                data = json.loads(manifest.read_text(encoding='utf-8'))
                paths = ['deploy/' + part['name'] for part in data['parts']]
                paths.append('deploy/catalog.sqlite.gz.manifest.json')
                execute([git, 'add', '--', *paths])
                changed = subprocess.run([git, 'diff', '--cached', '--quiet', '--', *paths], cwd=root)  # noqa: S603
                if changed.returncode == 1:
                    execute([git, 'commit', '-m', f'Atualiza metadados do catalogo: {stage}', '--', *paths])
                    execute([git, '-c', 'credential.interactive=false', 'push', 'origin', 'main'])
                elif changed.returncode != 0:
                    raise RuntimeError('Não foi possível verificar o snapshot no Git.')
        execute(base + ['sources', 'status'])
        status('finished', 'complete', note='Correspondências ambíguas permanecem para revisão.')
    except Exception:
        status(stage, 'failed', note='Progresso preservado; o mesmo comando retoma a fila.')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    run_pipeline(args.env_file.resolve(), args.publish)
