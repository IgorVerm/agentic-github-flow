#!/usr/bin/env python3
"""Audit a repository's locked dependencies against the OSV vulnerability database.

Usage: python3 audit_dependencies.py <repo> [--level info|low|moderate|high|critical]
                                          [--upgrades] [--no-npm] [--no-osv-scanner] [--reachability]
                                          [--offline <answers.json>] [--record <answers.json>] [--json]

The `review-security` and `check-web-deploy` skills run this. It is a thin client instead of an
installed scanner: the vulnerability data is OSV's (https://osv.dev, Google's open database that
also feeds osv-scanner, pip-audit and cargo-audit's RustSec mirror); the parsing and reporting are
here, with no dependency beyond Python 3. The skills ask the user before its first network call
in a repository, and a company overlay may forbid it.

What it reads: every lockfile under <repo> outside build and dependency folders:
`package-lock.json` (v1 to v3), `pnpm-lock.yaml`, `Cargo.lock`, `poetry.lock`, `uv.lock`,
`composer.lock`, and `requirements*.txt` and `requirements/*.txt` with `==` pins. Any other requirement in a requirements
file (`flask>=3`, a bare name, `==3.*`, a URL, a path, `-e`, a `-r` or `-c` include of a file
this run does not read itself) cannot be audited, because the installed version is unknown: it is
listed as `unaudited` with its file, line and reason, never skipped without a word, and it ranks
as moderate, like an advisory of unknown severity. Not seen: runtimes and platform packages
(Node itself, PHP itself, Homebrew, the OS), which have no lockfile here; the skills check those
against the vendor's supported-versions list by hand. Each package goes to OSV as name, ecosystem and version:
that is all that leaves the machine (POST https://api.osv.dev/v1/querybatch, then GET
/v1/vulns/<id> for each advisory found). Where a `package-lock.json` has npm beside it, `npm
audit --json` runs too, always against the public registry (`--registry=https://registry.npmjs.org/`,
so a `.npmrc` in the audited repository cannot redirect it; it sends the same kind of data) and
the two answers are compared, so a difference between the sources is visible instead of
silently trusted. `--no-npm` leaves it out.

Output, one line per advisory and package:
  <level>  <id>  <ecosystem>:<name>@<version>  direct|transitive[,dev]  fixed: <versions>  <lockfile>  <summary>
and one line per requirement that could not be audited:
  unaudited  <requirement>  <reason>  <requirements file>:<line>
Levels come from the advisory: GitHub's label when it has one, otherwise the CVSS 3.x base score
computed from the advisory's vector (none 0, low to 3.9, moderate to 6.9, high to 8.9, critical
above); an informational RustSec notice (unmaintained, unsound) is `info`; anything else is
`unknown` and ranks as moderate. One advisory known under several ids (GHSA, CVE, PYSEC, RUSTSEC)
is reported once per package, under its GHSA id when it has one. Exit 0 when nothing is at or above --level (default
high), 1 when something is, 2 on a usage, parse or network error: an audit that could not reach
its data is not a clean audit. A transitive finding is fixed through the direct dependency that
pulls it in (OWASP Vulnerable Dependency Management cheat sheet); suppress a finding only per
advisory id, with the reason on the issue, never by editing a version string.

`--upgrades` adds upgrade advice for what the repository actually uses, with no fixed list of
frameworks: every direct dependency in an npm or PyPI lockfile is looked up on its registry
(registry.npmjs.org, pypi.org: the package name is all that is sent) for its latest release, and
every direct dependency or runtime whose name endoflife.date tracks (next, react, node, python,
django, express, vue, angular, eslint, …; the runtime from `engines.node`, `.nvmrc`,
`.node-version`, `.python-version`) gets its release cycle's support status from
https://endoflife.date/api. Lines: `eol` (the cycle in use no longer receives fixes: ranks as
high), `major-behind` (a newer major exists: advice, ranks as low so the pre-deploy run at
`--level moderate` does not fail on it), `behind` (a newer minor or patch: info), `current`. Crates are not looked up on crates.io, whose crawler policy asks for contact
details in the User-Agent (`cargo update --dry-run` shows the same locally).

Second opinion: when `osv-scanner` is on PATH, it runs too, as `osv-scanner scan source -r
--no-resolve --all-packages --x-disable-plugins=directory --format json <repo>`, and its answer is
compared per package (its own lockfile parsers) and per advisory family (shared aliases are one
advisory), as with npm audit: the lines name what only one side found. The two flags keep what
leaves the machine to what this audit sends, package names and versions, to one host,
api.osv.dev: `--no-resolve` stops it resolving unpinned requirements through deps.dev, and
`--x-disable-plugins=directory` stops it sending file hashes of vendored folders (measured
2026-11-08). It still reads an unpinned requirement (`django>=3.0`) at its lower bound, which
this audit lists as unaudited, so its advisories there are for a version nobody pinned; and it
lists Rust workspace members, which this audit skips, as packages only it saw. Absent, failing,
an answer in an unexpected shape, or a release other than the pinned one: one line says so, and
this audit works as without it. Its answer never changes the exit code: this audit stays the
primary. `--reachability` adds `--call-analysis=rust`, on Linux only: what that builds and why it
needs Linux is in the review-security skill's `sources.md` (the osv-scanner row); it overwrites
the repository's `target/release`. Per advisory that names functions it reports whether one is
called: information, never a reason to suppress. `--no-osv-scanner` skips the second opinion.

`--record` saves the answers (osv-scanner's included) so a test can replay them with
`--offline`; `--json` prints the findings as JSON for other tools.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

OSV = 'https://api.osv.dev/v1'
NPM_REGISTRY = 'https://registry.npmjs.org/'
EOL = 'https://endoflife.date/api'
EOL_ALIASES = {'next': 'nextjs', 'node': 'nodejs', '@angular/core': 'angular', 'vue': 'vue', 'nuxt': 'nuxt'}
UNAUDITED_RANK = 'moderate'  # unknown risk, ranked like an advisory of unknown severity
UPGRADE_RANK = {'eol': 'high', 'major-behind': 'low', 'behind': 'info', 'current': 'info', 'unknown': 'info'}
LEVELS = ['info', 'low', 'moderate', 'high', 'critical']
SKIP_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'target', 'dist', 'build',
             '.next', '.turbo', '.cache', 'vendor', '.godot', 'DerivedData', 'site-packages'}
LOCKFILES = ('package-lock.json', 'pnpm-lock.yaml', 'Cargo.lock', 'poetry.lock', 'uv.lock', 'composer.lock')


class Package:
    __slots__ = ('ecosystem', 'name', 'version', 'direct', 'dev', 'lockfile')

    def __init__(self, ecosystem, name, version, direct, dev, lockfile):
        self.ecosystem, self.name, self.version = ecosystem, name, version
        self.direct, self.dev, self.lockfile = direct, dev, lockfile

    def key(self):
        return '%s:%s@%s' % (self.ecosystem, self.name, self.version)


# ---- lockfile parsers -------------------------------------------------------------------------

def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def read_lines(path):
    with open(path, encoding='utf-8') as f:
        return f.read().splitlines()


def parse_package_lock(path, rel):
    data = read_json(path)
    out = []
    if 'packages' in data:  # lockfile v2/v3
        root = data['packages'].get('', {})
        direct = set(root.get('dependencies', {})) | set(root.get('devDependencies', {})) | \
            set(root.get('optionalDependencies', {})) | set(root.get('peerDependencies', {}))
        for key, info in data['packages'].items():
            if not key or 'node_modules/' not in key or not info.get('version') or info.get('link'):
                continue
            name = key.rsplit('node_modules/', 1)[1]
            is_direct = key.count('node_modules/') == 1 and name in direct
            out.append(Package('npm', name, info['version'], is_direct, bool(info.get('dev')), rel))
    else:  # lockfile v1
        def walk(deps, depth):
            for name, info in deps.items():
                if info.get('version'):
                    out.append(Package('npm', name, info['version'], depth == 0, bool(info.get('dev')), rel))
                walk(info.get('dependencies', {}), depth + 1)
        walk(data.get('dependencies', {}), 0)
    return out


def parse_pnpm_lock(path, rel):
    out, section, importers_direct = [], None, set()
    for line in read_lines(path):
        if not line.startswith(' ') and line.rstrip().endswith(':'):
            section = line.strip()[:-1]
            continue
        if section == 'importers' and re.match(r'^      [^\s:]+:$', line):
            importers_direct.add(line.strip()[:-1].strip("'\""))
        if section in ('packages', 'snapshots') and re.match(r"^  ['\"]?/?@?[^\s]", line) and line.rstrip().endswith(':'):
            key = line.strip()[:-1].strip("'\"").lstrip('/')
            m = re.match(r'^(@?[^@(]+)@([^(:]+)', key)
            if m:
                name, version = m.group(1), m.group(2)
                if name and version and not version.startswith(('link', 'file', 'http', 'git')):
                    out.append(Package('npm', name, version, name in importers_direct, False, rel))
    seen, unique = set(), []
    for p in out:
        if p.key() not in seen:
            seen.add(p.key()); unique.append(p)
    return unique


def parse_toml_packages(path, rel, ecosystem, skip_without_source):
    out, block = [], {}
    def flush():
        if block.get('name') and block.get('version'):
            if not (skip_without_source and 'source' not in block):
                source = block.get('source', '')
                if not re.search(r'editable|virtual|path\+|directory', source):
                    out.append(Package(ecosystem, block['name'], block['version'], False, False, rel))
    for line in read_lines(path):
        s = line.strip()
        if s == '[[package]]':
            flush(); block = {}
        else:
            m = re.match(r'^(name|version|source)\s*=\s*(.+)$', s)
            if m:
                block[m.group(1)] = m.group(2).strip().strip('"')
    flush()
    return out


def parse_composer_lock(path, rel):
    data = read_json(path)
    out = []
    for section, dev in (('packages', False), ('packages-dev', True)):
        for info in data.get(section, []):
            if info.get('name') and info.get('version'):
                out.append(Package('Packagist', info['name'], info['version'].lstrip('vV'), True, dev, rel))
    return out


# pip options that change where or how packages come from, not which ones: no package to audit.
REQUIREMENT_OPTIONS = ('-i', '--index-url', '--extra-index-url', '--no-index', '-f', '--find-links',
                       '--trusted-host', '--pre', '--prefer-binary', '--only-binary', '--no-binary',
                       '--require-hashes', '--hash', '--use-feature', '--config-settings')


def requirement_lines(path):
    """(line number, text) per logical line: comments cut, `\\` continuations joined (pip-compile
    puts each `--hash` on a continuation line)."""
    out, buf, start = [], '', 0
    for n, line in enumerate(read_lines(path), 1):
        s = re.split(r'(?:^|\s)#', line, maxsplit=1)[0].rstrip()
        if not buf:
            start = n
        if s.endswith('\\'):
            buf += s[:-1] + ' '
            continue
        text = (buf + s).strip()
        buf = ''
        if text:
            out.append((start, text))
    if buf.strip():
        out.append((start, buf.strip()))
    return out


ARCHIVE_SUFFIXES = ('.whl', '.tar.gz', '.tgz', '.zip', '.tar.bz2')


def parse_requirements(path, rel, unaudited=None, audited=None):
    """The `==` pins of a requirements file. Every other requirement is a package the audit cannot
    vouch for; it goes to `unaudited` as {lockfile, line, requirement, reason} instead of being
    skipped without a word. A `-r` or `-c` include counts as audited only when the file
    it names, resolved from this file's folder, is in `audited` (the real paths of the files this
    run reads); any other include is named."""
    out = []

    def skip(n, requirement, reason):
        if unaudited is not None:
            unaudited.append({'lockfile': rel, 'line': n, 'requirement': requirement, 'reason': reason})

    for n, text in requirement_lines(path):
        first = text.split()[0]
        if first.startswith('-'):
            if '=' in first:
                opt, arg = first.split('=', 1)
            elif not first.startswith('--') and len(first) > 2:  # -rbase.txt, -efoo: pip's glued form
                opt, arg = first[:2], first[2:]
            else:
                opt, arg = first, text[len(first):].strip()
            arg = arg.split()[0] if arg.split() else ''
            if opt in ('-r', '--requirement', '-c', '--constraint'):
                if '://' in arg:
                    skip(n, text, 'remote include: the file it names is not read')
                elif not arg or audited is None or \
                        os.path.realpath(os.path.join(os.path.dirname(path), arg)) not in audited:
                    skip(n, text, 'included file not read: not among the files this audit reads')
            elif opt in ('-e', '--editable'):
                skip(n, text, 'editable or local requirement: no registry version to audit')
            elif opt not in REQUIREMENT_OPTIONS:
                skip(n, text, 'unknown option')
            continue
        req = text.split(';', 1)[0].strip()
        m = re.match(r'^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$', req)
        head = req.split('@', 1)[0]
        if not m or req.startswith(('.', '/', '~', 'file:')) or '://' in head or '/' in head or \
                '\\' in head or head.strip().lower().endswith(ARCHIVE_SUFFIXES):
            skip(n, text, 'URL or path: no registry version to audit')
            continue
        name, spec = m.group(1), m.group(2).strip()
        pin = re.match(r'^==\s*([^\s,;#]+)(?:\s+--hash(?:=|\s+)\S+)*\s*$', spec)
        if spec.startswith('@'):
            skip(n, name, 'direct URL: no registry version to audit')
        elif not spec:
            skip(n, name, 'no version: any release may be installed')
        elif pin and '*' not in pin.group(1) and not spec.startswith('==='):
            out.append(Package('PyPI', name, pin.group(1), True, False, rel))
        else:
            skip(n, name + spec.split(' --hash', 1)[0], 'not pinned with ==: the installed version is unknown')
    return out


def find_lockfiles(repo):
    """Lockfiles and requirements files: `requirements*.txt`, and every `.txt` directly in a folder
    named `requirements` (the `requirements/base.txt` layout)."""
    found = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.'))
        in_requirements_folder = os.path.basename(root) == 'requirements'
        for n in sorted(names):
            if n in LOCKFILES or (n.endswith('.txt') and (n.startswith('requirements') or in_requirements_folder)):
                found.append(os.path.join(root, n))
    return found


def parse_lockfile(path, repo, unaudited=None, audited=None):
    rel = os.path.relpath(path, repo).replace(os.sep, '/')
    name = os.path.basename(path)
    if name == 'package-lock.json':
        return parse_package_lock(path, rel)
    if name == 'pnpm-lock.yaml':
        return parse_pnpm_lock(path, rel)
    if name == 'Cargo.lock':
        return parse_toml_packages(path, rel, 'crates.io', skip_without_source=True)
    if name in ('poetry.lock', 'uv.lock'):
        return parse_toml_packages(path, rel, 'PyPI', skip_without_source=False)
    if name == 'composer.lock':
        return parse_composer_lock(path, rel)
    return parse_requirements(path, rel, unaudited, audited)


# ---- OSV clients -----------------------------------------------------------------------------

SYSTEM_CA_BUNDLES = ('/etc/ssl/cert.pem', '/etc/ssl/certs/ca-certificates.crt',
                     '/etc/pki/tls/certs/ca-bundle.crt')


def ssl_context():
    """A verifying TLS context. A python.org build on macOS ships no certificate bundle until its
    Install Certificates command is run; then the system bundle is used. Verification is never
    turned off."""
    ctx = ssl.create_default_context()
    paths = ssl.get_default_verify_paths()
    have = (paths.cafile and os.path.exists(paths.cafile)) or os.path.exists(paths.openssl_cafile or '') \
        or os.path.isdir(paths.openssl_capath or '') and os.listdir(paths.openssl_capath)
    if not have:
        for bundle in SYSTEM_CA_BUNDLES:
            if os.path.exists(bundle):
                ctx.load_verify_locations(bundle)
                break
    return ctx


class Online:
    def __init__(self, record_to=None):
        self.record_to = record_to
        self.answers = {'queries': {}, 'vulns': {}}
        self.ctx = ssl_context()

    def _call(self, url, body=None):
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                     headers={'Content-Type': 'application/json'} if body else {})
        try:
            with urllib.request.urlopen(req, timeout=60, context=self.ctx) as r:
                return json.load(r)
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
            # HTTPException: a reply cut off mid-body (IncompleteRead, measured 2026-11-08 through
            # the sandbox proxy) is a network error (exit 2), not a crash that exits 1 like a finding
            hint = ''
            if 'CERTIFICATE_VERIFY_FAILED' in str(exc):
                hint = ' (this Python has no certificate bundle: run its Install Certificates command, use the system Python, or set SSL_CERT_FILE)'
            raise RuntimeError('OSV %s: %s%s' % (url.replace(OSV, ''), exc, hint))

    def ids_for(self, packages):
        result = {}
        for start in range(0, len(packages), 1000):
            chunk = packages[start:start + 1000]
            body = {'queries': [{'package': {'name': p.name, 'ecosystem': p.ecosystem}, 'version': p.version}
                                for p in chunk]}
            answer = self._call(OSV + '/querybatch', body)
            for p, r in zip(chunk, answer.get('results', [])):
                ids = [v['id'] for v in r.get('vulns', [])]
                result[p.key()] = ids
                self.answers['queries'][p.key()] = ids
        return result

    def vuln(self, vid):
        record = self._call(OSV + '/vulns/' + vid)
        self.answers['vulns'][vid] = record
        return record

    def latest(self, package):
        """The latest release on the package's registry, or None when it has no lookup here."""
        if package.ecosystem == 'npm':
            url = 'https://registry.npmjs.org/' + package.name.replace('/', '%2F')
            pick = lambda d: (d.get('dist-tags') or {}).get('latest')
        elif package.ecosystem == 'PyPI':
            url = 'https://pypi.org/pypi/%s/json' % package.name
            pick = lambda d: (d.get('info') or {}).get('version')
        else:
            return None
        try:
            version = pick(self._call(url))
        except RuntimeError:
            version = None
        self.answers.setdefault('latest', {})[package.key()] = version
        return version

    def eol_products(self):
        products = self._call(EOL + '/all.json')
        self.answers['eol_products'] = products
        return products

    def eol_cycles(self, product):
        cycles = self._call(EOL + '/%s.json' % product)
        self.answers.setdefault('eol', {})[product] = cycles
        return cycles

    def osv_scanner(self, repo, reachability):
        answer = run_osv_scanner(repo, reachability)
        self.answers['osv_scanner'] = answer
        return answer

    def close(self):
        if self.record_to:
            with open(self.record_to, 'w', encoding='utf-8') as f:
                json.dump(self.answers, f, indent=1, sort_keys=True)


