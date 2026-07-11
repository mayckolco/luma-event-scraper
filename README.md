# Luma Event Scraper

Scraper diario de eventos **tech** y **ai** publicados en [Luma](https://lu.ma). Consulta el endpoint interno de descubrimiento, deduplica por `api_id` y genera CSVs con los eventos nuevos.

## Requisitos

- Python 3.10+
- Sin dependencias externas (solo stdlib)

## Uso

```bash
# Corrida completa: scrape + persistencia
python scraper.py

# Validar conectividad y parseo (sin escribir archivos)
python scraper.py --dry-run
```

## Archivos generados

| Archivo | Descripción |
|---|---|
| `seen_events.json` | Índice de deduplicación (`api_id` → `first_seen`) |
| `events_master.csv` | Historial acumulado de todos los eventos detectados |
| `new_events_<YYYY-MM-DD>.csv` | Solo eventos nuevos de la corrida del día |

### Campos del CSV

`name`, `url`, `start_date`, `city`, `category`, `first_seen`

## Configuración

Editar [`config.py`](config.py) sin tocar la lógica del scraper:

- `CATEGORIES` — slugs a consultar (default: `tech`, `ai`)
- `CITIES` — lista de `{name, lat, lon}` (mínimo 5 ciudades)
- `MAX_PAGES` — límite de seguridad por par categoría/ciudad
- `REQUEST_DELAY_MIN` / `REQUEST_DELAY_MAX` — pausa aleatoria entre requests
- `MAX_RETRIES` / `RETRY_BACKOFF_BASE` — reintentos ante fallos de red

## Automatización (GitHub Actions)

El workflow [`.github/workflows/scrape.yml`](.github/workflows/scrape.yml) ejecuta el scraper:

- **Cron:** `0 8 * * *` (08:00 UTC diario)
- **Manual:** Actions → Daily Luma Scrape → Run workflow
- **En push/PR:** job `validate` corre `--dry-run`

Los archivos de estado se commitean automáticamente al repo tras cada corrida programada.

## Mantenimiento

### Actualizar ciudades o categorías

1. Editar `config.py`
2. Correr `python scraper.py --dry-run` para validar
3. La siguiente corrida usará la nueva configuración

### Verificar que el pipeline funciona

```bash
python scraper.py --dry-run          # conectividad + parseo
python scraper.py                    # corrida completa
python scraper.py                    # segunda corrida → 0 duplicados falsos
```

### Monitorear una corrida

Al finalizar, el scraper imprime un resumen:

```
--- Resumen de corrida ---
Combinaciones exitosas: 12 / 12
Eventos consultados: ...
Eventos nuevos guardados: ...
Errores de parseo: ...
```

### Si el endpoint de Luma cambia

- Revisar logs con `Advertencias de esquema`
- Inspeccionar el payload crudo en los warnings de `extract_entries`
- Actualizar `parse_entry()` en `scraper.py` si cambió la estructura

## Documentación del proyecto

- [prd.md](prd.md) — especificación del producto
- [roadmap.md](roadmap.md) — plan de desarrollo y progreso
- [alcance.html](alcance.html) — vista visual del alcance
- [dashboard.html](dashboard.html) — dashboard interactivo de eventos

## Estructura

```
scraper.py          # Entry point y lógica principal
config.py           # Configuración editable
.github/workflows/  # CI/CD programado
```
