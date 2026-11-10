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

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, '..', 'plugins', 'guards', 'scripts', 'pre_tool_sandbox_network.py')
HOOKS_JSON = os.path.join(HERE, '..', 'plugins', 'guards', 'hooks', 'hooks.json')

CORE = ['gh *', 'ssh *', 'scp *', 'git fetch *', 'git pull *', 'git push *', 'git ls-remote *',
        'rsync *']


def main():
    tmp = os.path.realpath(tempfile.mkdtemp(prefix='sandbox-network-guard-'))
    try:
        return run_all(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def git(*args):
    subprocess.run(['git', *args], check=True, capture_output=True)


def make_repo(path, remotes, branch='agent/x'):
    os.makedirs(path)
    git('init', '-q', '-b', branch, path)
    for name, url in remotes:
        git('-C', path, 'remote', 'add', name, url)


def run_all(tmp):
    root = os.path.join(tmp, 'with space')
    proj = os.path.join(root, 'proj')            # a project with remote-run scripts
    proj_wt = os.path.join(root, 'proj-worktrees', 'task')
    lab = os.path.join(root, 'lab')
    scripts = ['bash "%s/proj*/tools/remote/%s.sh"*' % (root, s) for s in ('wait', 'status', 'run')]
    scripts.append('bash "%s/bin/remote-ssh"*' % lab)

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
    plain = os.path.join(root, 'plain')
    elsewhere = os.path.join(root, 'elsewhere')
    for folder in (plain, elsewhere, os.path.join(proj, 'tools', 'remote'), proj_wt,
                   os.path.join(lab, 'bin')):
        os.makedirs(folder, exist_ok=True)
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
        env = {k: v for k, v in os.environ.items() if k not in ('GH_REPO', 'GH_HOST')}
        env.update(CLAUDE_CONFIG_DIR=claude, XDG_CONFIG_HOME=xdg, **(extra or {}))
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