class Offline:
    def __init__(self, path):
        self.answers = read_json(path)

    def ids_for(self, packages):
        return {p.key(): self.answers['queries'].get(p.key(), []) for p in packages}

    def vuln(self, vid):
        return self.answers['vulns'][vid]

    def latest(self, package):
        return self.answers.get('latest', {}).get(package.key())

    def eol_products(self):
        return self.answers.get('eol_products', [])

    def eol_cycles(self, product):
        return self.answers.get('eol', {}).get(product, [])

    def osv_scanner(self, repo, reachability):
        return self.answers.get('osv_scanner') or {'problem': 'not in the recorded answers'}

    def close(self):
        pass


# ---- findings --------------------------------------------------------------------------------

CVSS3 = {'AV': {'N': 0.85, 'A': 0.62, 'L': 0.55, 'P': 0.2}, 'AC': {'L': 0.77, 'H': 0.44},
         'UI': {'N': 0.85, 'R': 0.62}, 'C': {'H': 0.56, 'L': 0.22, 'N': 0.0},
         'I': {'H': 0.56, 'L': 0.22, 'N': 0.0}, 'A': {'H': 0.56, 'L': 0.22, 'N': 0.0}}


def cvss3_base_score(vector):
    """The CVSS 3.0/3.1 base score of a vector string (FIRST's specification), or None."""
    try:
        parts = dict(p.split(':') for p in vector.split('/')[1:])
        scope_changed = parts['S'] == 'C'
        pr = {'N': 0.85, 'L': 0.68 if scope_changed else 0.62, 'H': 0.5 if scope_changed else 0.27}[parts['PR']]
        iss = 1 - (1 - CVSS3['C'][parts['C']]) * (1 - CVSS3['I'][parts['I']]) * (1 - CVSS3['A'][parts['A']])
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if scope_changed else 6.42 * iss
        exploit = 8.22 * CVSS3['AV'][parts['AV']] * CVSS3['AC'][parts['AC']] * pr * CVSS3['UI'][parts['UI']]
    except (KeyError, ValueError):
        return None
    if impact <= 0:
        return 0.0
    raw = min(1.08 * (impact + exploit), 10) if scope_changed else min(impact + exploit, 10)
    return __import__('math').ceil(raw * 10 - 1e-9) / 10  # round up to one decimal


