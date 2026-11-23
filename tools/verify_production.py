"""Verify real, unmodified public URLs after cache expiry; never submit email."""
import argparse
import hashlib
import json
import time
import urllib.request
import urllib.error
from prepare_deploy import ROOT, PUBLIC

BASE = 'https://jalauris-solutions.fr'

def request(path, method='GET', data=None, headers=None):
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers=headers or {})
    try:
        response = urllib.request.urlopen(req, timeout=20)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, response.headers, response.read()

def verify():
    failures = []
    for name in PUBLIC:
        # Check both home URL variants: they have separate cache entries.
        for path in (['/', '/index.html'] if name == 'index.html' else ['/' + name]):
            code, headers, body = request(path)
            if code != 200 or hashlib.sha256(body).digest() != hashlib.sha256((ROOT / name).read_bytes()).digest():
                failures.append(f'{path}: unexpected status/content ({code})')
            if (headers.get('X-Content-Type-Options') != 'nosniff'
                    or headers.get('X-Frame-Options') != 'DENY'
                    or not headers.get('Content-Security-Policy')
                    or not headers.get('Referrer-Policy')
                    or not headers.get('Permissions-Policy')):
                failures.append(f'{path}: missing security header')
            if 'max-age=60' not in headers.get('Cache-Control', ''):
                failures.append(f'{path}: missing bounded cache policy')
    code, headers, body = request('/api/contact-config')
    config = json.loads(body)
    if code != 200 or config.get('configured') is not True or set(config) != {'configured', 'siteKey'} or 'no-store' not in headers.get('Cache-Control', ''):
        failures.append('contact-config: unexpected configuration/cache response')
    for path in ['/api/contact', '/api/contact.php']:
        code, headers, _ = request(path)
        if code != 405 or headers.get('Allow') != 'POST' or 'no-store' not in headers.get('Cache-Control', ''):
            failures.append(f'{path}: GET not safely rejected')
    code, _, _ = request('/api/contact', method='POST', data=b'{}', headers={'Content-Type': 'application/json'})
    if code != 400:
        failures.append('contact: invalid submission not rejected')
    code, _, _ = request('/audit-missing-page-2026.html')
    if code != 404:
        failures.append('missing page: expected 404')
    # Do not follow redirects: verify exact target and preserve path/query.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    for path in ['/', '/prestations-informatiques.html?audit=https']:
        try:
            response = opener.open('http://jalauris-solutions.fr' + path, timeout=20)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            if response.status != 301 or response.headers.get('Location') != BASE + path:
                failures.append(f'{path}: HTTP to HTTPS redirect missing/incorrect')
    return failures

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    while True:
        try:
            failures = verify()
        except (OSError, ValueError) as exc:
            failures = [f'HTTP verification unavailable: {type(exc).__name__}']
        if not failures:
            print('PASS: public files, cache, security headers, configuration and rejected submissions.')
            break
        print('\n'.join(failures), flush=True)
        if time.monotonic() >= deadline:
            raise SystemExit('Production verification failed; inspect before any further deployment.')
        time.sleep(15)
