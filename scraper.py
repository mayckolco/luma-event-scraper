#!/usr/bin/env python3
"""Luma Event Scraper — entry point."""

import argparse
import csv
import json
import logging
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import config

log = logging.getLogger("scraper")

LUMA_EVENT_BASE_URL = "https://lu.ma/"


@dataclass
class Event:
    api_id: str
    name: str
    url: str
    start_date: str
    city: str
    category: str


@dataclass
class RunStats:
    events_consulted: int = 0
    events_new: int = 0
    parse_errors: int = 0
    network_errors: int = 0
    pairs_succeeded: int = 0
    pairs_failed: int = 0
    retries: int = 0
    schema_warnings: int = 0


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def validate_config() -> None:
    if not config.CATEGORIES:
        raise ValueError("CATEGORIES no puede estar vacío")
    if len(config.CITIES) < 5:
        raise ValueError(f"Se requieren al menos 5 ciudades, hay {len(config.CITIES)}")
    for city in config.CITIES:
        for key in ("name", "lat", "lon"):
            if key not in city:
                raise ValueError(f"Ciudad incompleta (falta '{key}'): {city}")


def build_request_url(category: str, city: dict, cursor: str | None = None) -> str:
    params = {
        "slug": category,
        "latitude": city["lat"],
        "longitude": city["lon"],
    }
    if cursor:
        params["pagination_cursor"] = cursor
    return f"{config.API_BASE_URL}?{urllib.parse.urlencode(params)}"