def level_from_score(score):
    if score == 0:
        return 'info'
    if score < 4:
        return 'low'
    if score < 7:
        return 'moderate'
    if score < 9:
        return 'high'
    return 'critical'


def level_of(record):
    sev = (record.get('database_specific') or {}).get('severity')
    if isinstance(sev, str) and sev.lower() in LEVELS:
        return sev.lower()
    for entry in record.get('affected', []):
        for spec in (entry.get('ecosystem_specific') or {}, entry.get('database_specific') or {}):
            sev = spec.get('severity')
            if isinstance(sev, str) and sev.lower() in LEVELS:
                return sev.lower()
            if spec.get('informational'):
                return 'info'
    for entry in record.get('severity', []) or []:
        if entry.get('type') == 'CVSS_V3':
            score = cvss3_base_score(entry.get('score', ''))
            if score is not None:
                return level_from_score(score)
    return 'unknown'


def rank(level):
    return LEVELS.index('moderate') if level == 'unknown' else LEVELS.index(level)



def fixed_versions(record, package):
    fixed = []
    for entry in record.get('affected', []):
        pkg = entry.get('package', {})
        if pkg.get('name', '').lower() != package.name.lower() or pkg.get('ecosystem') != package.ecosystem:
            continue
        for rng in entry.get('ranges', []):
            for ev in rng.get('events', []):
                if 'fixed' in ev and ev['fixed'] not in fixed:
                    fixed.append(ev['fixed'])
    return fixed


