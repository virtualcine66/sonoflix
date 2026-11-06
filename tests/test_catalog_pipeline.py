import json
from types import SimpleNamespace

import pytest

from scripts import complete_catalog


def test_pipeline_publishes_each_completed_stage_only(tmp_path, monkeypatch):
    monkeypatch.setattr(complete_catalog, '__file__', str(tmp_path / 'scripts' / 'complete_catalog.py'))
    monkeypatch.setattr(complete_catalog.shutil, 'which', lambda name: '/git')
    (tmp_path / 'deploy').mkdir()
    (tmp_path / 'deploy' / 'catalog.sqlite.gz.manifest.json').write_text(
        json.dumps({'parts': [{'name': 'catalog.sqlite.gz.part001'}]}), encoding='utf-8')
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1 if 'diff' in args else 0)

    monkeypatch.setattr(complete_catalog.subprocess, 'run', run)
    complete_catalog.run_pipeline(tmp_path / 'private.env', publish=True)
    assert sum('push' in call for call in calls) == 3
    assert sum('export-sqlite' in call for call in calls) == 3
    assert '--series-titles-first' in calls[0]
    assert json.loads((tmp_path / 'instance' / 'catalog-job.json').read_text())['state'] == 'complete'


def test_pipeline_stops_and_preserves_status_on_repeated_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(complete_catalog, '__file__', str(tmp_path / 'scripts' / 'complete_catalog.py'))
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(complete_catalog.subprocess, 'run', run)
    monkeypatch.setattr(complete_catalog.time, 'sleep', lambda seconds: None)
    with pytest.raises(RuntimeError):
        complete_catalog.run_pipeline(tmp_path / 'private.env')
    assert len(calls) == 3
    assert not any('export-sqlite' in call for call in calls)
    assert json.loads((tmp_path / 'instance' / 'catalog-job.json').read_text())['state'] == 'failed'
