#!/usr/bin/env python3
"""Runs `claude plugin validate --strict` on the marketplace, every plugin and every plugin's
skills folder: python3 tests/plugin_validate.py. Strict mode fails on warnings too (unknown
fields, missing metadata). Exits 77 (skipped) when no claude command is found; CLAUDE=<path>
overrides it.
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def main():
    claude = os.environ.get('CLAUDE') or shutil.which('claude')
    if not claude:
        print('SKIP: no claude command (install Claude Code, or set CLAUDE=<path>)')
        return 77
    targets = ['.']
    for plugin in sorted(os.listdir(os.path.join(ROOT, 'plugins'))):
        targets.append(os.path.join('plugins', plugin))
        if os.path.isdir(os.path.join(ROOT, 'plugins', plugin, 'skills')):
            targets.append(os.path.join('plugins', plugin, 'skills'))
    failures = 0
    for target in targets:
        r = subprocess.run([claude, 'plugin', 'validate', '--strict', target], cwd=ROOT,
                           capture_output=True, text=True)
        ok = r.returncode == 0
        failures += not ok
        print('%s %s' % ('ok  ' if ok else 'FAIL', target))
        if not ok:
            print('     ' + (r.stdout + r.stderr).strip().replace('\n', '\n     '))
    print('%d of %d valid' % (len(targets) - failures, len(targets)))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
