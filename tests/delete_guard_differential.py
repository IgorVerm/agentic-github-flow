#!/usr/bin/env python3
"""The delete guard never asks less than it did on main: python3 tests/delete_guard_differential.py.

tests/fixtures/delete_guard_main.py is the guard as it was on main before issue #4 (bcc141c),
kept byte for byte. This test judges the same commands with that guard and with the plugin's
guard, in-process, in the fixture home of tests/delete_guard_cases.py, and fails on any command
main asks about and the plugin's guard passes. A change that makes the guard ask less must say
so here, by changing this test, not by slipping through.

The commands: every ASK and PASS case of tests/delete_guard_cases.py; the probe corpus in
tests/fixtures/delete_guard_probes.txt (the independent reviews' probes); and a generated corpus
that joins prefixes which change, hide or confuse the working folder with deletes (also ones
without a delete word, which the guard's fallback for a fault or an overrun does not catch), in
the home folder, a repository and a folder deep inside it.

The fixture's own `import` of pre_tool_git_guard.py resolves to the plugin's copy (the shared
shell helpers): the fixture is loaded with the plugin's scripts folder as its location. Nothing
here runs a delete; the guards only read the commands.
"""
import itertools, os, random, sys, types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import delete_guard_cases as cases  # noqa: E402 (builds the fixture)

MAIN = os.path.join(HERE, 'fixtures', 'delete_guard_main.py')
PROBES = os.path.join(HERE, 'fixtures', 'delete_guard_probes.txt')
WHERE = {'HOME': cases.HOME, 'REPO': cases.REPO, 'DEEP': cases.DEEP, 'SCRIPTS': cases.SCRIPTS,
         'CODE': cases.CODE, 'OUTSIDE': cases.OUTSIDE}

# the environment the hook gets in tests/delete_guard_cases.py, for the in-process guards
for name in ('TMPDIR', 'TEMP', 'TMP'):
    os.environ.pop(name, None)
os.environ.update(cases.env_for())


def load_guard(name, source):
    """The guard in source as a module located in the plugin's scripts folder."""
    module = types.ModuleType(name)
    module.__file__ = cases.HOOK
    with open(source, encoding='utf-8') as f:
        code = compile(f.read(), source, 'exec')
    exec(code, module.__dict__)
    return module


main = load_guard('delete_guard_main', MAIN)
branch = load_guard('delete_guard_branch', cases.HOOK)