def is_retryable_error(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (429, 500, 502, 503, 504)
    if isinstance(exc, urllib.error.URLError):
        return True
    return isinstance(exc, TimeoutError)


def fetch_page_once(category: str, city: dict, cursor: str | None = None) -> dict:
    url = build_request_url(category, city, cursor)
    request = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(request, timeout=config.REQUEST_TIMEOUT) as response:
        return json.loads(response.read().decode())


def fetch_page(
    category: str,
    city: dict,
    cursor: str | None = None,
    stats: RunStats | None = None,
) -> dict:
    """Consulta una página con reintentos y backoff exponencial (RF-8)."""
    for attempt in range(config.MAX_RETRIES + 1):
        try:
            return fetch_page_once(category, city, cursor)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            if not is_retryable_error(exc) or attempt >= config.MAX_RETRIES:
                if stats:
                    stats.network_errors += 1
                raise

            if stats:
                stats.retries += 1

            wait = config.RETRY_BACKOFF_BASE ** attempt + random.uniform(0, 1)
            log.warning(
                "Reintento %d/%d en %.1fs (%s / %s): %s",
                attempt + 1,
                config.MAX_RETRIES,
                wait,
                category,
                city["name"],
                exc,
            )
            time.sleep(wait)

    raise RuntimeError("fetch_page agotó reintentos sin respuesta")


def extract_entries(payload: dict, stats: RunStats | None = None) -> list:
    entries = payload.get("entries", payload.get("events"))
    if entries is None:
        if stats:
            stats.schema_warnings += 1
        log.warning(
            "Respuesta inesperada — claves: %s | payload: %s",
            list(payload.keys()),
            json.dumps(payload)[:500],
        )
        return []
    if not isinstance(entries, list):
        if stats:
            stats.schema_warnings += 1
        log.warning(
            "Campo de eventos no es una lista: %s | payload: %s",
            type(entries).__name__,
            json.dumps(payload)[:500],
        )
        return []
    return entries


def build_event_url(slug: str) -> str:
    if slug.startswith("http://") or slug.startswith("https://"):
        return slug
    return f"{LUMA_EVENT_BASE_URL}{slug.lstrip('/')}"


def parse_entry(entry: dict, category: str, city_name: str) -> Event | None:
    event_data = entry.get("event", entry)
    api_id = entry.get("api_id") or event_data.get("api_id")
    name = event_data.get("name")
    slug = event_data.get("url")
    start_date = event_data.get("start_at") or event_data.get("start_date")

    if not api_id:
        log.warning("Evento sin api_id, omitiendo: %s", json.dumps(entry)[:200])
        return None
    if not name or not slug or not start_date:
        log.warning("Evento %s con campos incompletos (name/url/start_date)", api_id)
        return None

    return Event(
        api_id=api_id,
        name=name,
        url=build_event_url(slug),
        start_date=start_date,
        city=city_name,
        category=category,
    )


def sleep_between_requests() -> None:
    delay = random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
    time.sleep(delay)


def scrape_pair(category: str, city: dict, stats: RunStats) -> list[Event]:
    """Consulta y pagina el endpoint para un par (categoría, ciudad)."""
    events: list[Event] = []
    cursor: str | None = None

    for page in range(1, config.MAX_PAGES + 1):
        payload = fetch_page(category, city, cursor, stats)
        entries = extract_entries(payload, stats)

        for entry in entries:
            try:
                event = parse_entry(entry, category, city["name"])
            except (KeyError, TypeError, AttributeError, ValueError) as exc:
                stats.parse_errors += 1
                log.warning("Error parseando evento: %s | entrada: %s", exc, json.dumps(entry)[:200])
                continue
            if event:
                events.append(event)

        log.info(
            "  página %d: %d entradas (%d parseadas acumuladas)",
            page,
            len(entries),
            len(events),
        )

        cursor = payload.get("next_cursor")
        has_more = payload.get("has_more", bool(cursor))
        if not cursor or not has_more:
            break

        sleep_between_requests()

    else:
        log.warning(
            "Límite de seguridad alcanzado (%d páginas) para %s / %s",
            config.MAX_PAGES,
            category,
            city["name"],
        )

    return events


def scrape_all(stats: RunStats) -> list[Event]:
    """Consulta todas las combinaciones categoría × ciudad con dedup en memoria."""
    pairs = [(cat, city) for cat in config.CATEGORIES for city in config.CITIES]
    seen_ids: set[str] = set()
    all_events: list[Event] = []

    for index, (category, city) in enumerate(pairs):
        log.info("Consultando %s / %s", category, city["name"])
        try:
            pair_events = scrape_pair(category, city, stats)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            stats.pairs_failed += 1
            log.error("Par %s / %s falló tras reintentos: %s", category, city["name"], exc)
            continue

        stats.pairs_succeeded += 1
        new_in_pair = 0
        for event in pair_events:
            if event.api_id in seen_ids:
                continue
            seen_ids.add(event.api_id)
            all_events.append(event)
            new_in_pair += 1

        log.info(
            "  %s / %s: %d eventos únicos en esta corrida",
            category,
            city["name"],
            new_in_pair,
        )

        if index < len(pairs) - 1:
            sleep_between_requests()

    stats.events_consulted = len(all_events)
    return all_events


def new_events_filepath(run_date: date | None = None) -> Path:
    run_date = run_date or date.today()
    filename = f"{config.NEW_EVENTS_FILE_PREFIX}{run_date.isoformat()}.csv"
    return Path(filename)


def load_seen_events() -> dict[str, str]:
    """Carga el índice de deduplicación: api_id → first_seen (RF-3, RF-4)."""
    path = Path(config.SEEN_EVENTS_FILE)
    if not path.exists():
        return {}

    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("No se pudo leer %s (%s), iniciando índice vacío", path, exc)
        return {}

    if isinstance(data, dict):
        return {str(key): str(value) for key, value in data.items()}
    if isinstance(data, list):
        return {api_id: "" for api_id in data}

    log.warning("Formato inesperado en %s, iniciando índice vacío", path)
    return {}


def save_seen_events(seen: dict[str, str]) -> None:
    path = Path(config.SEEN_EVENTS_FILE)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(seen, handle, indent=2, sort_keys=True)
        handle.write("\n")


def event_to_row(event: Event, first_seen: str) -> dict[str, str]:
    return {
        "name": event.name,
        "url": event.url,
        "start_date": event.start_date,
        "city": event.city,
        "category": event.category,
        "first_seen": first_seen,
    }


def append_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return

    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=config.CSV_FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def dedupe_events(events: list[Event]) -> list[Event]:
    seen_ids: set[str] = set()
    unique: list[Event] = []
    for event in events:
        if event.api_id in seen_ids:
            continue
        seen_ids.add(event.api_id)
        unique.append(event)
    return unique


def filter_new_events(events: list[Event], seen: dict[str, str]) -> list[Event]:
    return [event for event in events if event.api_id not in seen]


def persist_results(events: list[Event], run_date: date | None = None) -> tuple[int, int]:
    """
    Deduplica contra seen_events.json y escribe CSVs (RF-5, RF-6).
    Retorna (total_consultados, total_nuevos).
    """
    run_date = run_date or date.today()
    first_seen = run_date.isoformat()
    unique_events = dedupe_events(events)
    seen = load_seen_events()
    new_events = filter_new_events(unique_events, seen)

    if new_events:
        rows = [event_to_row(event, first_seen) for event in new_events]
        append_csv(Path(config.EVENTS_MASTER_FILE), rows)
        append_csv(new_events_filepath(run_date), rows)

        for event in new_events:
            seen[event.api_id] = first_seen

        save_seen_events(seen)

    return len(unique_events), len(new_events)


def log_run_summary(stats: RunStats) -> None:
    """Resumen estructurado de la corrida (RF-9)."""
    total_pairs = len(config.CATEGORIES) * len(config.CITIES)
    log.info("--- Resumen de corrida ---")
    log.info("Combinaciones exitosas: %d / %d", stats.pairs_succeeded, total_pairs)
    log.info("Eventos consultados: %d", stats.events_consulted)
    log.info("Eventos nuevos guardados: %d", stats.events_new)
    log.info("Errores de parseo: %d", stats.parse_errors)
    log.info("Errores de red: %d", stats.network_errors)
    log.info("Advertencias de esquema: %d", stats.schema_warnings)
    log.info("Reintentos de red: %d", stats.retries)
    if stats.pairs_failed:
        log.warning("Combinaciones fallidas: %d", stats.pairs_failed)


def dry_run() -> int:
    """Valida configuración y conectividad sin escribir archivos de salida."""
    validate_config()
    category = config.CATEGORIES[0]
    city = config.CITIES[0]

    log.info("Modo dry-run: validando conectividad con Luma")
    log.info("Configuración: %d categorías, %d ciudades", len(config.CATEGORIES), len(config.CITIES))
    log.info("Prueba: categoría=%s, ciudad=%s", category, city["name"])

    stats = RunStats()

    try:
        payload = fetch_page(category, city, stats=stats)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        log.error("Fallo de conectividad: %s", exc)
        return 1

    entries = extract_entries(payload, stats)
    log.info("Conectividad OK — respuesta con %d entradas", len(entries))

    if entries:
        try:
            sample = parse_entry(entries[0], category, city["name"])
            if sample:
                log.info("Parseo OK — ejemplo: %s (%s)", sample.name, sample.url)
        except (KeyError, TypeError, AttributeError) as exc:
            log.warning("Parseo de ejemplo falló: %s", exc)

    return 0


def run() -> int:
    """Ejecuta una corrida completa del scraper."""
    validate_config()
    stats = RunStats()

    log.info("Iniciando corrida — %d combinaciones (categoría × ciudad)",
             len(config.CATEGORIES) * len(config.CITIES))
    log.info("Categorías: %s", ", ".join(config.CATEGORIES))
    log.info("Ciudades: %s", ", ".join(c["name"] for c in config.CITIES))

    events = scrape_all(stats)
    total, new_count = persist_results(events)
    stats.events_consulted = total
    stats.events_new = new_count

    if new_count:
        log.info(
            "Archivos actualizados: %s, %s, %s",
            config.SEEN_EVENTS_FILE,
            config.EVENTS_MASTER_FILE,
            new_events_filepath(),
        )

    log_run_summary(stats)

    if stats.pairs_failed and stats.pairs_succeeded == 0:
        return 1
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scraper diario de eventos tech/AI en Luma (lu.ma)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validar configuración y conectividad sin escribir archivos de salida",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)

    log.info("Luma Event Scraper — %s", date.today().isoformat())

    try:
        if args.dry_run:
            return dry_run()
        return run()
    except ValueError as exc:
        log.error("Configuración inválida: %s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("Corrida interrumpida por el usuario")
        return 130


if __name__ == "__main__":
    sys.exit(main())
