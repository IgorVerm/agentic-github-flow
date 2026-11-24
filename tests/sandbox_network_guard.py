#!/usr/bin/env python3
"""Checks the guards plugin's pre_tool_sandbox_network.py: python3 tests/sandbox_network_guard.py.

The guard refuses a Bash call only when it can name a lone call that does the same and matches
an `excludedCommands` entry configured now, with the sandbox enabled. Everything here runs in a
scratch folder whose path holds a space: a Claude settings folder (CLAUDE_CONFIG_DIR) per
configuration, the guard's own settings folder (XDG_CONFIG_HOME) and scratch repositories with
GitHub remotes. No command is run; the guard only reads the command and the repositories' config.

BLOCK pairs a command with a line its refusal must contain: calls that escape the sandbox today
(they stay inside, fail, and are retried outside) and must be turned away with the form that
runs excluded. PASS lists calls it must leave alone: no faithful lone call exists, the call
needs no network, or it is already in its excluded form. The end checks the cwd of the session
itself, a sandbox that is off or has no entries, and the hook contract (JSON on stdin, "deny" or
nothing on stdout, exit 0, never "allow" or "ask", never a block on a fault).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, '..', 'plugins', 'guards', 'scripts', 'pre_tool_sandbox_network.py')
HOOKS_JSON = os.path.join(HERE, '..', 'plugins', 'guards', 'hooks', 'hooks.json')
TEMPLATE_PRE_PUSH = os.path.join(HERE, '..', 'templates', 'pre-push')

CORE = ['gh *', 'ssh *', 'scp *', 'git fetch *', 'git pull *', 'git push *', 'git ls-remote *',
        'rsync *']


def main():
    tmp = os.path.realpath(tempfile.mkdtemp(prefix='sandbox-network-guard-'))
    if os.name == 'nt':  # no sandbox on native Windows: the guard must pass everything there
        try:
            return windows(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    try:
        return run_all(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def windows(tmp):
    with open(os.path.join(tmp, 'settings.json'), 'w') as handle:
        json.dump({'sandbox': {'enabled': True, 'excludedCommands': CORE}}, handle)
    repo = os.path.join(tmp, 'repo')
    make_repo(repo, [('origin', 'git@github.com:example-org/demo.git')])
    env = dict(os.environ, CLAUDE_CONFIG_DIR=tmp)
    failures = []
    for command in ('cd "%s" && gh pr list' % repo, 'cd "%s" && ssh -i k box uptime' % repo,
                    'bash "%s/../x.sh"' % repo):
        payload = json.dumps({'tool_name': 'Bash', 'cwd': tmp,
                              'tool_input': {'command': command}})
        r = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                           text=True, env=env)
        if r.returncode or r.stdout.strip():
            failures.append('refused on Windows: %r: %r' % (command, r.stdout))
    for line in failures:
        print('FAIL', line)
    print('sandbox_network_guard: %d/3 ok (native Windows: the guard passes every call)'
          % (3 - len(failures)))
    return 1 if failures else 0


def git(*args):
    subprocess.run(['git', *args], check=True, capture_output=True)


def make_repo(path, remotes, branch='agent/x'):
    os.makedirs(path)
    git('init', '-q', '-b', branch, path)
    for name, url in remotes:
        git('-C', path, 'remote', 'add', name, url)


def git_worktrees(tmp, run, claude, failures):
    """`git -C <dir> push|fetch|pull|ls-remote` and its `--git-dir`/`cd` spellings: refused with
    the lone call where that does the same from the session's worktree, passed otherwise."""
    base = os.path.join(tmp, 'wt space')
    main_co = os.path.join(base, 'main')
    make_repo(main_co, [('origin', 'git@github.com:example-org/demo.git')], branch='main')
    git('-C', main_co, '-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q',
        '--allow-empty', '-m', 'start')
    wt_a, wt_b, wt_c = (os.path.join(base, n) for n in ('wt-a', 'wt-b', 'wt-c'))
    for path, branch in ((wt_a, 'agent/a'), (wt_b, 'agent/b'), (wt_c, 'agent/c')):
        git('-C', main_co, 'worktree', 'add', '-q', '-b', branch, path)
    os.makedirs(os.path.join(wt_a, 'sub'))
    with open(os.path.join(wt_c, '.gitmodules'), 'w') as handle:  # submodules: not the same
        handle.write('[submodule "x"]\n\tpath = x\n\turl = ../x\n')
    other = os.path.join(base, 'other')
    make_repo(other, [('origin', 'git@github.com:example-org/demo.git')], branch='main')
    cfg = os.path.join(base, 'cfg')  # per-worktree configuration switched on
    make_repo(cfg, [('origin', 'git@github.com:example-org/demo.git')], branch='main')
    git('-C', cfg, '-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q',
        '--allow-empty', '-m', 'start')
    cfg_y, cfg_z = os.path.join(base, 'cfg-y'), os.path.join(base, 'cfg-z')
    git('-C', cfg, 'worktree', 'add', '-q', '-b', 'agent/y', cfg_y)
    git('-C', cfg, 'worktree', 'add', '-q', '-b', 'agent/z', cfg_z)
    git('-C', cfg, 'config', 'extensions.worktreeConfig', 'true')
    git('-C', cfg_y, 'config', '--worktree', 'core.sparseCheckout', 'false')  # as merge_landing
    git('-C', cfg_z, 'config', '--worktree', 'remote.origin.url', 'git@github.com:a/fork.git')
    gitdir_b = os.path.join(main_co, '.git', 'worktrees', 'wt-b')
    # review of #140: a remote whose URL is a relative path names another repository from
    # another folder (finding 3); `..` after a symlink in -C leaves for where the link points,
    # since git changes folder physically (finding 4)
    git('-C', main_co, 'remote', 'add', 'near', '../../remote.git')
    git('-C', main_co, 'remote', 'add', 'pushnear', 'git@github.com:example-org/demo.git')
    git('-C', main_co, 'config', 'remote.pushnear.pushurl', '../remote.git')
    os.symlink(other, os.path.join(wt_a, 'link'))
    a, b = '"%s"' % wt_a, '"%s"' % wt_b
    block = [
        ('git -C %s push origin main' % b, '    git push origin main\n'),
        ('git -C %s push -u origin agent/b' % b, '    git push -u origin agent/b\n'),
        ('git -C %s push origin agent/b:agent/b' % b, '    git push origin agent/b:agent/b\n'),
        ('git -C %s push origin --delete agent/old' % b,
         '    git push origin --delete agent/old\n'),
        ('git -C %s push --tags origin' % b, '    git push --tags origin\n'),
        ('git -C %s fetch origin' % b, '    git fetch origin\n'),
        ('git -C %s fetch --prune origin main' % b, '    git fetch --prune origin main\n'),
        ('git -C %s fetch --all' % b, '    git fetch --all\n'),
        ('git -C %s ls-remote origin' % b, '    git ls-remote origin\n'),
        ('git -C "%s" fetch origin' % main_co, '    git fetch origin\n'),
        ('git --git-dir="%s/.git" push origin agent/b' % main_co,
         '    git push origin agent/b\n'),
        ('git --git-dir "%s" fetch origin' % gitdir_b, '    git fetch origin\n'),
        ('cd %s && git push origin agent/b' % b, '    git push origin agent/b\n'),
        ('git -C %s push origin main 2>&1 | tail -3' % b, '    git push origin main\n'),
        ('git -C %s fetch origin && git -C %s log -1' % (b, b), '    git fetch origin\n'),
        # the session's own worktree: everything git does there is the same as a lone call
        ('git -C %s push' % a, '    git push\n'),
        ('git -C %s pull --ff-only' % a, '    git pull --ff-only\n'),
        ('git -C "%s/sub" push origin agent/a' % wt_a, '    git push origin agent/a\n'),
        ('git -C "%s/sub" push' % wt_a, '    git push\n'),
    ]
    passing = [
        # what is pushed or fetched depends on the other worktree's HEAD or upstream
        'git -C %s push' % b, 'git -C %s push origin' % b, 'git -C %s push origin HEAD' % b,
        'git -C %s push origin HEAD:main' % b, 'git -C %s push origin @:main' % b,
        'git -C %s push --follow-tags origin' % b, 'git -C %s fetch' % b,
        'git -C %s ls-remote' % b, 'git -C %s fetch --set-upstream origin main' % b,
        # pull changes the other worktree's files; a local branch as a fetch target
        'git -C %s pull origin main' % b, 'git -C %s fetch origin main:main' % b,
        'git --work-tree=%s --git-dir="%s" pull' % (b, gitdir_b),
        # FETCH_HEAD is each worktree's own
        'git -C %s fetch origin && git -C %s merge FETCH_HEAD' % (b, b),
        # options git reads in the folder, or that this guard does not know
        'git -c core.sshCommand=x -C %s push origin main' % b,
        'git -C %s -c push.default=current push origin main' % b,
        'git --no-pager -C %s push origin main' % b,
        'git -C %s push --receive-pack=x origin main' % b,
        'git -C %s push --frobnicate origin main' % b,
        # a path relative to the other folder
        'git -C %s push ../other main' % b, 'git -C "%s/sub" push ../x main' % wt_a,
        # another repository, submodules, a computed or missing folder
        'git -C "%s" push origin main' % other, 'git -C "%s" push origin agent/c' % wt_c,
        'git -C "$W" push origin main', 'git -C "%s/missing" push origin main' % base,
        # a remote URL or push URL relative to the folder (review of #140, finding 3)
        'git -C %s push near agent/b' % b, 'git -C %s push pushnear agent/b' % b,
        'git -C "%s/sub" push near agent/a' % wt_a, 'git -C %s ls-remote near' % b,
        # `..` after a symlink: git follows the link (finding 4)
        'git -C "%s/link/.." pull' % wt_a, 'git -C "%s/link/.." push origin main' % wt_a,
        'git -C "%s" -C link/.. pull' % wt_a,
        # `~` after `=` stays literal in the shell: the call as written fails
        'git --git-dir=~/x fetch origin',
    ]
    for command, expected in block:
        result = run(['--check', command, '--cwd', wt_a], claude)
        if result.returncode != 2 or expected not in result.stdout:
            failures.append('worktree BLOCK %r: rc %d, wanted %r in:\n%s%s' % (
                command, result.returncode, expected, result.stdout, result.stderr))
    for command in passing:
        result = run(['--check', command, '--cwd', wt_a], claude)
        if result.returncode != 0:
            failures.append('worktree PASS %r: rc %d:\n%s%s' % (
                command, result.returncode, result.stdout, result.stderr))
    # per-worktree configuration: a sparse-checkout key changes nothing for the network, a
    # remote of its own does
    result = run(['--check', 'git -C "%s" push origin agent/y' % cfg_y, '--cwd', cfg], claude)
    if result.returncode != 2 or '    git push origin agent/y\n' not in result.stdout:
        failures.append('sparse per-worktree key, not refused: %s' % result.stdout)
    result = run(['--check', 'git -C "%s" push origin agent/z' % cfg_z, '--cwd', cfg], claude)
    if result.returncode != 0:
        failures.append('own remote in config.worktree, refused: %s' % result.stdout)
    # configuration included per branch can give each worktree its own remote (review of #140)
    inc, inc_w = os.path.join(base, 'inc'), os.path.join(base, 'inc-w')
    make_repo(inc, [('origin', 'git@github.com:example-org/demo.git')], branch='main')
    git('-C', inc, '-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q',
        '--allow-empty', '-m', 'start')
    git('-C', inc, 'worktree', 'add', '-q', '-b', 'agent/w', inc_w)
    git('-C', inc, 'config', 'includeIf.onbranch:agent/w.path', 'fork.inc')
    result = run(['--check', 'git -C "%s" push origin agent/w' % inc_w, '--cwd', inc], claude)
    if result.returncode != 0:
        failures.append('includeIf onbranch, refused: %s' % result.stdout)
    return len(block) + len(passing) + 3 + hooks(base, run, claude, failures)