def preferred_id(ids):
    """One id for an advisory family: GHSA first, then CVE, then the rest alphabetically."""
    order = {'GHSA': 0, 'CVE': 1}
    return sorted(ids, key=lambda i: (order.get(i.split('-')[0], 2), i))[0]


def audit(packages, client):
    unique = {}
    for p in packages:
        unique.setdefault(p.key(), p)
    ids = client.ids_for(list(unique.values()))
    wanted = sorted({vid for vids in ids.values() for vid in vids})
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = dict(zip(wanted, pool.map(client.vuln, wanted)))
    findings = []
    for key, vids in ids.items():
        p = unique[key]
        families = [{vid, *(records[vid].get('aliases') or [])} for vid in vids]
        merged = True  # advisories sharing an alias are one finding, whatever order the ids came in
        while merged:
            merged = False
            for i in range(len(families)):
                for j in range(i + 1, len(families)):
                    if families[i] & families[j]:
                        families[i] |= families.pop(j)
                        merged = True
                        break
                if merged:
                    break
        for fam in families:
            members = [v for v in vids if v in fam]
            vid = preferred_id(members)
            rec = records[vid]
            level = max((level_of(records[m]) for m in members), key=rank)
            findings.append({
                'level': level, 'id': vid, 'aliases': sorted(fam - {vid}),
                'ecosystem': p.ecosystem, 'name': p.name, 'version': p.version,
                'direct': p.direct, 'dev': p.dev, 'lockfile': p.lockfile,
                'fixed': fixed_versions(rec, p) or [f for m in members for f in fixed_versions(records[m], p)],
                'summary': (rec.get('summary') or rec.get('details') or '').strip().split('\n')[0][:120],
            })
    findings.sort(key=lambda f: (-rank(f['level']), f['ecosystem'], f['name'], f['id']))
    return findings


