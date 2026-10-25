#!/usr/bin/env python3
"""Checks the guards plugin's pre_tool_git_guard.py: python3 tests/git_guard.py.

BLOCK lists commands the core rules' §Git forbids, in the spellings the Codex prefix rules cannot see
(tests/codex_policy.py GAPS) and inside wrappers. ALLOW lists everyday commands, including commit
messages that merely mention a forbidden command, which must pass. The hook contract (JSON on
stdin, exit 2 to block) is exercised for one case of each kind.
"""
import json, os, subprocess, sys, time

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plugins', 'guards', 'scripts',
                    'pre_tool_git_guard.py')

BLOCK = [
    'git push --force origin main', 'git push -f', 'git push origin main --force-with-lease',
    'git push origin +main', 'git push --mirror', 'git -C /tmp/x push --force origin main',
    'git reset --hard', 'git reset HEAD~1 --hard', 'git -C /tmp/x reset --hard HEAD',
    'git clean -fd', 'git restore a.txt', 'git restore --staged --worktree a.txt',
    'git checkout -- a.txt', 'git checkout .', 'git checkout -f main', 'git switch --discard-changes main',
    'git stash drop', 'git stash clear', 'git rebase main', 'git -C /tmp/x rebase main',
    'git tag -d v1', 'git -C /tmp/x tag -d v1', 'git tag -f v1', 'git branch -D x', 'git branch -f main HEAD~1',
    'git filter-branch --tree-filter x', 'git filter-repo --path x', 'git replace a b',
    'git reflog expire --all', 'git gc --prune=now', 'git prune', 'git update-ref -d refs/heads/x',
    'git worktree remove ../wt', 'git -C /tmp/x worktree remove ../wt',
    'git commit -m probe --no-verify', 'git commit -m probe -n', 'git commit -m probe -a',
    'git commit -am probe', 'git -C /tmp/x commit --no-verify -m x', 'git push --no-verify origin main',
    'git add -A', 'git add example.txt -A', 'git add example.txt --all', 'git add src -f', 'git add .',
    'git -c core.hooksPath=/dev/null commit -m x', 'git config --global user.email x',
    'git config core.hooksPath /dev/null', 'git config user.name x',
    '/usr/bin/git reset --hard', 'env GIT_INDEX_FILE=/tmp/i git commit --no-verify -m x',
    'GIT_DIR=/tmp/g git reset --hard', '/bin/zsh -lc "git push --force origin main"',
    "bash -lc 'git reset --hard HEAD'", 'sh -c "cd /tmp && git clean -fd"',
    'cd /tmp/x && git add -A && git commit -m x', 'git status; git reset --hard',
    'for f in a b; do git checkout -- $f; done',
    'python3 -c "import subprocess; subprocess.run(\'git reset --hard\', shell=True)"',
    'true || git rebase main', 'echo ok | xargs git branch -D',
    # a line continuation, a here-document read by a shell, command substitution
    'git push \\\n  --force origin main', 'git reset \\\n--hard',
    'bash <<EOF\ngit reset --hard\nEOF', "ssh box bash -s <<'EOF'\ncd repo && git clean -fd\nEOF",
    'python3 - <<EOF\nimport os\nos.system("git reset --hard")\nEOF',
    'echo "$(git reset --hard)"', 'echo `git clean -fd`', 'x=$(git stash drop)',
    'gh issue comment 1 --body "ran `git rebase main` here"',
    'echo "a <<EOF b"\ngit reset --hard\nEOF', 'git commit -m "see <<EOF" -- a.md\ngit reset --hard\nEOF',
    'echo \\<<EOF\ngit clean -fd\nEOF', 'bash <<< "git reset --hard"', 'echo git reset --hard | bash',
    'printf "git push --force" | sh -s', 'git --config-env=core.hooksPath=X commit -m x',
    'gh config set git_protocol ssh', 'gh alias set co "pr checkout"',
    # more spellings
    'git pull --rebase', 'git pull -r origin main', 'git pull origin main --rebase=merges',
    'git checkout main a.txt', 'git checkout HEAD~1 src/a.py', 'git checkout -B main origin/main',
    'git checkout ./', 'git switch -C main', 'git switch --force-create main',
    'git worktree add ../wt -B main', 'git add ./', 'git add *', 'git add :/', 'git add ../',
    'git reset --har', 'git push --forc origin main', 'git commit -m x --no-ve',
    'git branch -M main', 'git update-ref --delete refs/heads/x',
    # wrappers, other machines, eval
    'timeout 60 git reset --hard', 'nice -n 5 git clean -fd', 'caffeinate -i git push --force',
    'sudo env A=b git reset --hard', 'ssh box "cd repo && git reset --hard"',
    'ssh box git push --force', 'eval "git reset --hard"', "eval 'git push -f'",
    # configuration, whatever the key or the route
    'git config alias.co checkout', 'git config pull.rebase true', 'git config --edit',
    'git config --add remote.origin.fetch x', 'git config --replace-all a.b c',
    'git config --remove-section branch.x', 'git config set user.name x', 'git config unset a.b',
    'git config --unset core.hooksPath', 'git -c alias.x=reset x', 'git -c pull.rebase=true pull',
    'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x',
    'env GIT_CONFIG_GLOBAL=/tmp/c git commit -m x', 'export GIT_CONFIG_NOSYSTEM=1',
    # spellings the parse would otherwise hide: they fail closed
    'git push origin {-f,main}', 'git reset {--hard,HEAD}', "$'git' reset --hard",
    "$'\\x67it' reset --hard", "$'\\147it' push --force", "git reset $'\\q' --hard",
    "env -S 'git reset --hard'", "env --split-string='git push --force'",
    "env -S'git clean -fd'", 'git push origin -- +main', "g''it reset --hard",
    'eval ' * 10 + 'git status',
]

