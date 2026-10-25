#!/usr/bin/env python3
"""Runs every offline test: python3 tests/run_all.py [--require-all].

A test that needs a client command it cannot find exits 77 and counts as skipped; with
--require-all (CI) a skip is a failure. The live skill-choice probe (skill_triggers.py) spends
tokens and is not part of this gate.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = ['skills_format.py', 'repo_checks.py', 'claude_permissions.py', 'git_guard.py',
         'personal_data_guard.py', 'scan_secrets.py', 'audit_dependencies.py',
         'skill_triggers_offline.py', 'worktree_tools.py', 'installer.py', 'codex_policy.py',
         'plugin_validate.py']


def main():
    require_all = '--require-all' in sys.argv[1:]
    results = []
    for name in TESTS:
        started = time.time()
        r = subprocess.run([sys.executable, os.path.join(HERE, name)], capture_output=True,
                           text=True)
        status = {0: 'ok', 77: 'skip'}.get(r.returncode, 'FAIL')
        results.append((name, status))
        lines = (r.stdout + r.stderr).strip().splitlines()
        print('%-4s %-28s %5.1fs  %s' % (status, name, time.time() - started,
                                         lines[-1] if lines else ''))
        if status == 'FAIL':
            print('     ' + '\n     '.join(lines[-30:]))
    failed = [n for n, s in results if s == 'FAIL' or (s == 'skip' and require_all)]
    skipped = [n for n, s in results if s == 'skip']
    print('%d of %d passed%s%s' % (
        sum(s == 'ok' for _, s in results), len(results),
        '; skipped: ' + ', '.join(skipped) if skipped else '',
        '; FAILED: ' + ', '.join(failed) if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