# ---- upgrades ----------------------------------------------------------------------------------

def version_tuple(version):
    nums = re.findall(r'\d+', version.split('-')[0].split('+')[0])
    return tuple(int(n) for n in nums[:3]) if nums else ()


def runtimes(repo):
    """Runtime versions the repository pins: (product, version, where)."""
    found = []
    pkg = os.path.join(repo, 'package.json')
    if os.path.isfile(pkg):
        try:
            node = (read_json(pkg).get('engines') or {}).get('node', '')
        except ValueError:
            node = ''
        m = re.search(r'\d+(?:\.\d+)*', node or '')
        if m:
            found.append(('nodejs', m.group(0), 'package.json engines.node'))
    for name, product in (('.nvmrc', 'nodejs'), ('.node-version', 'nodejs'), ('.python-version', 'python')):
        path = os.path.join(repo, name)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                m = re.search(r'\d+(?:\.\d+)*', f.read())
            if m:
                found.append((product, m.group(0), name))
    return found


def cycle_for(cycles, version):
    """The endoflife.date cycle a version belongs to: the longest cycle name that prefixes it."""
    parts = version_tuple(version)
    best = None
    for c in cycles:
        name = str(c.get('cycle', ''))
        cparts = version_tuple(name)
        if cparts and parts[:len(cparts)] == cparts and (best is None or len(cparts) > len(version_tuple(str(best['cycle'])))):
            best = c
    return best


def support_status(cycle, today):
    if cycle is None:
        return 'unknown', ''
    eol = cycle.get('eol')
    if eol is True or (isinstance(eol, str) and eol <= today):
        return 'eol', 'support ended %s' % eol
    if eol is False or eol is None:
        return 'supported', 'supported, no end date' + (' (LTS)' if cycle.get('lts') else '')
    return 'supported', 'supported until %s' % eol


def upgrades(packages, runtime_pins, client, today):
    """Upgrade advice for direct dependencies and pinned runtimes; see the module docstring."""
    direct = {}
    for p in packages:
        if p.direct and p.ecosystem in ('npm', 'PyPI'):
            direct.setdefault(p.key(), p)
    products = set(client.eol_products())
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        latest = dict(zip(direct, pool.map(client.latest, direct.values())))
    cycles_cache = {}

    def cycles(product):
        if product not in cycles_cache:
            cycles_cache[product] = client.eol_cycles(product)
        return cycles_cache[product]

    rows = []
    for key, p in direct.items():
        new = latest.get(key)
        cur, new_t = version_tuple(p.version), version_tuple(new or '')
        if not new_t:
            state = 'unknown'
        elif new_t[0] > cur[0]:
            state = 'major-behind'
        elif new_t > cur:
            state = 'behind'
        else:
            state = 'current'
        product = EOL_ALIASES.get(p.name, p.name.lower())
        support, note = ('', '')
        if product in products:
            support, note = support_status(cycle_for(cycles(product), p.version), today)
            if support == 'eol':
                state = 'eol'
        rows.append({'kind': 'package', 'state': state, 'ecosystem': p.ecosystem, 'name': p.name,
                     'version': p.version, 'latest': new, 'note': note, 'lockfile': p.lockfile, 'dev': p.dev})
    for product, version, where in runtime_pins:
        if product in products:
            support, note = support_status(cycle_for(cycles(product), version), today)
            state = 'eol' if support == 'eol' else ('current' if support == 'supported' else 'unknown')
        else:
            state, note = 'unknown', ''
        rows.append({'kind': 'runtime', 'state': state, 'ecosystem': 'runtime', 'name': product,
                     'version': version, 'latest': None, 'note': note, 'lockfile': where, 'dev': False})
    order = {'eol': 0, 'major-behind': 1, 'behind': 2, 'unknown': 3, 'current': 4}
    rows.sort(key=lambda r: (order[r['state']], r['ecosystem'], r['name']))
    return rows


