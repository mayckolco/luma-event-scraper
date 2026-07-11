# PRD: Luma Event Scraper (Tech / AI)

**Autor:** —
**Fecha:** 11 de julio de 2026
**Estado:** Borrador
**Versión:** 1.0

---

## 1. Resumen

Un scraper automatizado que descubre diariamente eventos nuevos publicados en
Luma (lu.ma) dentro de las categorías **tech** y **ai**, y recopila el nombre
y link de cada evento para su posterior consumo (dashboard, newsletter,
notificación a un canal, etc.).

## 2. Problema / Motivación

Luma no ofrece una API pública oficial para terceros, ni un mecanismo nativo
de alertas por categoría/tema fuera de su propia newsletter semanal por
ciudad. Para alguien que quiere monitorear activamente el ecosistema de
eventos tech/AI (para asistir, promocionar, hacer research de comunidad,
generar leads, etc.), la única forma hoy es revisar manualmente la página de
Discover todos los días — lento y con alta probabilidad de perderse eventos.

## 3. Objetivo

Automatizar la detección de eventos nuevos de tech/AI en Luma, corriendo una
vez al día, sin depender de una API oficial ni de intervención manual.

## 4. Alcance

### 4.1 Dentro de alcance (v1)
- Consultar eventos de las categorías `tech` y `ai`.
- Cobertura multi-ciudad (lista configurable de coordenadas) para mitigar el
  sesgo geográfico del endpoint de descubrimiento.
- Deduplicación entre corridas (solo reportar eventos realmente nuevos).
- Persistencia de:
  - Estado de eventos ya vistos.
  - Historial acumulado de todos los eventos (CSV maestro).
  - Archivo diario con únicamente los eventos nuevos detectados.
- Ejecución programada 1 vez al día (cron o GitHub Actions).
- Manejo de errores con reintentos y backoff ante fallos de red.

### 4.2 Fuera de alcance (v1)
- Autenticación / scraping de listas de asistentes (requiere cookie de
  sesión — mayor complejidad legal y técnica).
- Notificaciones push automáticas (Slack/Telegram/email) — propuesto como v2.
- Enriquecimiento de datos de hosts (redes sociales, bios).
- Filtrado semántico por palabras clave o relevancia (más allá de la
  categoría nativa de Luma).
- UI / dashboard de visualización.
- Deduplicación semántica entre eventos con nombres similares mismo
  organizador (solo se deduplica por `api_id`).

## 5. Usuarios / Casos de uso

| Usuario | Caso de uso |
|---|---|
| Persona interesada en eventos tech/AI | Recibir un feed diario de eventos nuevos sin revisar Luma manualmente |
| Community manager / organizador | Detectar eventos de la competencia o del ecosistema para benchmarking |
| Equipo de growth / partnerships | Identificar eventos donde vale la pena tener presencia o patrocinar |

## 6. Requisitos funcionales

| ID | Requisito | Prioridad |
|---|---|---|
| RF-1 | El sistema debe consultar el endpoint de descubrimiento de Luma por cada combinación de categoría configurada (`tech`, `ai`) y ciudad configurada. | Alta |
| RF-2 | El sistema debe paginar automáticamente los resultados hasta agotar el listado o alcanzar un límite de seguridad de páginas. | Alta |
| RF-3 | El sistema debe identificar de forma única cada evento (`api_id`) para evitar duplicados entre corridas. | Alta |
| RF-4 | El sistema debe persistir en disco el conjunto de eventos ya vistos entre ejecuciones. | Alta |
| RF-5 | El sistema debe generar un archivo con únicamente los eventos nuevos detectados en la corrida actual, incluyendo como mínimo: nombre, link, fecha de inicio, ciudad, categoría. | Alta |
| RF-6 | El sistema debe mantener un historial acumulado (append-only) de todos los eventos detectados desde el inicio. | Media |
| RF-7 | El sistema debe poder ejecutarse de forma desatendida y programada (sin intervención manual) al menos una vez al día. | Alta |
| RF-8 | El sistema debe reintentar automáticamente ante fallos de red transitorios, con backoff progresivo. | Media |
| RF-9 | El sistema debe registrar (logging) cada corrida: cuántos eventos se consultaron, cuántos eran nuevos, y errores encontrados. | Media |
| RF-10 | La lista de ciudades y categorías a consultar debe ser configurable sin modificar la lógica central del script. | Media |

