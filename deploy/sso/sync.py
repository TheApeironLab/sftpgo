"""Project eligible IAM identities into explicitly provisioned, scoped Files accounts.

Storage credentials and private/shared buckets are an operator-owned Secret; this
process cannot create IAM grants, buckets or cluster resources. Admin API is loopback.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(
    context=ssl.create_default_context(cafile='/etc/chentu-ca/ca.crt')))


def read(name, key):
    return (Path('/run/sso') / name / key).read_text().strip()


def http(url, body=None, token=None, basic=None, method=None, form=False):
    headers = {}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if basic:
        headers['Authorization'] = 'Basic ' + base64.b64encode(basic.encode()).decode()
    data = None
    if body is not None:
        data = (urllib.parse.urlencode(body) if form else json.dumps(body)).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    with opener.open(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=15) as response:
        data = response.read(4 * 1024 * 1024)
        return json.loads(data) if data else None


def directory():
    deadline = time.monotonic() + 120
    def request(*args, **kwargs):
        if time.monotonic() >= deadline:
            raise TimeoutError("directory snapshot exceeded its deadline")
        return http(*args, **kwargs)
    issuer = read('directory', 'issuer')
    token = request(issuer + '/protocol/openid-connect/token', {
        'grant_type': 'client_credentials', 'client_id': read('directory', 'client-id'),
        'client_secret': read('directory', 'client-secret')}, form=True)['access_token']
    base = issuer.replace('/realms/', '/admin/realms/')
    def scan():
        count = request(base + '/users/count', token=token)
        if not isinstance(count, int) or not 0 <= count <= 100000:
            raise ValueError('invalid directory size')
        users = []
        for first in range(0, count, 100):
            page = request(base + '/users?' + urllib.parse.urlencode({'first': first, 'max': 100, 'briefRepresentation': 'false'}), token=token)
            if len(page) != min(100, count - first):
                raise RuntimeError('incomplete directory')
            users.extend(page)
        if len({u['id'] for u in users}) != count or request(base + '/users/count', token=token) != count:
            raise RuntimeError('directory changed during scan')
        result = []
        for user in users:
            if not user.get('enabled') or user.get('serviceAccountClientId'):
                continue
            roles = {r['name'] for r in request(base + '/users/' + urllib.parse.quote(user['id'], safe='') + '/role-mappings/realm/composite', token=token)}
            if 'files-user' not in roles or user.get('attributes', {}).get('tenant') != [os.environ['SSO_TENANT']]:
                continue
            result.append({'sub': user['id'], 'admin': 'files-admin' in roles})
        return sorted(result, key=lambda u: u['sub'])
    first, second = scan(), scan()
    if first != second:
        raise RuntimeError('directory changed during scan')
    return second


def account(subject, personal, shared, credential):
    def filesystem(bucket):
        return {
            "provider": 1,
            "s3config": {
                "bucket": bucket,
                "region": os.environ.get("S3_REGION", "us-east-1"),
                "endpoint": os.environ["S3_ENDPOINT"],
                "force_path_style": True,
                "access_key": credential["accessKey"],
                "access_secret": {
                    "status": "Plain",
                    "payload": credential["secretKey"],
                },
            },
        }

    writable = [
        "list",
        "download",
        "upload",
        "overwrite",
        "delete",
        "create_dirs",
        "rename",
    ]
    return {
        "username": subject,
        "status": 1,
        "home_dir": f"/var/lib/sftpgo/homes/{subject}",
        "permissions": {"/": ["list"], "/我的文件": writable, "/团队文件": writable},
        # A read-only local landing directory holds only the two independent mounts.
        "filesystem": {"provider": 0},
        "filters": {"denied_protocols": ["SSH", "FTP", "DAV"]},
        "virtual_folders": [
            {
                "name": "files-" + kind + "-" + subject,
                "virtual_path": path,
                "mapped_path": f"/var/lib/sftpgo/{kind}/{subject}",
                "quota_size": -1,
                "quota_files": -1,
                "filesystem": filesystem(bucket),
            }
            for kind, path, bucket in (
                ("personal", "/我的文件", personal),
                ("team", "/团队文件", shared),
            )
        ],
    }


def sync():
    issuer = read('directory', 'issuer')
    marker = 'vasi.files:' + hashlib.sha256(issuer.encode()).hexdigest()
    state = Path('/var/lib/sftpgo/vasi-sso.json')
    identity = {'issuer': issuer, 'clientId': os.environ['SSO_CLIENT_ID']}
    if state.exists():
        if json.loads(state.read_text()) != identity:
            raise RuntimeError('refusing to rebind persisted accounts')
    else:
        temporary = state.with_suffix('.tmp')
        temporary.write_text(json.dumps(identity)); temporary.chmod(0o600); temporary.replace(state)
    declared = json.loads(read('storage', 'users.json'))
    shared = read('storage', 'shared-bucket')
    def bucket(value):
        if not isinstance(value, str) or not re.fullmatch(r'files-[a-z0-9][a-z0-9-]{0,55}[a-z0-9]', value):
            raise ValueError('Files requires explicitly scoped files- buckets')
        return value
    bucket(shared)
    subjects, buckets = set(), {shared}
    for user in declared:
        if (not re.fullmatch(r'[0-9a-f-]{36}', user['subject']) or user['subject'] in subjects
                or bucket(user['bucket']) in buckets or not user['credential'].get('accessKey')
                or not user['credential'].get('secretKey')):
            raise ValueError('invalid or ambiguous scoped storage declaration')
        subjects.add(user['subject']); buckets.add(user['bucket'])
    # Never infer eligibility from a partial or failed directory response.
    eligible = {u['sub'] for u in directory()}
    base = 'http://127.0.0.1:8081/api/v2'
    token = http(base + '/token', basic=read('admin', 'username') + ':' + read('admin', 'password'))['access_token']
    def api(path, body=None, method=None):
        return http(base + path, body=body, token=token, method=method)
    existing = []
    for offset in range(0, 100001, 100):
        page = api('/users?' + urllib.parse.urlencode({'offset': offset, 'limit': 100}))
        existing.extend(page)
        if len(page) < 100:
            break
    else:
        raise RuntimeError('application account pagination exceeded')
    owned = {u['username']: u for u in existing if u.get('description') == marker}
    names = {u['username'] for u in existing}
    wanted = {u['subject']: u for u in declared if u['subject'] in eligible}
    for subject, user in owned.items():
        if subject not in wanted:
            user['status'] = 0
            api('/users/' + subject, user, 'PUT')
    for subject, declaration in wanted.items():
        if subject in names and subject not in owned:
            raise RuntimeError('refusing to take over a foreign Files account')
        body = account(subject, declaration['bucket'], shared, declaration['credential'])
        body['description'] = marker
        for folder in body['virtual_folders']:
            # A new owned user cannot adopt a preexisting virtual folder.
            try:
                actual = api('/folders/' + folder['name'])
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                api('/folders', folder, 'POST')
            else:
                if subject not in owned:
                    raise RuntimeError('refusing to take over a foreign Files folder')
                api('/folders/' + folder['name'], folder, 'PUT')
        api('/users/' + subject if subject in owned else '/users', body, 'PUT' if subject in owned else 'POST')


if __name__ == '__main__':
    if sys.argv[1:] == ['ready']:
        try:
            fresh = time.time() - Path('/tmp/sso-ready').stat().st_mtime < 120
        except OSError:
            fresh = False
        sys.exit(0 if fresh else 1)
    while True:
        try:
            sync()
            Path('/tmp/sso-ready').touch()
        except Exception as error:
            Path('/tmp/sso-ready').unlink(missing_ok=True)
            print('Files SSO projection unavailable: ' + type(error).__name__, flush=True)
        time.sleep(10)