def npm_audit(directory):
    """GHSA ids and severities from `npm audit --json`, or None when npm is absent or fails."""
    if not shutil.which('npm'):
        return None, 'npm not on PATH'
    try:
        # the public registry, whatever a .npmrc in the audited repository names
        r = subprocess.run(['npm', 'audit', '--json', '--no-fund', '--registry=' + NPM_REGISTRY],
                           cwd=directory, capture_output=True, text=True, timeout=180)
        data = json.loads(r.stdout or '{}')
    except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
        return None, 'npm audit failed: %s' % type(exc).__name__
    if 'vulnerabilities' not in data:
        return None, 'npm audit gave no report (%s)' % (data.get('error', {}).get('code') or 'no output')
    found = {}
    for name, v in data['vulnerabilities'].items():
        for via in v.get('via', []):
            if isinstance(via, dict):
                m = re.search(r'(GHSA-[a-z0-9-]+)', via.get('url', ''))
                if m:
                    found[m.group(1)] = via.get('severity', '?')
    return found, None


def compare_with_npm(findings, lockfile_dir, lockfile_rel):
    npm_ids, problem = npm_audit(lockfile_dir)
    if problem:
        return 'npm audit (%s): skipped, %s' % (lockfile_rel, problem)
    osv_ids = set()
    for f in findings:
        if f['lockfile'] == lockfile_rel:
            osv_ids.update(i for i in [f['id'], *f['aliases']] if i.startswith('GHSA-'))
    both = osv_ids & set(npm_ids)
    only_npm = sorted(set(npm_ids) - osv_ids)
    only_osv = sorted(osv_ids - set(npm_ids))
    return ('npm audit (%s): %d advisories; OSV: %d GHSA ids; in both: %d; only npm: %s; only OSV: %s'
            % (lockfile_rel, len(npm_ids), len(osv_ids), len(both),
               ', '.join(only_npm) or 'none', ', '.join(only_osv) or 'none'))


# ---- osv-scanner, the second opinion ---------------------------------------------------------

OSV_SCANNER_PIN = '2.7.0'  # the release review-security's sources.md pins, with its checksums
OSV_SCANNER_ARGS = ['scan', 'source', '-r', '--no-resolve', '--all-packages', '--x-disable-plugins=directory',
                    '--format', 'json']


def run_osv_scanner(repo, reachability):
    """osv-scanner's answer for `repo`, compacted and with lockfile paths relative to it:
    {'version', 'args', 'exit', 'notes', 'output'}, or {'problem': ...} when it is absent or fails."""
    exe = shutil.which('osv-scanner')
    if not exe:
        return {'problem': 'not installed; second opinion skipped (to install it: review-security sources.md, osv-scanner)'}
    args, notes = list(OSV_SCANNER_ARGS), []
    if reachability:
        if sys.platform.startswith('linux'):
            args.append('--call-analysis=rust')
        else:
            notes.append('osv-scanner reachability: skipped, its Rust call analysis reads ELF binaries '
                         'only, so it runs on Linux, not on %s' % sys.platform)
    try:
        v = subprocess.run([exe, '--version'], capture_output=True, text=True, errors='replace', timeout=30)
        m = re.search(r'version:?\s*v?(\d+(?:\.\d+)+)', v.stdout + v.stderr)
        r = subprocess.run([exe, *args, repo], capture_output=True, text=True, errors='replace',
                           timeout=3600 if reachability else 600)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {'problem': 'failed: %s; second opinion skipped' % type(exc).__name__}
    version = m.group(1) if m else None
    if r.returncode == 128:  # osv-scanner: no packages found
        output = {'results': []}
    elif r.returncode in (0, 1):  # 1: packages with vulnerabilities
        try:
            output = json.loads(r.stdout)
        except ValueError:
            return {'version': version, 'problem': 'gave no JSON (exit %d); second opinion skipped' % r.returncode}
    else:
        last = (r.stderr.strip().splitlines() or ['no message'])[-1][:200]
        return {'version': version, 'problem': 'failed (exit %d: %s); second opinion skipped' % (r.returncode, last)}
    try:
        results = []
        for res in output.get('results') or []:
            path = (res.get('source') or {}).get('path', '')
            packages = []
            for pv in res.get('packages') or []:
                packages.append({'package': {k: (pv.get('package') or {}).get(k, '') for k in ('ecosystem', 'name', 'version')},
                                 'groups': [dict(g) for g in pv.get('groups') or []]})
            rel = os.path.relpath(path, repo) if os.path.isabs(path) else path
            results.append({'source': {'path': rel.replace(os.sep, '/')}, 'packages': packages})
    except (AttributeError, TypeError, ValueError):
        # its answer never fails this audit, not even in a shape nobody expected
        return {'version': version, 'problem': 'gave an answer in an unexpected shape (exit %d); second '
                                               'opinion skipped' % r.returncode}
    return {'version': version, 'args': args, 'exit': r.returncode, 'notes': notes, 'output': {'results': results}}


