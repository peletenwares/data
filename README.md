# Channels Auditor

Herramienta para auditar automáticamente los streams HLS listados en `channels.json`, preservando historial y evitando eliminaciones agresivas.

## Instalación

1. Asegúrate de tener Python instalado (versión 3.8 o superior).
2. Instala las dependencias:
   ```
   pip install -r requirements.txt
   ```

## Uso

Ejecuta el script de auditoría:
```
python auditor.py
```

## Flujo de Auditoría

- **`channels.json`** permanece como el archivo productivo principal (no se modifica automáticamente).
- Antes de auditar, se crea una copia histórica en `history/channels_<timestamp>_backup.json`.
- Se auditan todos los canales, manteniendo el estado anterior (`failCount`, etc.).
- Se actualizan campos: `auditStatus`, `lastCheckedAt`, `lastAuditReason`, `failCount`.
- Lógica de estados:
  - Si funciona: `auditStatus = "active"`, `failCount = 0`.
  - Si falla 1 vez: `auditStatus = "suspect"`.
  - Si falla 3 veces: `auditStatus = "inactive"`.
- No se eliminan canales; se marcan como `suspect` o `inactive`.
- Salida: `channels_audited.json` para revisión manual antes de reemplazar `channels.json`.

## Salida

El script genera estos archivos:
- **`channels_audited.json`**: Versión auditada para revisión manual (reemplaza `channels.json` si apruebas).
- **`reports/audit_report_<timestamp>.json`**: Reporte completo de la auditoría.
- **`reports/channels_failed_<timestamp>.json`**: Canales `suspect` o `inactive`.
- **`reports/channels_working_<timestamp>.json`**: Canales `active`.
- **`history/channels_<timestamp>_backup.json`**: Backup histórico de `channels.json`.

## Qué valida

- Usa `GET` con timeout de 10 segundos.
- Verifica que la respuesta contenga `#EXTM3U`.
- Si la playlist es un master playlist con `#EXT-X-STREAM-INF`, resuelve variantes relativas o absolutas y prueba cada variante.
- Si es un media playlist, valida que contenga `#EXTINF` o URLs de segmentos `.ts`, `.m4s` o `.mp4`.
- Usa concurrencia limitada a 20 hilos.

## Campos Agregados/Actualizados

- **`auditStatus`**: `"active"`, `"suspect"`, `"inactive"`.
- **`lastCheckedAt`**: Timestamp ISO de la última auditoría.
- **`lastAuditReason`**: Razón del último fallo (si aplica).
- **`failCount`**: Contador de fallos consecutivos.

Todos los campos originales se mantienen intactos.