# --- the generated corpus --------------------------------------------------------------------
PREFIXES = [
    'cd ~', 'cd ..', 'cd ../..', 'cd /tmp/x', 'cd ~/Documents', 'cd ~/.ssh', 'cd -', 'cd',
    'cd -1', 'cd ~ x', 'cd a/b/deep Documents', 'pushd ~', 'pushd /tmp/x', 'popd', 'pushd',
    'pushd +1', 'dirs -c', 'time cd /tmp/x', 'FOO=1 cd /tmp/x', 'builtin cd /tmp/x',
    'command cd ~', '! cd /tmp/x', 'noglob cd /tmp/x', 'nocorrect cd /tmp/x', 'eval "cd ~"',
    'eval "cd /tmp/x"', 'eval "echo cd"', 'eval "$(echo cd ~)"', 'eval "$(ssh-agent -s)"',
    'ROOT=$(cd .. && pwd)', 'D="$(cd ~/proj && pwd)"', 'C="cd /tmp/x"; $C', 'C="cd ~"; $C',
    '$(echo cd) /tmp/x', '(cd ~)', '(cd /tmp/x && make)', 'env -C /tmp/x true',
    'f() { cd ..; }', 'f() { cd /tmp/x; }; f', 'function g { cd /tmp/x; }; g',
    'for i in 1 2; do cd ..; done', 'for i in 1 2; do cd /tmp/x; done',
    'for d in a b; do (cd $d && make); done', 'while read d; do cd "$d"; done < l',
    'repeat 2 cd ..', "trap 'cd ~' EXIT", "trap 'cd /tmp/x' DEBUG", 'true', 'false',
    'cd /tmp/x || exit 1', 'set -e', 'cd "$D"', 'cd $(mktemp -d)', 'CDPATH=~', 'export CDPATH=~',
    'T=$(mktemp -d)', 'X=~', 'X=/tmp/x', 'cd /tmp/x | true', 'if cd /tmp/x; then true; fi',
    '{ cd /tmp/x; }', 'case a in a) cd /tmp/x;; esac',
]
JOINERS = [' && ', '; ', ' || ', ' | ', ' & ', '\n']
DELETES = [
    'rm .zshrc', 'rm -f .zshrc', 'rm -rf *', 'rm *', 'rm -rf Documents', 'rm *.log',
    'rm ~-/.zshrc', 'rm -rf Library', 'rm -rf build', 'find . -delete', 'rm -rf .git',
    'rm known_hosts', 'rm -rf ../Documents', 'rm -rf "$X"', 'rm -rf $X/Library', 'rm -rf .',
    'rmdir Documents', 'unlink .zshrc', 'rm -rf ~+/Library', "trap 'rm -rf Documents' EXIT",
    'bash -c "rm -rf Documents"', 'eval "rm .zshrc"', 'ls | xargs rm', 'f',
    # deletes without a delete word, which a fault or an overrun of the guard does not catch
    'R=rm; $R -r Library', '/bin/r? -r Documents', "$'\\x72m' -r ~/Library", '=rm -r .ssh',
    '$RMCMD -rf Library',
]
GENERATED_WHERE = ('HOME', 'REPO', 'SCRIPTS')


def generated():
    """Every prefix with every joiner and delete, and a fixed sample of two- and three-prefix
    chains."""
    out = [(p + j + d, WHERE[w]) for p, j, d, w in itertools.product(
        PREFIXES, JOINERS, DELETES, GENERATED_WHERE)]
    rng = random.Random(4)  # fixed: the same corpus on every run and system
    for _ in range(6000):
        n = rng.choice((2, 2, 3))
        text = rng.choice(PREFIXES)
        for _ in range(n - 1):
            text += rng.choice(JOINERS) + rng.choice(PREFIXES)
        out.append((text + rng.choice(JOINERS) + rng.choice(DELETES),
                    WHERE[rng.choice(GENERATED_WHERE)]))
    return out


def probes():
    out = []
    with open(PROBES, encoding='utf-8') as f:
        for k, line in enumerate(f.read().split('\n'), 1):
            if not line.strip() or line.startswith('#'):
                continue
            where, _, command = line.partition(' ')
            if where not in WHERE:  # an empty command is a probe too
                sys.exit('%s line %d: expected `<%s> <command>`' % (PROBES, k, '|'.join(WHERE)))
            out.append((command, WHERE[where]))
    return out


def verdict(guard, command, cwd):
    reason, _ = guard.decide_bounded(command, cwd)
    return reason


def main_check():
    corpora = [('cases', cases.ASK + cases.PASS), ('probes', probes()),
               ('generated', generated())]
    regressions, counts = [], []
    for label, corpus in corpora:
        asked_main = asked_branch = 0
        for command, cwd in corpus:
            old = verdict(main, command, cwd)
            new = verdict(branch, command, cwd)
            asked_main += bool(old)
            asked_branch += bool(new)
            if old and not new:
                regressions.append('%s: main asks, the guard passes: %r (cwd %s)\n    main: %s'
                                   % (label, command[:200], os.path.relpath(cwd, cases.tmp),
                                      old[:200]))
        counts.append('%s %d (main asks %d, the guard %d)' % (label, len(corpus), asked_main,
                                                             asked_branch))
    if regressions:
        print('\n'.join(regressions))
        print('FAILED: %d commands main asks about pass' % len(regressions))
        return 1
    print('OK: the guard asks for every command main asks for; ' + '; '.join(counts))
    return 0


if __name__ == '__main__':
    sys.exit(main_check())