def package_key(ecosystem, name, version):
    """One key per package on both sides: PyPI names compare as PEP 503 normalises them;
    Packagist names without case and versions without the leading `v` that composer.lock keeps
    and osv-scanner reports (this audit's parser strips it)."""
    if ecosystem == 'PyPI':
        name = re.sub(r'[-_.]+', '-', name).lower()
    elif ecosystem == 'Packagist':
        name, version = name.lower(), version.lstrip('vV')  # as parse_composer_lock does
    return '%s:%s@%s' % (ecosystem, name, version)


def compare_with_osv_scanner(findings, packages, answer):
    """(lines, summary): osv-scanner's packages and advisories against this audit's. An advisory
    is the same on both sides when the package matches and the id families share an id."""
    if 'problem' in answer:
        return ['osv-scanner: %s' % answer['problem']], {'problem': answer['problem']}
    lines = []
    version = answer.get('version')
    if version != OSV_SCANNER_PIN:
        lines.append('osv-scanner: version %s, not the pinned %s; compared anyway' % (version or 'unknown', OSV_SCANNER_PIN))
    ours_packages = {}
    for p in packages:
        ours_packages.setdefault(package_key(p.ecosystem, p.name, p.version), p.lockfile)
    theirs_packages, groups = {}, []
    for res in answer['output'].get('results') or []:
        rel = res['source']['path']
        for pv in res.get('packages') or []:
            pkg = pv['package']
            key = package_key(pkg['ecosystem'], pkg['name'], pkg['version'])
            theirs_packages.setdefault(key, rel)
            for g in pv.get('groups') or []:
                ids = list(g.get('ids') or [])
                if ids:
                    groups.append({'key': key, 'lockfile': rel, 'id': preferred_id(ids),
                                   'family': set(ids) | set(g.get('aliases') or []),
                                   'severity': g.get('max_severity') or '',
                                   'analysis': g.get('experimental_analysis') or {}})
    matched, both, only_ours = set(), [], []
    for f in findings:
        key = package_key(f['ecosystem'], f['name'], f['version'])
        hits = [i for i, g in enumerate(groups) if g['key'] == key and g['family'] & {f['id'], *f['aliases']}]
        matched.update(hits)
        (both if hits else only_ours).append({'id': f['id'], 'package': key, 'lockfile': f['lockfile']})
    only_theirs, seen = [], set()
    for i, g in enumerate(groups):
        if i not in matched and (g['key'], g['id']) not in seen:
            seen.add((g['key'], g['id']))
            only_theirs.append({'id': g['id'], 'package': g['key'], 'lockfile': g['lockfile'], 'severity': g['severity']})
    reach, seen = [], set()
    for g in groups:
        if g['analysis'] and (g['key'], g['id']) not in seen:
            seen.add((g['key'], g['id']))
            called = any(a.get('called') for a in g['analysis'].values())
            reach.append({'id': g['id'], 'package': g['key'], 'state': 'reachable' if called else 'not-reachable'})
    advisories = len({(g['key'], g['id']) for g in groups})
    pk_only_ours = sorted(set(ours_packages) - set(theirs_packages))
    pk_only_theirs = sorted(set(theirs_packages) - set(ours_packages))

    def sample(keys):
        return ', '.join(keys[:5]) + (', …' if len(keys) > 5 else '') if keys else 'none'
    lines.append('osv-scanner %s: %d package(s), %d advisory(ies); ours: %d package(s), %d finding(s); '
                 'in both: %d; only ours: %d; only osv-scanner: %d' % (
                     version or '?', len(theirs_packages), advisories, len(ours_packages), len(findings),
                     len(both), len(only_ours), len(only_theirs)))
    lines.append('osv-scanner packages: only ours: %d (%s); only osv-scanner: %d (%s)' % (
        len(pk_only_ours), sample(pk_only_ours), len(pk_only_theirs), sample(pk_only_theirs)))
    for o in only_ours:
        lines.append('only-ours\t%s\t%s\t%s' % (o['id'], o['package'], o['lockfile']))
    for o in only_theirs:
        lines.append('only-osv-scanner\t%s\t%s\t%s\t%s' % (o['id'], o['package'], o['severity'] or '?', o['lockfile']))
    for r in reach:
        lines.append('%s\t%s\t%s\t(osv-scanner call analysis; information only)' % (r['state'], r['id'], r['package']))
    lines += answer.get('notes') or []
    summary = {'version': version, 'packages': len(theirs_packages), 'advisories': advisories,
               'both': both, 'only_ours': only_ours, 'only_osv_scanner': only_theirs,
               'packages_only_ours': pk_only_ours, 'packages_only_osv_scanner': pk_only_theirs,
               'reachability': reach, 'notes': answer.get('notes') or []}
    return lines, summary


def second_opinion(findings, packages, answer):
    """compare_with_osv_scanner, except that an answer in a shape it cannot read (a recorded file
    edited by hand, a release that changed its output) skips the second opinion, never the audit."""
    try:
        return compare_with_osv_scanner(findings, packages, answer)
    except (KeyError, TypeError, AttributeError, IndexError, ValueError) as exc:
        problem = 'answer in an unexpected shape (%s); second opinion skipped' % type(exc).__name__
        return ['osv-scanner: ' + problem], {'problem': problem}