def hooks(base, run, claude, failures):
    """A push from another worktree runs its hooks in the session's worktree (review of #140,
    finding 2; the maintainer chose (b)): refused only under no hook, or the agentic-github-flow pre-push
    hook as some version of templates/pre-push wrote it, with both worktrees equally exempt from
    its personal-data check."""
    hk, hk_a, hk_b = (os.path.join(base, n) for n in ('hk', 'hk-a', 'hk-b'))
    make_repo(hk, [('origin', 'git@github.com:example-org/demo.git')], branch='main')
    git('-C', hk, '-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q',
        '--allow-empty', '-m', 'start')
    for path, branch in ((hk_a, 'agent/a'), (hk_b, 'agent/b')):
        git('-C', hk, 'worktree', 'add', '-q', '-b', branch, path)
    hook_dir = os.path.join(hk, '.git', 'hooks')
    with open(TEMPLATE_PRE_PUSH, 'rb') as handle:
        template = handle.read()

    def install(name, data):
        for old in ('pre-push', 'reference-transaction'):
            if os.path.exists(os.path.join(hook_dir, old)):
                os.remove(os.path.join(hook_dir, old))
        if name:
            with open(os.path.join(hook_dir, name), 'wb') as handle:
                handle.write(data)

    def settings(name, folders):
        folder = os.path.join(base, name)
        os.makedirs(os.path.join(folder, 'agentic-github-flow'))
        with open(os.path.join(folder, 'agentic-github-flow', 'exempt-dirs'), 'w') as handle:
            handle.write(''.join(f + '\n' for f in folders))
        return folder

    only_b, both = settings('xdg-only-b', [hk_b]), settings('xdg-both', [hk_a, hk_b])
    only_a = settings('xdg-only-a', [hk_a])
    push = 'git -C "%s" push origin agent/b' % hk_b
    # the session's own worktree through --git-dir from another folder: git runs the hooks
    # there (second review of #140, finding 2)
    out = os.path.join(base, 'hk-out')
    os.makedirs(out)
    own = 'git -C "%s" --git-dir="%s" push origin agent/a' % (
        out, os.path.join(hk, '.git', 'worktrees', 'hk-a'))
    cases = [  # (hook, its content, XDG_CONFIG_HOME or None, command, refused[, project])
        (None, b'', None, push, True),
        ('pre-push', template, None, push, True),
        ('pre-push', template, both, push, True),
        ('pre-push', template, only_b, push, False),     # the lone call would skip the check
        ('pre-push', template + b'test -e BROKEN && exit 1\n', None, push, False),
        ('pre-push', b'#!/bin/sh\ntest -e BROKEN && exit 1\nexit 0\n', None, push, False),
        ('pre-push', template, None, 'git -C "%s" fetch origin' % hk_b, True),
        ('reference-transaction', b'#!/bin/sh\nexit 0\n', None,
         'git -C "%s" fetch origin' % hk_b, False),
        ('pre-push', template, None, 'git --work-tree="%s" push origin agent/a' % hk_b, False),
        (None, b'', None, own, True),
        ('pre-push', template, None, own, True),
        ('pre-push', template, only_a, own, False),      # the hook in hk-out is not exempt
        ('pre-push', b'#!/bin/sh\nexit 0\n', None, own, False),
        # alike only with CLAUDE_PROJECT_DIR, which the push from Bash lacks (finding 3)
        ('pre-push', template, only_a, push, False, hk),
        ('pre-push', template, only_a, push, False),
        ('pre-push', template, both, push, True, hk_a),
    ]
    for name, data, xdg, command, refused, *project in cases:
        install(name, data)
        result = run(['--check', command, '--cwd', hk_a], claude,
                     **({'xdg': xdg} if xdg else {}),
                     extra={'CLAUDE_PROJECT_DIR': project[0]} if project else None)
        if result.returncode != (2 if refused else 0):
            failures.append('hook %s (%s), %s: rc %d:\n%s%s' % (
                name, xdg and os.path.basename(xdg), command, result.returncode, result.stdout,
                result.stderr))
    install(None, b'')
    return len(cases)


