import concurrent.futures
import datetime
import json
import urllib.parse

import requests

HEADERS = {'User-Agent': 'Channels-Auditor/1.0'}
TIMEOUT = 10
MAX_WORKERS = 20
OUTPUT_REPORT = 'audit-report.json'
OUTPUT_CLEAN = 'channels_clean.json'
OUTPUT_FAILED = 'channels_failed.json'


def load_channels(path='channels.json'):
    with open(path, 'r', encoding='utf-8') as source:
        return json.load(source)


def now_isoz():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def find_variant_uris(manifest_text):
    lines = [line.strip() for line in manifest_text.splitlines() if line.strip()]
    variant_uris = []
    for index, line in enumerate(lines):
        if line.startswith('#EXT-X-STREAM-INF'):
            for candidate in lines[index + 1:]:
                if not candidate.startswith('#'):
                    variant_uris.append(candidate)
                    break
    return variant_uris


def has_media_segments(manifest_text):
    lower_text = manifest_text.lower()
    if '#extinf' in lower_text:
        return True
    for ext in ('.ts', '.m4s', '.mp4'):
        for line in manifest_text.splitlines():
            candidate = line.strip()
            if not candidate or candidate.startswith('#'):
                continue
            if ext in candidate.lower():
                return True
    return False


def validate_hls_manifest(base_url, manifest_text, depth=0):
    if depth > 2:
        return False, 'Profundidad máxima de validación alcanzada'

    if '#EXTM3U' not in manifest_text:
        return False, 'Respuesta no contiene #EXTM3U'

    if '#EXT-X-STREAM-INF' in manifest_text:
        variant_uris = find_variant_uris(manifest_text)
        if not variant_uris:
            return False, 'Playlist maestro sin variantes válidas'

        errors = []
        for variant_uri in variant_uris:
            resolved_url = urllib.parse.urljoin(base_url, variant_uri)
            try:
                response = requests.get(resolved_url, headers=HEADERS, timeout=TIMEOUT)
                if not 200 <= response.status_code < 300:
                    errors.append(f'{resolved_url} HTTP {response.status_code}')
                    continue
                variant_text = response.text
                valid, reason = validate_hls_manifest(resolved_url, variant_text, depth + 1)
                if valid:
                    return True, None
                errors.append(f'{resolved_url} {reason}')
            except requests.RequestException as exc:
                errors.append(f'{resolved_url} {exc}')

        return False, 'Ninguna variante válida encontrada: ' + '; '.join(errors)

    if has_media_segments(manifest_text):
        return True, None

    return False, 'Playlist media inválida: falta #EXTINF o segmentos .ts/.m4s/.mp4'


def audit_channel(channel):
    checked_at = now_isoz()
    result = dict(channel)
    result['checkedAt'] = checked_at

    stream_url = channel.get('streamUrl')
    if not stream_url:
        result['auditStatus'] = 'failed'
        result['auditReason'] = 'streamUrl ausente'
        return result

    try:
        response = requests.get(stream_url, headers=HEADERS, timeout=TIMEOUT)
        if not 200 <= response.status_code < 300:
            result['auditStatus'] = 'failed'
            result['auditReason'] = f'HTTP {response.status_code}'
            return result

        manifest_text = response.text
        valid, reason = validate_hls_manifest(stream_url, manifest_text)
        if not valid:
            result['auditStatus'] = 'failed'
            result['auditReason'] = reason
            return result

        result['auditStatus'] = 'working'
        return result
    except requests.RequestException as exc:
        result['auditStatus'] = 'failed'
        result['auditReason'] = str(exc)
        return result
    except Exception as exc:
        result['auditStatus'] = 'failed'
        result['auditReason'] = f'Error de validación: {exc}'
        return result


def main():
    channels = load_channels()
    print(f'Iniciando auditoría de {len(channels)} canales...')

    audited = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(audit_channel, channel) for channel in channels]
        for future in concurrent.futures.as_completed(futures):
            audited.append(future.result())

    clean = [item for item in audited if item['auditStatus'] == 'working']
    failed = [item for item in audited if item['auditStatus'] != 'working']

    with open(OUTPUT_REPORT, 'w', encoding='utf-8') as output:
        json.dump(audited, output, indent=2, ensure_ascii=False)

    with open(OUTPUT_CLEAN, 'w', encoding='utf-8') as output:
        json.dump(clean, output, indent=2, ensure_ascii=False)

    with open(OUTPUT_FAILED, 'w', encoding='utf-8') as output:
        json.dump(failed, output, indent=2, ensure_ascii=False)

    total = len(audited)
    working = len(clean)
    failed_count = len(failed)
    percent = (working / total * 100) if total else 0.0

    print('Auditoría completada.')
    print(f'Total: {total}')
    print(f'Working: {working}')
    print(f'Failed: {failed_count}')
    print(f'Porcentaje working: {percent:.2f}%')
    print(f'Reportes generados: {OUTPUT_REPORT}, {OUTPUT_CLEAN}, {OUTPUT_FAILED}')


if __name__ == '__main__':
    main()
