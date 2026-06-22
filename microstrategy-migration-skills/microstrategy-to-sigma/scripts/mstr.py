#!/usr/bin/env python3
"""Minimal MicroStrategy (Strategy One) REST client. Zero dependencies.

Usage: import mstr; s = mstr.Session(); s.get('/projects') ...

Credentials (in priority order):
  1. Environment: MSTR_BASE_URL, MSTR_USERNAME, MSTR_PASSWORD
     (+ optional MSTR_PROJECT_ID, MSTR_LOGIN_MODE — default 1 = standard)
  2. The agent-neutral cred file ~/.sigma-migration/env (lines of
     `export KEY="value"`), same pattern as the sibling sigma-migration-skills.

MSTR_BASE_URL is the Library root, e.g. https://<host>/MicroStrategyLibrary
(the client appends /api). Auth = POST /api/auth/login -> X-MSTR-AuthToken
header + session cookies; there is no API-key concept.
"""
import json
import os
import ssl
import urllib.error
import urllib.request

# Some MicroStrategy cloud-trial CA certs lack the key-usage extension;
# Python 3.13+ rejects them under VERIFY_X509_STRICT (on by default).
# curl accepts them — relax only the strictness flag, keep verification on.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

CRED_FILE = os.path.expanduser('~/.sigma-migration/env')


def _load_env():
    env = {}
    if os.path.exists(CRED_FILE):
        for line in open(CRED_FILE):
            line = line.strip()
            if line.startswith('export '):
                k, _, v = line[7:].partition('=')
                env[k] = v.strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k.startswith('MSTR_')})
    missing = [k for k in ('MSTR_BASE_URL', 'MSTR_USERNAME', 'MSTR_PASSWORD')
               if not env.get(k)]
    if missing:
        raise SystemExit(
            f'missing {", ".join(missing)} — export them or add them to '
            f'{CRED_FILE} (export KEY="value" lines)')
    return env


class Session:
    def __init__(self, project_id=None):
        e = _load_env()
        self.base = e['MSTR_BASE_URL'].rstrip('/') + '/api'
        self.project_id = project_id or e.get('MSTR_PROJECT_ID')
        self.cookies = {}
        self.token = None
        self.last_headers = {}
        self._login(e['MSTR_USERNAME'], e['MSTR_PASSWORD'],
                    int(e.get('MSTR_LOGIN_MODE', '1')))

    def _req(self, method, path, body=None, headers=None, raw=False):
        url = self.base + path
        h = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.token:
            h['X-MSTR-AuthToken'] = self.token
        if self.project_id:
            h['X-MSTR-ProjectID'] = self.project_id
        if self.cookies:
            h['Cookie'] = '; '.join(f'{k}={v}' for k, v in self.cookies.items())
        if headers:
            h.update(headers)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            resp = urllib.request.urlopen(req, context=_SSL_CTX)
        except urllib.error.HTTPError as err:
            detail = err.read().decode()[:2000]
            raise RuntimeError(f'{method} {path} -> {err.code}: {detail}') from None
        # Response headers, lowercased — instance-save flows need
        # x-mstr-ms-instance from a *creation response* header.
        self.last_headers = {k.lower(): v for k, v in resp.headers.items()}
        for sc in resp.headers.get_all('Set-Cookie') or []:
            kv = sc.split(';', 1)[0]
            k, _, v = kv.partition('=')
            self.cookies[k] = v
        tok = resp.headers.get('X-MSTR-AuthToken')
        if tok:
            self.token = tok
        text = resp.read().decode()
        if raw:
            return text
        return json.loads(text) if text else None

    def _login(self, user, pw, login_mode=1):
        self._req('POST', '/auth/login',
                  {'username': user, 'password': pw, 'loginMode': login_mode})

    def get(self, path, **kw):
        return self._req('GET', path, **kw)

    def post(self, path, body=None, **kw):
        return self._req('POST', path, body, **kw)

    def put(self, path, body=None, **kw):
        return self._req('PUT', path, body, **kw)

    def patch(self, path, body=None, **kw):
        return self._req('PATCH', path, body, **kw)

    def delete(self, path, **kw):
        return self._req('DELETE', path, **kw)

    # -- changeset helpers (schema edits require one; reports do NOT) --
    def changeset(self, schema_edit=True):
        r = self.post(f'/model/changesets?schemaEdit={"true" if schema_edit else "false"}')
        return r['id']

    def commit(self, cs_id):
        r = self.post(f'/model/changesets/{cs_id}/commit',
                      headers={'X-MSTR-MS-Changeset': cs_id})
        self.delete(f'/model/changesets/{cs_id}',
                    headers={'X-MSTR-MS-Changeset': cs_id})
        return r

    def cs_post(self, path, body, cs_id):
        return self.post(path, body, headers={'X-MSTR-MS-Changeset': cs_id})

    def abort(self, cs_id):
        """Delete a changeset (releases its schema lock)."""
        try:
            self.delete(f'/model/changesets/{cs_id}',
                        headers={'X-MSTR-MS-Changeset': cs_id})
        except Exception:
            pass

    def schema_edit(self, fn):
        """Run fn(cs_id) inside a schema changeset; commit on success,
        abort on failure so the schema lock is never left dangling.
        (A failed call inside an undeleted changeset leaves 'Schema editing
        is in use by another user' — clear via DELETE /api/model/schema/lock.)"""
        cs = self.changeset()
        try:
            result = fn(cs)
        except Exception:
            self.abort(cs)
            raise
        self.commit(cs)
        return result


if __name__ == '__main__':
    s = Session()
    print('token ok; projects:', [p['name'] for p in s.get('/projects')])