def run_all(tmp):
    root = os.path.join(tmp, 'with space')
    proj = os.path.join(root, 'proj')            # a project with remote-run scripts
    proj_wt = os.path.join(root, 'proj-worktrees', 'task')
    lab = os.path.join(root, 'lab')
    scripts = ['bash "%s/proj*/tools/remote/%s.sh"*' % (root, s) for s in ('wait', 'status', 'run')]
    scripts.append('bash "%s/bin/remote-ssh"*' % lab)
    tool = os.path.join(tmp, 'plainroot', 'tool')  # a script path without a space
    scripts += ['bash "%s/remote-x.sh"*' % tool, 'bash %s/other.sh *' % tool]

    def settings(name, entries, enabled=True):
        folder = os.path.join(tmp, name)
        os.makedirs(folder)
        sandbox = {'excludedCommands': entries}
        if enabled is not None:
            sandbox['enabled'] = enabled
        with open(os.path.join(folder, 'settings.json'), 'w') as handle:
            json.dump({'sandbox': sandbox}, handle)
        return folder

    full = settings('claude-full', CORE + scripts)
    core = settings('claude-core', CORE)
    off = settings('claude-off', CORE + scripts, enabled=False)
    unset = settings('claude-unset', CORE + scripts, enabled=None)
    empty = os.path.join(tmp, 'claude-none')
    os.makedirs(empty)
    xdg = os.path.join(tmp, 'xdg')
    os.makedirs(os.path.join(xdg, 'agentic-github-flow'))
    with open(os.path.join(xdg, 'agentic-github-flow', 'sandbox-scripts'), 'w') as handle:
        handle.write('# scripts that find their own folder\n%s/proj*/tools/remote/*.sh\n'
                     'relative/ignored.sh\n' % root)
    no_xdg = os.path.join(tmp, 'xdg-none')

    repo = os.path.join(root, 'repo')
    make_repo(repo, [('origin', 'git@github.com:example-org/demo.git')])
    other_repo = os.path.join(root, 'other')
    make_repo(other_repo, [('origin', 'https://github.com/example-org/other.git')])
    fork = os.path.join(root, 'fork')
    make_repo(fork, [('origin', 'git@github.com:someone/demo.git'),
                     ('upstream', 'git@github.com:example-org/demo.git')])
    resolved = os.path.join(root, 'resolved')
    make_repo(resolved, [('origin', 'git@github.com:someone/demo.git'),
                         ('upstream', 'git@github.com:example-org/demo.git')])
    git('-C', resolved, 'config', 'remote.upstream.gh-resolved', 'base')
    enterprise = os.path.join(root, 'enterprise')
    make_repo(enterprise, [('origin', 'git@github.example.com:team/app.git')])
    tracking = os.path.join(root, 'tracking')
    make_repo(tracking, [('origin', 'git@github.com:example-org/demo.git')])
    git('-C', tracking, 'config', 'branch.agent/x.merge', 'refs/heads/feature-y')
    plain = os.path.join(root, 'plain')
    elsewhere = os.path.join(root, 'elsewhere')
    for folder in (plain, elsewhere, os.path.join(proj, 'tools', 'remote'), proj_wt,
                   os.path.join(lab, 'bin'), os.path.join(root, 'other-x', 'x'), tool,
                   os.path.join(proj, 'data')):
        os.makedirs(folder, exist_ok=True)
    os.symlink(os.path.join(root, 'other-x', 'x'), os.path.join(root, 'link'))
    with open(os.path.join(proj_wt, 'input.txt'), 'w') as handle:
        handle.write('x\n')
    home = os.path.expanduser('~')
    for name, line in (('status.sh', '#!/bin/bash'), ('run.sh', '#!/usr/bin/env python3')):
        with open(os.path.join(proj, 'tools', 'remote', name), 'w') as handle:
            handle.write(line + '\necho\n')

    q = '"%s"' % repo
    D = '"%s' % repo  # the start of a quoted absolute path into the scratch repository
    O = 'example-org/demo'

    block = [
        # gh: -R right after the subcommand, the branch where a read-only pr selector is optional
        ("cd %s && gh issue view 29 --json body --jq '.body' | head -300" % q,
         "gh issue view -R %s 29 --json body --jq '.body'" % O),
        ('cd %s && gh pr create --title "a b" --body-file b.md' % q,
         'gh pr create -R %s --head agent/x --title "a b" --body-file %s/b.md"' % (O, D)),
        ('cd %s && gh pr view 5 --repo example-org/other' % q,
         '    gh pr view 5 --repo example-org/other\n'),
        ('cd %s && gh issue list -Rexample-org/x' % q, '    gh issue list -Rexample-org/x\n'),
        ('cd %s && gh pr checks' % q, 'gh pr checks agent/x -R %s' % O),
        ('cd %s && gh pr view --json title' % q, 'gh pr view agent/x -R %s --json title' % O),
        ('cd %s && gh pr diff' % q, 'gh pr diff agent/x -R %s' % O),
        ('cd %s && gh pr merge 7 --squash' % q, 'gh pr merge -R %s 7 --squash' % O),
        ('cd %s && gh issue list -- --foo' % q, 'gh issue list -R %s -- --foo' % O),
        ("cd %s && gh api repos/{owner}/{repo}/pulls --jq '.[].number'" % q,
         "gh api repos/%s/pulls --jq '.[].number'" % O),
        ('cd %s && gh api "repos/{owner}/{repo}/issues/$N" --jq .title' % q,
         'gh api "repos/%s/issues/$N" --jq .title' % O),
        ('cd %s && gh pr view --comments 5' % q, 'gh pr view -R %s --comments 5' % O),
        ('cd %s && gh issue create --title "-Rough draft" --body x' % q,
         'gh issue create -R %s --title "-Rough draft" --body x' % O),
        ('cd %s && gh release create v1 dist/a.zip' % q,
         'gh release create -R %s v1 %s/dist/a.zip"' % (O, D)),
        ('cd %s && gh release create v1 --title Rel1 -n x --target main dist/a.zip' % q,
         'gh release create -R %s v1 --title Rel1 -n x --target main %s/dist/a.zip"' % (O, D)),
        ('cd %s && gh secret set FOO -f vars.env' % q,
         'gh secret set -R %s FOO -f %s/vars.env"' % (O, D)),
        ('cd %s && gh repo view --json name' % q, 'gh repo view %s --json name' % O),
        ('cd %s && gh repo archive --yes' % q, 'gh repo archive %s --yes' % O),
        ('cd %s && gh auth status' % q, '    gh auth status\n'),
        ('cd %s && f=/tmp/body.md && gh issue comment 5 --body-file "$f"' % q,
         'gh issue comment -R %s 5 --body-file /tmp/body.md' % O),
        ('cd %s && gh pr create --title t --body "$(cat <<\'EOF\'\nit\'s `x`\nEOF\n)" --base main'
         % q, 'gh pr create -R %s --head agent/x --title t --body-file "<file>" --base main' % O),
        ('cd %s && gh issue comment 5 --body "$(cat <<\'EOF\'\nhi\nEOF\n)" --edit-last | tail -3'
         % q, 'gh issue comment -R %s 5 --body-file "<file>" --edit-last\n' % O),
        ('cd %s && gh issue comment 5 --body "$(cat notes/b.md)"' % q,
         'gh issue comment -R %s 5 --body-file %s/notes/b.md"' % (O, D)),
        ('cd %s && gh run download 7 -D out' % q, 'gh run download -R %s 7 -D %s/out"' % (O, D)),
        ('cd %s && gh release upload v1 dist/app.zip' % q,
         'gh release upload -R %s v1 %s/dist/app.zip"' % (O, D)),
        ('cd %s && gh issue list && gh pr list -L 5' % q, 'gh pr list -R %s -L 5' % O),
        ('cd %s && ./build.sh $(nproc) && gh pr list' % q, '    gh pr list -R %s\n' % O),
        # gh's own choice among several remotes: the one marked gh-resolved
        ('cd "%s" && gh issue list' % resolved, 'gh issue list -R %s' % O),
        # a second cd later in the call moves the folder (Fable audit finding 1)
        ('cd %s && gh issue view 5 && cd "%s" && gh pr list' % (q, other_repo),
         'gh pr list -R example-org/other'),
        ('cd %s && gh issue view 5 && cd ../other && gh pr list' % q,
         'gh issue view -R %s 5' % O),
        ('cd %s && gh issue view 5 && cd ../other && gh pr list' % q,
         'gh pr list -R example-org/other'),
        # git network next to another network command: listed, with a note and no escape advice
        ('cd %s && gh pr list && git push origin agent/x' % q,
         'git -C "%s" push origin agent/x   [matches no excluded command' % repo),
        # ssh, scp, rsync: local paths absolute
        ("cd %s && ssh -o ConnectTimeout=5 box 'ls ~' | head" % q,
         "    ssh -o ConnectTimeout=5 box 'ls ~'\n"),
        ('cd %s && ssh -F cfg/ssh -i k box uptime' % q,
         'ssh -F %s/cfg/ssh" -i %s/k" box uptime' % (D, D)),
        ('cd %s && ssh -E ssh.log box uptime' % q, 'ssh -E %s/ssh.log" box uptime' % D),
        ('cd %s && ssh -o IdentityFile=/keys/k box uptime' % q,
         '    ssh -o IdentityFile=/keys/k box uptime\n'),
        ('cd %s && scp -P 22 -i k.pem out/a.txt host:/tmp/' % q,
         'scp -P 22 -i %s/k.pem" %s/out/a.txt" host:/tmp/' % (D, D)),
        ('cd %s && rsync -a -e "ssh -p 22" ./dir/ host:x/' % q,
         'rsync -a -e "ssh -p 22" %s/dir/" host:x/' % D),
        ('cd %s && rsync -a --exclude target --exclude-from=ex.txt --link-dest ../prev d/ host:x/'
         % q, 'rsync -a --exclude target "--exclude-from=%s/ex.txt" --link-dest ../prev %s/d/" '
              'host:x/' % (repo, D)),
        # cd spellings
        ('cd %s && gh issue view 3' % repo.replace(' ', '\\ '), 'gh issue view -R %s 3' % O),
        ("cd '%s' ; gh issue view 3" % repo, 'gh issue view -R %s 3' % O),
        ('cd "%s" && cd repo && gh issue view 3' % root, 'gh issue view -R %s 3' % O),
        ('cd "%s" && cd ../plain && ssh box uptime' % plain, '    ssh box uptime\n'),
        # scripts with an excluded `bash "<path>"` entry, listed in sandbox-scripts: after a cd
        ('cd "%s" && tools/remote/status.sh lane2 2>&1 | head -12' % proj_wt,
         'bash "%s/tools/remote/status.sh" lane2' % proj_wt),
        ('cd "%s"; git status --short | head -3; tools/remote/wait.sh lane2 HEAD' % proj_wt,
         'bash "%s/tools/remote/wait.sh" lane2 HEAD' % proj_wt),
        ('cd "%s" && bash tools/remote/wait.sh lane1 g2' % proj,
         'bash "%s/tools/remote/wait.sh" lane1 g2' % proj),
        # ... and without a cd, in another form than the entry's
        ('"%s/tools/remote/wait.sh" lane1 g3' % proj_wt,
         'bash "%s/tools/remote/wait.sh" lane1 g3' % proj_wt),
        ('%s/tools/remote/wait.sh lane1' % proj_wt.replace(' ', '\\ '),
         'bash "%s/tools/remote/wait.sh" lane1' % proj_wt),
        ("bash '%s/tools/remote/wait.sh' lane1" % proj_wt,
         'bash "%s/tools/remote/wait.sh" lane1' % proj_wt),
        ('bash "%s/tools/remote/status.sh" lane1 | tail -5' % proj,
         'bash "%s/tools/remote/status.sh" lane1' % proj),
        ('echo go; bash "%s/tools/remote/wait.sh" lane1' % proj_wt,
         'bash "%s/tools/remote/wait.sh" lane1' % proj_wt),
        ('"%s/bin/remote-ssh" uptime' % lab, 'bash "%s/bin/remote-ssh" uptime' % lab),
        # loose matches of an entry with a middle `*`: these run outside the sandbox today
        ('bash "%s/proj-worktrees/../x/tools/remote/run.sh" lane1' % root,
         'matches an excluded command only loosely'),
        ('bash "%s/proj/evil.sh" "/tools/remote/wait.sh"' % root,
         'matches an excluded command only loosely'),
        # a `*` spanning a substitution (review of #20)
        ('bash "%s/proj$(id)/tools/remote/run.sh" x' % root, 'only loosely'),
        ('bash "%s/proj`id`/tools/remote/run.sh" x' % root, 'only loosely'),
        ('bash "%s/proj${X:-}/tools/remote/run.sh" x' % root, 'only loosely'),
        # a script at a path without a space, entries written quoted or plain
        ('%s/remote-x.sh a' % tool, 'bash "%s/remote-x.sh" a' % tool),
        ('"%s/other.sh" b' % tool, '    bash %s/other.sh b\n' % tool),
        # paths the shell expands the same from any folder, or variables with a literal value
        ('cd %s && scp ~/notes.txt host:/tmp/' % q, '    scp ~/notes.txt host:/tmp/\n'),
        ('cd %s && gh issue comment 5 --body "$(cat ~/body.md)"' % q,
         '--body-file %s/body.md' % home),
        ('f=~/b.md && cd %s && gh issue comment 5 --body-file "$f"' % q,
         '--body-file %s/b.md' % home),
        ('cd %s && gh workflow run ci.yml -F config=@inputs.json' % q,
         '"config=@%s/inputs.json"' % repo),
        ('cd %s && gh api repos/{owner}/{repo}/issues -F body=@-' % q, '-F body=@-\n'),
        ('cd %s && gh pr merge 5 --squash' % q, 'gh pr merge -R %s 5 --squash' % O),
        ('cd %s && gh issue comment 5 -F "$HOME/b.md"' % q,
         'gh issue comment -R %s 5 -F "$HOME/b.md"' % O),
        # too long to parse, and holding the start of an entry with a middle `*` (re-review)
        ('bash "%s/proj/../evil/tools/remote/run.sh" ' % root + 'a' * 32000,
         'longer than 32000 characters'),
    ]
    if repo.startswith(os.path.expanduser('~') + '/'):
        block.append(('cd "$HOME/%s" && gh issue view 3' % repo[len(os.path.expanduser('~')) + 1:],
                      'gh issue view -R %s 3' % O))

    passing = [
        # already a lone excluded call, or no network at all
        'gh issue view 5', 'gh issue view 5 | head', 'ssh box uptime',
        'bash "%s/tools/remote/wait.sh" lane x' % proj_wt,
        'bash "%s/tools/remote/wait.sh" lane x 2>&1' % proj_wt,
        'bash "%s/tools/remote/wait.sh" a && bash "%s/tools/remote/status.sh" b' % (proj_wt, proj),
        'bash "%s/tools/remote/wait.sh" a && gh pr list' % proj_wt,
        '"%s/tools/remote/wait.sh" lane x' % repo,          # no entry for this path
        'bash "%s/tools/remote/lib.sh" x' % proj,            # no entry for this script
        'cd %s && tools/remote/wait.sh x' % q,               # a script with no entry
        'bash "%s/bin/remote-ssh" uptime' % lab, 'cd %s && ./configure && make' % q,
        'git -C %s push origin main' % q, 'cd %s && git status && git log -1' % q,
        'cd %s && git fetch origin 2>&1 | tail -2; git status' % q,  # git for another folder only
        'cd %s && git -C sub push origin main' % q, 'cd %s && python3 tools/x.py | head' % q,
        'cd %s && cargo test' % q, 'cd %s && rsync -a assets/ build/assets/' % q,
        'cd %s && scp a.txt b.txt' % q,
        # gh cannot be pointed at the same repository from another folder
        'cd "%s" && gh issue view 1' % plain, 'cd "%s" && gh api repos/{owner}/{repo}' % plain,
        'cd "%s" && gh issue list' % fork,               # two remotes, none marked: gh would ask
        'cd "%s" && gh pr list' % enterprise,            # not github.com
        'cd %s && gh repo rename x' % q, 'cd %s && gh frobnicate' % q,
        'cd %s && gh pr checkout 5' % q, 'cd %s && gh pr status' % q,
        'cd %s && gh pr create --fill' % q, 'cd %s && gh issue develop 5 --checkout' % q,
        'cd %s && gh repo clone example-org/x' % q, 'cd %s && gh run download 7' % q,
        'cd %s && gh release download v1' % q, 'cd %s && gh gist create notes.md' % q,
        # a pull request chosen by the folder's branch, for a command that changes it
        'cd %s && gh pr merge --squash' % q, 'cd %s && gh pr comment --body x' % q,
        'cd %s && gh pr close' % q, 'cd %s && gh pr edit --add-label x' % q,
        'cd %s && gh pr ready' % q, 'cd %s && gh pr review --approve' % q,
        # input, output to a file, substitutions, assignments, wrappers
        'cd %s && gh issue create --title "$(date)"' % q, 'cd %s && ssh box bash < run.sh' % q,
        'cd %s && gh secret set FOO < secret.txt' % q, 'cd %s && GH_TOKEN=x gh api user' % q,
        'cd %s && GH_REPO=a/b gh pr list' % q,
        'cd %s && echo hi | gh issue comment 5 --body-file -' % q,
        "cd %s && ssh host bash -s <<'EOF'\nuptime\nEOF" % q,
        "cd %s && gh issue comment 5 --body-file - <<'EOF'\nhi\nEOF" % q,
        'cd %s && gh issue comment 5 --body "$(cat <<\'EOF\'\nhi\nEOF\n)" && echo done' % q,
        'cd %s && gh issue comment 5 --body "$(cat <<\'EOF\'\nhi\nEOF\n)" > out.txt' % q,
        'cd "%s" && bash tools/remote/wait.sh l > "$TMPDIR/o"' % proj_wt,
        'cd "%s" && tools/remote/status.sh l | tee s.txt' % proj_wt,
        'cd %s && gh pr list | python3 x.py' % q,
        'bash "%s/tools/remote/wait.sh" lane1 > /tmp/w.txt' % proj_wt,
        'bash "%s/tools/remote/wait.sh" lane1 $(git rev-parse HEAD)' % proj_wt,
        'cd %s && rsync -a --frobnicate x d/ host:x/' % q,
        'cd %s && timeout 60 gh pr list' % q, 'cd %s && command gh pr list' % q,
        'cd %s && exec gh pr list' % q, 'cd %s && gh api graphql -F owner={owner} -f query=q' % q,
        'cd %s && gh pr list | sort -o out.txt' % q, "cd %s && gh pr list | sed -n 'w out.txt'" % q,
        'cd %s && gh pr list | sort -uo out.txt' % q,
        "cd %s && gh pr view 5 | sed -n 's/a/b/w out.txt'" % q,
        'cd %s && gh pr list &' % q,
        # globs: the shell would expand them against another folder (Fable audit finding 2)
        'cd %s && gh release create v1 dist/*' % q, 'cd %s && scp out/*.txt host:/tmp/' % q,
        'cd %s && rsync -a build/[ab] host:x/' % q, 'cd %s && gh release upload v1 dist/?.zip' % q,
        # a second cd whose target is computed, or a later cd that cannot be followed
        'cd %s && gh issue view 5 && cd "$X" && gh pr list' % q,
        'cd %s && gh issue view 5 && cd - && gh pr list' % q,
        'cd %s && gh issue view 5; pushd /tmp && gh pr list' % q,
        # ssh option values the rewrite cannot place
        'cd %s && ssh -o IdentityFile=k box uptime' % q,
        'cd %s && ssh -oIdentityFile=keys/k box uptime' % q,
        'cd %s && ssh -o "ProxyCommand=./jump %%h" box uptime' % q,
        'cd %s && rsync -a -e "ssh -i k" d/ host:x/' % q,
        'cd %s && scp -S ./myssh a.txt host:/tmp/' % q,
        'cd %s && scp -o IdentityFile=k a.txt host:/tmp/' % q,
        # a listed script from another folder, but its interpreter is not bash
        'cd "%s" && tools/remote/run.sh x' % proj, '"%s/tools/remote/run.sh" x' % proj,
        # a script with an entry, after a cd to another folder, not listed in sandbox-scripts
        'cd "%s" && bin/remote-ssh uptime' % lab,
        # rewrites that would name another file, branch or folder (review of #20)
        'cd "%s/link" && scp ../secret.txt host:/tmp/' % root,
        'cd %s && scp "~/notes.txt" host:/tmp/' % q, 'cd %s && rsync -a . host:/dst/' % q,
        'cd %s && rsync -a sub/. host:/dst/' % q,
        'cd %s && rsync -aR sub/file.txt host:/dst/' % q,
        'cd %s && rsync -a --relative sub/file.txt host:/dst/' % q,
        "cd %s && rsync -a -f 'merge rules.txt' src/ host:/dst/" % q,
        "cd %s && rsync -a --filter='. rules.txt' src/ host:/dst/" % q,
        'cd "%s" && gh pr create --title t --body b' % resolved,
        'cd "%s" && gh pr view' % resolved,
        'cd "%s" && gh pr create --title t --body b' % tracking,
        'cd "%s" && gh pr checks' % tracking,
        'f=draft.md; f="$TMPDIR/body.md"; cd %s && gh pr comment 5 --body-file "$f"' % q,
        'f=a.md || f=b.md; cd %s && gh issue comment 5 --body-file "$f"' % q,
        'cd %s && gh issue comment 5 --body-file "notes-$n.md"' % q,
        'cd %s && ssh host -i id_test uptime' % q,
        'cd "%s/data" && ../tools/remote/wait.sh ./input.txt' % proj,
        'cd "%s" && tools/remote/wait.sh ./input.txt' % proj_wt,
        'cd "%s" && tools/remote/wait.sh input.txt' % proj_wt,
        'cd "%s" && sh tools/remote/wait.sh x' % proj_wt,
        'cd %s && gh ruleset check' % q, 'cd %s && gh pr merge 5 --delete-branch' % q,
        'cd %s && gh pr merge 5 -d' % q,
        'bash "%s"/proj*/tools/remote/wait.sh x' % root,
        'cd %s && gh pr list ' % q + 'x' * 40000,
        # variables whose value is not certain, and more paths (re-review of #20)
        'f=a.md; declare f=b.md; cd %s && gh pr comment 5 -F "$f"' % q,
        'f=a.md; unset f; cd %s && gh pr comment 5 -F "$f"' % q,
        'f=a.md; read -r f < name.txt; cd %s && gh pr comment 5 -F "$f"' % q,
        'f=b.md; test -e a.md && f=a.md; cd %s && gh pr comment 5 -F "$f"' % q,
        'f=a; f+=.md; cd %s && gh pr comment 5 -F "$f"' % q,
        'cd "%s" && tools/remote/wait.sh newfile.txt' % proj_wt,
        'cd "%s" && tools/remote/wait.sh --input=input.txt' % proj_wt,
        'cd %s && gh issue comment 5 --body "$(cat \'body.md\')"' % q,
        'cd %s && scp "$TMPDIR/a.txt" host:/tmp/' % q,
        'cd %s && gh issue comment 5 -F "$TMPDIR/b.md"' % q,
        # loops, conditionals, other shapes
        'bash "%s/tools/remote/run.sh" lane1 -- \'cd /work/../x && ls\'' % proj_wt,
        'cd %s && for n in 1 2; do gh issue view $n; done' % q,
        'cd %s && if true; then git push; fi' % q,
        'cd "$W" && gh issue view 5', 'cd - && gh issue view 5', 'cd && gh issue view 5',
        'cd %s || exit 1; gh issue view 5' % q, 'echo cd %s && echo gh' % q,
        "cd %s && echo 'gh issue view 5'" % q, "cd %s && git commit -m 'git push later'" % q,
        'cd %s && gh issue view "5' % q, 'cd %s && ( gh issue view 5 )' % q,
        "ssh host 'cat /a/../b'", 'scp %s/../x host:' % repo, "bash <<< 'gh pr list'",
    ]

    def run(args, claude, stdin=None, xdg=xdg, extra=None):
        env = {k: v for k, v in os.environ.items()
               if k not in ('GH_REPO', 'GH_HOST', 'CLAUDE_PROJECT_DIR')}
        env.update(CLAUDE_CONFIG_DIR=claude, XDG_CONFIG_HOME=xdg, **(extra or {}))
        if args[:1] == ['--check'] and len(args) > 1:  # the command through stdin: Windows
            stdin, args = args[1], ['--check', '-'] + args[2:]  # caps a command line at 32,767
        return subprocess.run([sys.executable, HOOK, *args], input=stdin, capture_output=True,
                              text=True, env=env)

    failures = []
    for command, expected in block:
        result = run(['--check', command, '--cwd', elsewhere], full)
        if result.returncode != 2 or expected not in result.stdout:
            failures.append('BLOCK %r: rc %d, wanted %r in:\n%s%s' % (
                command, result.returncode, expected, result.stdout, result.stderr))
        elif 'dangerouslyDisableSandbox' in result.stdout or 'escape' in result.stdout:
            failures.append('BLOCK %r: the reason advises an escape:\n%s' % (command,
                                                                            result.stdout))
    for command in passing:
        result = run(['--check', command, '--cwd', elsewhere], full)
        if result.returncode != 0:
            failures.append('PASS %r: rc %d:\n%s%s' % (command, result.returncode, result.stdout,
                                                      result.stderr))
    checks = len(block) + len(passing)

    # the session's own folder: gh needs no -R, git and listed or unlisted scripts lose the cd
    same = ((repo, 'cd %s && gh issue view 3 | head' % q, '    gh issue view 3\n'),
            (repo, 'cd %s && git fetch origin 2>&1 | tail -2; git status' % q,
             '    git fetch origin\n'),
            (repo, 'cd %s && git ls-remote origin' % q, '    git ls-remote origin\n'),
            (repo, 'cd %s && gh pr merge --squash' % q, '    gh pr merge --squash\n'),
            (fork, 'cd "%s" && gh issue list' % fork, '    gh issue list\n'),
            (lab, 'cd "%s" && bin/remote-ssh uptime' % lab, 'bash "%s/bin/remote-ssh" uptime' % lab),
            (repo, 'cd %s && gh release create v1 dist/*' % q, '    gh release create v1 dist/*\n'))
    for cwd, command, expected in same:
        result = run(['--check', command, '--cwd', cwd], full)
        if result.returncode != 2 or expected not in result.stdout:
            failures.append('same folder %r: %s%s' % (command, result.stdout, result.stderr))
    checks += len(same)

    # git's network commands through -C, --git-dir or a cd, from a worktree of the same
    # repository (#122): the session works in `wt_a`; `wt_b` and the main checkout share its
    # branches and remotes
    checks += git_worktrees(tmp, run, full, failures)

    # nothing is refused where the sandbox is off, unset, has no entries, or has no settings
    sample = [c for c, _ in block[:5] + block[-8:]]
    for claude, what in ((off, 'sandbox off'), (unset, 'sandbox not enabled'),
                         (empty, 'no settings')):
        for command in sample:
            result = run(['--check', command, '--cwd', elsewhere], claude)
            if result.returncode != 0:
                failures.append('%s refused %r: %s' % (what, command, result.stdout))
        checks += len(sample)
    # without the script entries no script call is refused
    for command in ('cd "%s" && tools/remote/status.sh lane2' % proj_wt,
                    '"%s/tools/remote/wait.sh" l' % proj_wt):
        result = run(['--check', command, '--cwd', elsewhere], core)
        if result.returncode != 0:
            failures.append('core settings refused %r: %s' % (command, result.stdout))
        checks += 1
    # without sandbox-scripts, a script after a cd to another folder passes
    result = run(['--check', 'cd "%s" && tools/remote/status.sh lane2' % proj_wt, '--cwd',
                  elsewhere], full, xdg=no_xdg)
    if result.returncode != 0:
        failures.append('no sandbox-scripts file, still refused: %s' % result.stdout)
    # GH_REPO in the environment picks gh's repository, not the folder: pass
    result = run(['--check', 'cd %s && gh pr list' % q, '--cwd', elsewhere], full,
                 extra={'GH_REPO': 'example-org/other'})
    if result.returncode != 0:
        failures.append('GH_REPO set, still refused: %s' % result.stdout)
    checks += 2
    # one folder named in many parts costs its git lookups once (re-review: 58 s before)
    started = time.time()
    run(['--check', ('cd "%s" && ' % repo) + ' && '.join(['gh pr view 1'] * 1500), '--cwd',
         elsewhere], full)
    if time.time() - started > 5:
        failures.append('1,500 gh parts took %.1f s' % (time.time() - started))
    checks += 1

    # the hook contract
    def hook(payload, claude=full):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return run([], claude, stdin=text)

    result = hook({'tool_name': 'Bash', 'cwd': elsewhere,
                   'tool_input': {'command': 'cd %s && gh issue view 3' % q}})
    decision = json.loads(result.stdout)['hookSpecificOutput'] if result.stdout.strip() else {}
    text = decision.get('permissionDecisionReason', '')
    if result.returncode != 0 or decision.get('permissionDecision') != 'deny' \
            or '-R %s' % O not in text or 'sandbox-network guard' not in text:
        failures.append('hook contract, deny: %r' % result.stdout)
    passes = ({'tool_name': 'Bash', 'cwd': elsewhere, 'tool_input': {'command': 'gh issue view 3'}},
              {'tool_name': 'Read', 'tool_input': {'file_path': '/x'}},
              {'tool_name': 'mcp__terminal__run_in_terminal', 'cwd': elsewhere,
               'tool_input': {'command': 'cd %s && gh issue view 3' % q}},
              {'tool_name': 'Bash', 'tool_input': {'command': 5}}, 'not json', '[]', '"x"')
    for payload in passes:
        result = hook(payload)
        if result.stdout.strip() or result.returncode != 0:
            failures.append('hook contract, pass: %r: %r' % (payload, result.stdout))
    broken = os.path.join(tmp, 'claude-broken')
    os.makedirs(broken)
    with open(os.path.join(broken, 'settings.json'), 'w') as handle:
        handle.write('{"sandbox": ')
    result = hook({'tool_name': 'Bash', 'cwd': elsewhere,
                   'tool_input': {'command': 'cd %s && gh issue view 3' % q}}, broken)
    if result.stdout.strip() or result.returncode != 0:
        failures.append('unreadable settings refused a call: %r' % result.stdout)
    if run(['--check'], full).returncode != 64:
        failures.append('--check without a command')
    checks += 1 + len(passes) + 2

    # the plugin does not wire it: it is opt-in through the installer (--guards sandbox)
    with open(HOOKS_JSON) as handle:
        if 'pre_tool_sandbox_network.py' in handle.read():
            failures.append('hooks.json wires the opt-in guard for everyone')
    checks += 1

    for line in failures:
        print('FAIL', line)
    print('sandbox_network_guard: %d/%d ok (%d refused with a rewrite, %d passed)' % (
        checks - len(failures), checks, len(block), len(passing)))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