ALLOW = [
    'git status', 'git diff --stat', 'git log --oneline -5', 'git fetch origin',
    'git add src/a.py', 'git add -u', 'git add -p src/a.py', 'git commit -m "Fix the parser (#12)" -- src/a.py',
    'git commit -m "never use git reset --hard or git push --force here"',
    'git commit -m "explain add -A and --no-verify in the docs" -- docs/x.md',
    'git commit --amend -m x', 'git push origin main', 'git push origin --delete agent/12-x',
    'git -C /tmp/x push origin main', 'git checkout main', 'git checkout -b agent/12-x', 'git switch main',
    'git restore --staged a.txt', 'git stash push -m why -- a.txt', 'git stash list',
    'git merge --ff-only --no-autostash --no-overwrite-ignore abc123', 'git merge --no-ff abc123',
    'git revert abc123', 'git tag v1', 'git branch -d agent/12-x', 'git branch --show-current',
    'git worktree add ../wt -b agent/12-x main', 'git worktree list', 'git worktree prune',
    'git reset -q -- a.txt', 'git reset --soft HEAD~1', 'git config --get user.name', 'git config --list',
    'git gc', 'git reflog', 'git update-ref refs/heads/x abc', 'git rev-parse --git-path hooks',
    'grep -rn "git reset --hard" docs', 'echo "git push --force"', 'ls -la', 'cargo test',
    'python3 tests/git_guard.py', 'gh issue comment 12 --body "do not git rebase"',
    # here-document bodies are data unless a shell or an interpreter reads them
    'git commit -F - -- a.txt <<EOF\nRemove git reset --hard from the notes\n\ngit clean -fd was wrong\nEOF',
    'git commit -m "$(cat <<\'EOF\'\nExplain why git push --force is forbidden (#18)\n\nIt isn\'t safe.\nEOF\n)" -- a.md',
    'cat > notes.md <<EOF\ngit rebase main\ngit reset --hard\nEOF',
    "gh issue comment 1 --body-file - <<'EOF'\ngit checkout -- . destroyed the work\nEOF",
    'gh issue comment 1 --body \'ran `git rebase main` here\'',
    'git status \\\n  --short',
    'echo "git status" | bash', 'bash tools/run.sh', 'gh config get git_protocol', 'gh alias list',
    'cat <<< "git reset --hard"',
    # reading is not changing; printing is not running
    'git config --global --list', 'git config --global --get user.name', 'git config user.name',
    'git config get user.name', 'git config -l', 'git rebase --help', 'git help rebase', 'git push -h',
    'python3 -c "print(\'git reset --hard\')"', "node -e \"console.log('git push --force')\"",
    'git pull --ff-only', 'git pull --rebase=false', 'git pull --recurse-submodules',
    'git checkout -b agent/12-x main', 'git checkout --detach abc123', 'git checkout -t origin/x',
    'git switch -c agent/12-x', 'git switch --detach abc123', 'git worktree add ../wt main',
    'git add ../other/a.py', 'git add "*.md"', 'git merge --no-verify-signatures abc',
    'git branch -m old new', 'git tag -l "v*" --format=x', 'git commit --amend --author=x -m y',
    'timeout 60 git fetch origin', 'ssh box "cd repo && git pull --ff-only"', 'find . -name git',
    'echo "$(git status --short)"', 'export GIT_PAGER=cat', 'GIT_EDITOR=true git merge --continue',
    'git show HEAD@{1}', 'git reflog show main@{2}', 'echo ${HOME}', 'eval eval git status',
    "git commit -m $'line1\\nline2' -- a.md", "git log --format='{%h,%s}'",
    'find . -name "*.py" -exec wc -l {} +', "printf $'a\\tb\\n'",
]