## 7. Requisitos no funcionales

| ID | Requisito |
|---|---|
| RNF-1 | **Sin dependencia de API oficial**: el sistema no debe requerir API key ni acceso autorizado por Luma. |
| RNF-2 | **Respetuoso con el servidor de destino**: pausas aleatorias entre requests, sin concurrencia agresiva. |
| RNF-3 | **Resiliencia ante cambios de esquema**: fallos en el parseo de un campo no deben tumbar toda la corrida; se debe loggear y continuar. |
| RNF-4 | **Portabilidad**: debe correr con Python estándar (sin dependencias externas obligatorias) para simplificar el despliegue en cron/CI. |
| RNF-5 | **Costo**: debe poder operar en un runner gratuito (ej. GitHub Actions free tier) sin necesidad de infraestructura paga. |
| RNF-6 | **Auditabilidad**: todo evento nuevo debe quedar trazado con la fecha en que fue detectado por primera vez (`first_seen`). |

## 8. Diseño de solución (alto nivel)

1. **Fuente de datos**: endpoint JSON no documentado que usa el propio
   frontend de Luma (`api.luma.com/discover/get-paginated-events`), consultado
   por `slug` de categoría + coordenadas.
2. **Orquestación**: script Python ejecutado por un scheduler externo
   (cron / GitHub Actions / systemd timer) — el script no mantiene estado en
   memoria entre corridas, todo el estado vive en archivos locales.
3. **Almacenamiento**:
   - `seen_events.json` — índice de deduplicación.
   - `events_master.csv` — historial completo.
   - `new_events_<fecha>.csv` — salida del día.
4. **Programación**: 1 corrida diaria (horario configurable).

## 9. Métricas de éxito

| Métrica | Meta v1 |
|---|---|
| Eventos nuevos detectados por semana | > 0 de forma consistente (validar que el pipeline funciona) |
| Tasa de error de corridas (fallos no recuperados) | < 5% de las ejecuciones programadas |
| Falsos duplicados (evento reportado como nuevo más de una vez) | 0 |
| Cobertura geográfica | Al menos 5 ciudades/regiones distintas consultadas por corrida |

## 10. Riesgos y consideraciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| El endpoint no documentado cambia de forma o deja de responder | Alto — el scraper deja de funcionar | Logging detallado + revisión manual periódica del payload crudo |
| Luma introduce medidas anti-bot (rate limiting, bloqueo de IP) | Medio | Pausas entre requests, evitar concurrencia, respetar backoff |
| Cambios en los Términos de Servicio de Luma que restrinjan este uso | Medio-Alto | Revisión legal antes de un uso comercial o a gran escala; no persistir datos de asistentes/PII |
| Sesgo geográfico del endpoint (resultados centrados en la coordenada consultada) | Bajo-Medio | Consultar múltiples ciudades; monitorear cobertura |

## 11. Roadmap futuro (fuera de v1)

- **v1.1**: Notificaciones automáticas (Slack/Telegram/email) cuando se detecten eventos nuevos.
- **v1.2**: Filtrado por palabras clave dentro del nombre/descripción del evento.
- **v2**: Enriquecimiento con datos de hosts (redes sociales) para lead-gen.
- **v2**: Dashboard simple (web) para visualizar el historial de eventos.

## 12. Preguntas abiertas

- ¿El uso previsto es personal/research o tiene un fin comercial (lead-gen, reventa de datos)? Esto determina qué tan riguroso debe ser el chequeo de Términos de Servicio de Luma.
- ¿Se necesita cobertura global o basta con ciudades específicas (ej. Lima + hubs tech principales)?
- ¿Se requiere alertamiento en tiempo real o basta con el reporte diario acumulado?