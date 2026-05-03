# Channels Auditor

Herramienta para auditar automáticamente los streams HLS listados en `channels.json`.

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

## Salida

El script genera estos archivos:
- `audit-report.json`
- `channels_clean.json`
- `channels_failed.json`

El archivo original `channels.json` no se modifica.

## Qué valida

- Usa `GET` con timeout de 10 segundos.
- Verifica que la respuesta contenga `#EXTM3U`.
- Si la playlist es un master playlist con `#EXT-X-STREAM-INF`, resuelve variantes relativas o absolutas y prueba cada variante.
- Si es un media playlist, valida que contenga `#EXTINF` o URLs de segmentos `.ts`, `.m4s` o `.mp4`.
- Usa concurrencia limitada a 20 hilos.