def run(command):
    return subprocess.run([sys.executable, HOOK, '--check', command], capture_output=True, text=True)


def run_hook(command):
    event = {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'tool_input': {'command': command}}
    return subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True)


failures = []
for command in BLOCK:
    r = run(command)
    if r.returncode != 2 or 'Blocked by the git guard' not in r.stderr:
        failures.append('NOT BLOCKED: ' + command)
for command in ALLOW:
    r = run(command)
    if r.returncode != 0:
        failures.append('WRONGLY BLOCKED: %s  (%s)' % (command, r.stderr.strip()[:80]))
if run_hook('git reset --hard').returncode != 2:
    failures.append('hook contract: a forbidden command on stdin must exit 2')
if run_hook('git status').returncode != 0:
    failures.append('hook contract: an ordinary command on stdin must exit 0')
event = {'tool_name': 'shell', 'tool_input': {'command': ['git', 'reset', '--hard']}}
if subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True,
                  text=True).returncode != 2:
    failures.append('hook contract: a forbidden command given as a list must exit 2')
event['tool_input']['command'] = ['git', 'commit', '-m', 'mention git reset --hard']
if subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True,
                  text=True).returncode != 0:
    failures.append('hook contract: an ordinary command given as a list must exit 0')
if run('git commit -m "an unclosed quote').returncode != 0:
    failures.append('an input the guard cannot parse must not block')
if subprocess.run([sys.executable, HOOK], input='not json', capture_output=True, text=True).returncode != 0:
    failures.append('hook contract: unreadable input must not block')
if subprocess.run([sys.executable, HOOK], input='[]', capture_output=True, text=True).returncode != 2:
    failures.append('hook contract: JSON that is not an object must block')
long_git = 'git status ' + 'x' * 40000
if run(long_git).returncode != 2:
    failures.append('a command over MAX_INPUT that may run git must block')
if run('echo ' + 'x' * 40000).returncode != 0:
    failures.append('a long command without git must pass')
started = time.time()
slow = run('git push x ' + 'a ' * 4300 + "# it's\ngit reset --hard")  # shlex cannot parse it
if slow.returncode != 2 or time.time() - started > 3:
    failures.append('the unparsable 9 KB case must block within 3 s (took %.1f s)'
                    % (time.time() - started))

if failures:
    print('\n'.join(failures)); sys.exit(1)
print('OK: %d blocked, %d allowed, hook contract holds' % (len(BLOCK), len(ALLOW)))
