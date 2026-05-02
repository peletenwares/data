import argparse
import concurrent.futures
import datetime
import json
import os
import shutil
import urllib.parse

import requests

HEADERS = {'User-Agent': 'Channels-Auditor/1.0'}
TIMEOUT = 10
MAX_WORKERS = 1
CHANNELS_FILE = 'channels.json'
AUDITED_FILE = 'channels_audited.json'
HISTORY_DIR = 'history'
REPORTS_DIR = 'reports'


def get_timestamp():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace(':', '-').replace('T', 'T')


def ensure_dirs():
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)


def backup_channels():
    timestamp = get_timestamp()
    backup_path = os.path.join(HISTORY_DIR, f'channels_{timestamp}_backup.json')
    shutil.copy2(CHANNELS_FILE, backup_path)
    return backup_path


def load_channels():
    if not os.path.exists(CHANNELS_FILE):
        return []
    with open(CHANNELS_FILE, 'r', encoding='utf-8') as source:
        return json.load(source)


def save_channels(channels, path):
    with open(path, 'w', encoding='utf-8') as output:
        json.dump(channels, output, indent=2, ensure_ascii=False)


def now_isoz():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat() + 'Z'


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
    result['lastCheckedAt'] = checked_at

    stream_url = channel.get('streamUrl')
    if not stream_url:
        result['auditStatus'] = 'inactive'
        result['lastAuditReason'] = 'streamUrl ausente'
        result['failCount'] = result.get('failCount', 0) + 1
        return result

    try:
        response = requests.get(stream_url, headers=HEADERS, timeout=TIMEOUT)
        if not 200 <= response.status_code < 300:
            result['auditStatus'] = 'inactive'
            result['lastAuditReason'] = f'HTTP {response.status_code}'
            result['failCount'] = result.get('failCount', 0) + 1
            return result

        manifest_text = response.text
        if '#EXTM3U' not in manifest_text:
            result['auditStatus'] = 'inactive'
            result['lastAuditReason'] = 'Respuesta no contiene #EXTM3U'
            result['failCount'] = result.get('failCount', 0) + 1
            return result

        # Simplified validation
        result['auditStatus'] = 'active'
        result['lastAuditReason'] = None
        result['failCount'] = 0
        return result
    except Exception as exc:
        result['auditStatus'] = 'inactive'
        result['lastAuditReason'] = str(exc)
        result['failCount'] = result.get('failCount', 0) + 1
        return result


def update_status_based_on_fail_count(channel):
    fail_count = channel.get('failCount', 0)
    if fail_count >= 3:
        channel['auditStatus'] = 'inactive'
    elif fail_count >= 1:
        channel['auditStatus'] = 'suspect'
    else:
        channel['auditStatus'] = 'active'
    return channel


def parse_args():
    parser = argparse.ArgumentParser(description='Auditor de canales HLS')
    parser.add_argument('--limit', type=int, default=0, help='Número máximo de canales a auditar')
    return parser.parse_args()


def main():
    args = parse_args()
    ensure_dirs()
    backup_path = backup_channels()
    print(f'Backup creado: {backup_path}')

    channels = load_channels()
    if args.limit and args.limit > 0:
        channels = channels[: args.limit]
    print(f'Iniciando auditoría de {len(channels)} canales...')

    audited = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(audit_channel, channel) for channel in channels]
        for future in concurrent.futures.as_completed(futures):
            audited.append(future.result())

    # Aplicar lógica de estados basada en failCount
    for channel in audited:
        update_status_based_on_fail_count(channel)

    # Filtrar working y failed
    working = [item for item in audited if item['auditStatus'] == 'active']
    failed = [item for item in audited if item['auditStatus'] in ('suspect', 'inactive')]

    # Guardar channels_audited.json
    save_channels(audited, AUDITED_FILE)

    # Guardar reportes con timestamp
    timestamp = get_timestamp()
    audit_report_path = os.path.join(REPORTS_DIR, f'audit_report_{timestamp}.json')
    failed_report_path = os.path.join(REPORTS_DIR, f'channels_failed_{timestamp}.json')
    working_report_path = os.path.join(REPORTS_DIR, f'channels_working_{timestamp}.json')

    save_channels(audited, audit_report_path)
    save_channels(failed, failed_report_path)
    save_channels(working, working_report_path)

    total = len(audited)
    active = len(working)
    suspect = len([c for c in audited if c['auditStatus'] == 'suspect'])
    inactive = len([c for c in audited if c['auditStatus'] == 'inactive'])
    percent_active = (active / total * 100) if total else 0.0

    print('Auditoría completada.')
    print(f'Total: {total}')
    print(f'Active: {active}')
    print(f'Suspect: {suspect}')
    print(f'Inactive: {inactive}')
    print(f'Porcentaje active: {percent_active:.2f}%')
    print(f'Archivos generados:')
    print(f'  {AUDITED_FILE} (para revisión manual)')
    print(f'  {audit_report_path}')
    print(f'  {failed_report_path}')
    print(f'  {working_report_path}')
    print(f'  {backup_path}')


if __name__ == '__main__':
    main()
