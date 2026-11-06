"""Trabalho pesado executado localmente; o servidor gratuito só resolve sob demanda."""
import json
import time
from pathlib import Path

import click
from flask import current_app

from app.extensions import db
from app.models import utcnow
from app.services.m3u import entries, import_m3u
from app.services.source_matching import attach, match
from app.services.source_resolver import SourceError, probe
from app.services.tmdb import TMDbError
from app.source_models import MediaSource


def register_source_cli(app):
    @app.cli.group("sources")
    def sources():
        """Importar, revisar e verificar fontes privadas de reprodução."""

    @sources.command("build-catalog")
    def build_source_catalog():
        """Publica a lista inteira no catálogo local; TMDB é enriquecimento posterior."""
        from app.services.source_catalog import build_catalog

        result = build_catalog(progress=lambda count: click.echo(json.dumps(count)))
        click.echo(json.dumps(result))

    @sources.command("export-sqlite")
    @click.argument("output", type=click.Path(dir_okay=False))
    @click.option("--split", "split_output", is_flag=True, help="Divide para upload pelo navegador do GitHub.")
    def export_sqlite(output, split_output):
        """Exporta o catálogo completo para testes, excluindo contas de usuários."""
        from app.services.sqlite_seed import export_seed, split_seed

        if db.engine.dialect.name != "sqlite" or db.engine.url.database == ":memory:":
            raise click.ClickException("Este comando exige um arquivo SQLite local.")
        count = export_seed(Path(db.engine.url.database).resolve(), output)
        if split_output:
            split_seed(output)
            Path(output).unlink()
        else:
            # Não deixe um manifesto antigo prevalecer sobre uma exportação nova.
            Path(output + '.manifest.json').unlink(missing_ok=True)
        click.echo(f"Snapshot pronto: {count} fontes; sem contas de usuários.")

    @sources.command("status")
    def status_command():
        """Contagens da fila, sem exibir URLs ou credenciais."""
        from sqlalchemy import func

        from app.models import Episode, Movie, Series

        statuses = dict(db.session.execute(db.select(MediaSource.match_status, func.count())
                        .group_by(MediaSource.match_status)).all())
        counts = {model.__tablename__: db.session.scalar(db.select(func.count()).select_from(model))
                  for model in (Movie, Series, Episode)}
        click.echo(json.dumps({"sources": statuses, "catalog": counts}))

    @sources.command("sync-all")
    @click.option("--status", default="pending", type=click.Choice(["pending", "review", "error"]))
    @click.option("--limit", type=click.IntRange(1))
    @click.option("--kind", type=click.Choice(["movie", "series"]))
    @click.option("--series-titles-first", is_flag=True, help="Busca capas e sinopses de uma série por vez.")
    @click.option("--workers", default=8, type=click.IntRange(1, 32),
                  help="Consultas paralelas; gravação serial no SQLite.")
    def sync_all(status, limit, kind, series_titles_first, workers):
        """Processa toda a fila automaticamente; repetir retoma os pendentes."""
        from app.services.bulk_catalog import BatchClient, process_queue, process_series_titles

        config = current_app.config
        if not (config["TMDB_API_TOKEN"] or config["TMDB_API_KEY"]):
            raise click.ClickException("Configure a credencial TMDB no arquivo de ambiente local.")
        client = BatchClient(Path(current_app.instance_path) / "tmdb-batch-cache.db",
                             token=config["TMDB_API_TOKEN"], api_key=config["TMDB_API_KEY"],
                             language=config["TMDB_LANGUAGE"], region=config["TMDB_REGION"],
                             timeout=config["TMDB_TIMEOUT"])
        started = time.monotonic()
        try:
            def progress(counts):
                elapsed = time.monotonic() - started
                click.echo(json.dumps({**counts, 'elapsed_seconds': round(elapsed, 1),
                                       'items_per_minute': round(counts['processed'] * 60 / max(elapsed, 0.01), 1)}))
            if series_titles_first:
                process_series_titles(client, limit=limit, progress=progress, workers=workers)
            else:
                process_queue(client, status=status, limit=limit, kind=kind, progress=progress, workers=workers)
        except TMDbError as exc:
            db.session.rollback()
            raise click.ClickException(f"{exc} Execute novamente para retomar os pendentes.") from exc
        finally:
            client.close()

    @sources.command("preview")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False))
    @click.option("--encoding", default="utf-8-sig")
    @click.option("--limit", default=10, type=click.IntRange(1, 100))
    def preview(path, encoding, limit):
        """Mostra somente títulos e grupos, sem credenciais nem consultas de rede."""
        with open(path, encoding=encoding, errors="strict") as stream:
            for index, item in enumerate(entries(stream), 1):
                click.echo(json.dumps({"title": item["title"], "group": item["group"]}, ensure_ascii=False))
                if index >= limit:
                    break

    @sources.command("import-m3u")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False))
    @click.option("--encoding", default="utf-8-sig")
    @click.option("--limit", type=click.IntRange(1))
    @click.option("--group")
    def import_command(path, encoding, limit, group):
        """Importa em lotes de 500; executar novamente retoma sem duplicar URLs."""
        try:
            with open(path, encoding=encoding, errors="strict") as stream:
                totals = import_m3u(stream, limit=limit, group=group,
                                    progress=lambda n: click.echo(json.dumps(n)))
        except UnicodeError as exc:
            db.session.rollback()
            raise click.ClickException(
                "Codificação inválida. Tente --encoding cp1252; lotes anteriores foram preservados."
            ) from exc
        except ValueError as exc:
            db.session.rollback()
            raise click.ClickException(str(exc)) from exc
        click.echo(json.dumps(totals))

    @sources.command("enrich")
    @click.option("--limit", default=50, type=click.IntRange(1, 1000))
    @click.option("--status", default="pending", type=click.Choice(["pending", "error"]))
    def enrich(limit, status):
        """Busca TMDB em lote limitado. Ambiguidades ficam para revisão no painel."""
        client = current_app.extensions["tmdb"]
        if not client.configured:
            raise click.ClickException("Configure TMDB_API_TOKEN ou TMDB_API_KEY.")
        ids = list(db.session.scalars(db.select(MediaSource.id).where(
            MediaSource.match_status == status).order_by(MediaSource.id).limit(limit)))
        for source_id in ids:
            source = db.session.get(MediaSource, source_id)
            try:
                match(source, client)
            except TMDbError as exc:
                db.session.rollback()
                # Interrompe em falha de fornecedor; permanece pendente para retomada.
                raise click.ClickException(str(exc)) from exc
            except ValueError:
                db.session.rollback()
                source.match_status = "review"
                db.session.commit()
            click.echo(f"{source_id}: {source.match_status}")
            time.sleep(0.35)
            db.session.expunge_all()

    @sources.command("bind")
    @click.argument("source_id", type=int)
    @click.argument("tmdb_id", type=int)
    @click.option("--season", type=click.IntRange(0))
    @click.option("--episode", type=click.IntRange(1))
    def bind(source_id, tmdb_id, season, episode):
        """Associa explicitamente uma fonte a um ID do TMDB, após revisão."""
        source = db.session.get(MediaSource, source_id)
        if not source:
            raise click.ClickException("Fonte não encontrada.")
        if season is not None:
            source.season_number = season
        if episode is not None:
            source.episode_number = episode
        try:
            attach(source, tmdb_id, current_app.extensions["tmdb"])
        except (TMDbError, ValueError) as exc:
            db.session.rollback()
            raise click.ClickException(str(exc)) from exc
        click.echo("Fonte associada.")

    @sources.command("check")
    @click.argument("source_id", type=int)
    def check(source_id):
        """Sonda uma fonte: até 1 KiB do corpo, sem reproduzir nem baixar o filme."""
        source = db.session.get(MediaSource, source_id)
        if not source:
            raise click.ClickException("Fonte não encontrada.")
        hosts = {h.strip().lower() for h in current_app.config["SOURCE_ALLOWED_HOSTS"].split(",") if h.strip()}
        try:
            result = probe(source.get_url(), hosts)
            source.last_code = "ready"
            click.echo(json.dumps({k: v for k, v in result.items() if k != "url"}))
        except SourceError as exc:
            source.last_code = exc.code
            click.echo(str(exc))
            if exc.host:
                click.echo(f"Domínio a revisar em SOURCE_ALLOWED_HOSTS: {exc.host}")
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        source.checked_at = utcnow()
        db.session.commit()