def main(argv):
    repo, level, use_npm, offline, record, as_json, want_upgrades = None, 'high', True, None, None, False, False
    use_osv_scanner, reachability = True, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--level' and i + 1 < len(argv) and argv[i + 1] in LEVELS:
            level = argv[i + 1]; i += 1
        elif a == '--no-npm':
            use_npm = False
        elif a == '--no-osv-scanner':
            use_osv_scanner = False
        elif a == '--reachability':
            reachability = True
        elif a == '--offline' and i + 1 < len(argv):
            offline = argv[i + 1]; i += 1
        elif a == '--record' and i + 1 < len(argv):
            record = argv[i + 1]; i += 1
        elif a == '--json':
            as_json = True
        elif a == '--upgrades':
            want_upgrades = True
        elif a in ('-h', '--help'):
            print(__doc__); return 0
        elif a.startswith('-') or repo is not None:
            print(__doc__, file=sys.stderr); return 2
        else:
            repo = a
        i += 1
    if repo is None or not os.path.isdir(repo):
        print(__doc__, file=sys.stderr); return 2
    repo = os.path.abspath(repo)
    lockfiles = find_lockfiles(repo)
    if not lockfiles:
        print('audit_dependencies: no lockfile found under %s' % repo)
        if use_osv_scanner:  # it reads lockfiles this audit has no parser for
            client = Offline(offline) if offline else Online(record)
            try:
                print('\n'.join(second_opinion([], [], client.osv_scanner(repo, reachability))[0]))
            finally:
                client.close()
        return 0
    packages, unaudited = [], []
    audited = {os.path.realpath(p) for p in lockfiles}
    for path in lockfiles:
        try:
            packages += parse_lockfile(path, repo, unaudited, audited)
        except (ValueError, OSError) as exc:
            print('audit_dependencies: cannot parse %s: %s' % (os.path.relpath(path, repo).replace(os.sep, '/'), exc), file=sys.stderr)
            return 2
    client = Offline(offline) if offline else Online(record)
    advice, second = [], None
    try:
        findings = audit(packages, client)
        if want_upgrades:
            import datetime
            advice = upgrades(packages, runtimes(repo), client, datetime.date.today().isoformat())
        if use_osv_scanner:
            second = client.osv_scanner(repo, reachability)
    except RuntimeError as exc:
        print('audit_dependencies: %s' % exc, file=sys.stderr)
        return 2
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        # an answer in an unexpected shape is a failed audit (2), not a finding (1)
        print('audit_dependencies: unexpected answer from the vulnerability data (%s: %s)'
              % (type(exc).__name__, exc), file=sys.stderr)
        return 2
    finally:
        client.close()
    notes = []
    if use_npm and not offline:
        for path in lockfiles:
            if os.path.basename(path) == 'package-lock.json':
                notes.append(compare_with_npm(findings, os.path.dirname(path), os.path.relpath(path, repo).replace(os.sep, '/')))
    osv_summary = None
    if second is not None:
        osv_lines, osv_summary = second_opinion(findings, packages, second)
        notes += osv_lines
    if as_json:
        print(json.dumps({'packages': len(packages), 'lockfiles': [os.path.relpath(p, repo).replace(os.sep, '/') for p in lockfiles],
                          'findings': findings, 'unaudited': unaudited, 'upgrades': advice, 'notes': notes,
                          'osv_scanner': osv_summary},
                         indent=1))
    else:
        for f in findings:
            print('%s\t%s\t%s:%s@%s\t%s%s\tfixed: %s\t%s\t%s' % (
                f['level'], f['id'], f['ecosystem'], f['name'], f['version'],
                'direct' if f['direct'] else 'transitive', ',dev' if f['dev'] else '',
                ', '.join(f['fixed']) or 'none', f['lockfile'], f['summary']))
        for u in unaudited:
            print('unaudited\t%s\t%s\t%s:%d' % (u['requirement'], u['reason'], u['lockfile'], u['line']))
        for n in notes:
            print(n)
        for r in advice:
            print('%s\t%s:%s@%s%s\tlatest %s\t%s\t%s' % (
                r['state'], r['ecosystem'], r['name'], r['version'], ',dev' if r['dev'] else '',
                r['latest'] or '?', r['note'] or '-', r['lockfile']))
        counts = {}
        for f in findings:
            counts[f['level']] = counts.get(f['level'], 0) + 1
        print('audit_dependencies: %d package(s) in %d lockfile(s); %d finding(s)%s' % (
            len(packages), len(lockfiles), len(findings),
            '' if not findings else ' (' + ', '.join('%s %d' % (k, counts[k]) for k in LEVELS + ['unknown'] if k in counts) + ')')
            + ('; %d requirement(s) not audited' % len(unaudited) if unaudited else ''))
        if advice:
            states = {}
            for r in advice:
                states[r['state']] = states.get(r['state'], 0) + 1
            print('upgrades: %d direct package(s) and runtime(s) checked (%s)' % (
                len(advice), ', '.join('%s %d' % (k, states[k]) for k in ('eol', 'major-behind', 'behind', 'current', 'unknown') if k in states)))
    failing = [f for f in findings if rank(f['level']) >= LEVELS.index(level)]
    failing += [r for r in advice if rank(UPGRADE_RANK[r['state']]) >= LEVELS.index(level)]
    failing += [u for u in unaudited if rank(UNAUDITED_RANK) >= LEVELS.index(level)]
    return 1 if failing else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
