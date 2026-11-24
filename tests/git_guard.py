#!/usr/bin/env python3
"""Checks the guards plugin's pre_tool_git_guard.py: python3 tests/git_guard.py.

BLOCK lists commands the core rules' §Git forbids, in the spellings the Codex prefix rules cannot see
(tests/codex_policy.py GAPS) and inside wrappers. ALLOW lists everyday commands, including commit
messages that merely mention a forbidden command, which must pass. The hook contract (JSON on
stdin, exit 2 to block) is exercised for one case of each kind. Under `--claude` (Claude Code,
#33) ASK lists what the user approves per call (exit 3 with --check, "ask" on stdout as a hook),
CLAUDE_PASS commits whose message names an asked command, and every BLOCK stays blocked.
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
    # brace expansion is still blocked when git is the command, in any spelling
    '/usr/bin/git push origin {-f,main}', 'env A=b git reset {--hard,HEAD}',
    'cd repo && git push {origin,upstream} +main', 'GIT reset {--hard,HEAD}',
]

ALLOW = [
    'git status', 'git diff --stat', 'git log --oneline -5', 'git fetch origin',
    'git add src/a.py', 'git add -u', 'git add -p src/a.py', 'git commit -m "Fix the parser (#12)" -- src/a.py',
    'git commit -m "never use git reset --hard or git push --force here"',
    'git commit -m "explain add -A and --no-verify in the docs" -- docs/x.md',
    'git commit --amend -m x', 'git push origin main', 'git push origin --delete agent/12-x',
    'git -C /tmp/x push origin main', 'git checkout main', 'git checkout -b agent/12-x', 'git switch main',
    'git stash push -m why -- a.txt', 'git stash list',
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
    # brace expansion without git as a command word: words that merely contain git or gh
    'mkdir -p src/{high,low}', 'cp night.txt{,.bak}', 'mkdir -p .github/{workflows,ISSUE_TEMPLATE}',
    'touch {highlight,digit}.md', 'mv my-git-notes.{txt,md}', 'ls ~/.gitconfig.d/{a,b}',
    # a commit message is never a flag (#33), also attached or flag-shaped
    'git commit -mnote', 'git commit -m "--no-verify"', 'git commit -m "-n is refused now"',
    'git -C /r commit -q -m "a clean step: push, rebase, reset --hard, add -A"',
    'git commit -F msg.txt -- a.md', 'git log --grep --no-verify', 'git -C /r log --grep clean',
    'git -C /r commit -uno -m x -- a.md', 'git commit -uall -m x', 'git commit -Sabc -m x',
    'git -C /r commit -m "fix: don\'t push --force" -- a.md # it\'s', 'git commit -m "#33 note"',
    'git commit --allow-empty -m "--all of it"', 'git commit --message "--amend" -- a.md',
    'git status # {a,b} is not expanded in a comment', 'echo ${#x} && git status',
]
# a shell comment with an apostrophe once hid these from the parser (#33)
BLOCK += ["git -C /r stash drop # don't", "git -C /r tag -d v1 # it's gone",
          "git -C /r worktree remove /w # it's landed", "git -C /r add -A # don't",
          "git -C /r commit -am x # it's", "git -C /r update-ref -d refs/x # it's",
          "git -C /r config core.hooksPath /dev/null # don't",
          "# don't\necho \"$(git -C /r clean -fd)\"", "echo hi # it's\necho \"`git -C /r stash drop`\"",
          "echo hi # it's\nx=\"$(git -C /r reset --hard)\"",
          "# it's\ngit -C /r log --format=\"$(git -C /r tag -d v1)\"",
          'git commit -m x --no-verify # a message is not this flag', 'git commit -nm x',
          'git commit --all -m x', 'git -C /r commit -q --all -m "a clean step"',
          # the review of #33: quoting starts over inside $(…) and backticks; <<\EOF opens a
          # here-document; an alias still cannot skip a hook; an option value is no subcommand
          'echo "$(echo \'"\')\' # " ; git -C r clean -fdx',
          'echo "$(echo \'"\')\' # " ; git -C r reset --hard',
          'echo "`echo \'"\'`\' # " ; git -C r clean -fdx',
          "cat <<\\EOF\n'\nEOF\necho ' # ' ; git -C r clean -fdx",
          'git ci --no-verify -m x', 'git -C r ci --no-verify -m x',
          'git -C r --attr-source HEAD clean -fdx', 'git --attr-source HEAD reset --hard',
          'git --some-new-option HEAD clean -fdx', 'git -C r --no-pager clean -n',
          # a comment inside backticks ends at the closing backtick (second review)
          'echo `echo a #b` ; git -C r clean -fdx', 'x="`echo a # b`"; git -C r reset --hard',
          # third review: an escaped character before `#`, an escaped backtick in a backtick
          # comment; the removed rest of a line is judged too, so these hold whatever the scanner
          # reads (#33, the approach approved 2026-11-23)
          'echo \\`#a ; git -C r clean -fdx', 'echo \\)#b ; git -C r clean -fdx',
          'echo `echo a #x \\` #z` ; git -C r clean -fdx',
          # the accepted cost: a comment that names a forbidden git command is refused
          'git status # then git reset --hard',
          # more unknown options than the guard reads both ways
          'git ' + '-q ' * 16 + 'status',
          # fourth review: a `#` right after an escaped character is a word, not a comment, so
          # a quote after it spans lines; also after a line continuation (`a\\<newline>#`)
          "echo a\\ #'\n'; git -C r clean -fdx; echo '\n\\ #'",
          "echo a\\ #'\n'; git -C r reset --hard; echo '\n\\ #'",
          "echo a\\)#'\n'; git -C r clean -fdx; echo '\n\\)#'",
          "echo a\\`#'\n'; git -C r clean -fdx; echo '\n\\`#'",
          "echo a\\\n#'\n'; git -C r clean -fdx; echo '\n\\\n#'",
          # restore --staged drops staged changes; as in the Codex rules and `git restore *`
          'git restore --staged a.txt', 'git -C r restore --staged a.py', 'git restore -S a.txt',
          # fifth review: a backslash-newline is joined only where the shell joins it (not after
          # an escaped backslash, not in a comment); a quoted `)` does not end "$(…)"; `<<` in
          # arithmetic is a shift; a here-document delimiter is the whole word
          "echo a\\\\\n#'\ngit -C r clean -fdx\n#'", "echo a\\\\\n#'\ngit -C r stash drop\n#'",
          "# trailing backslash \\\ngit -C r reset --hard", "echo C:\\\\\ngit -C r reset --hard",
          "echo \"$(echo ')' ; git -C r stash drop)\"",
          "echo $((1<<X))\n# it's\ngit -C r stash drop\n# isn't",
          "(( y = 1 << X ))\n# it's\ngit -C r stash drop\n# isn't",
          "cat <<E\\OF\nx\nEOF\n# it's\ngit -C r clean -fdx\n# isn't",
          # sixth review: a redirection is no word of the command; the commands before an open
          # quote or a trailing backslash run
          '2>&1 git -C r stash drop', 'git -C r 2>&1 stash drop', 'git 2>&1 -C r clean -fd',
          'git -C r >/dev/null reset --hard', 'git -C r &>log clean -fd',
          'git -C r stash drop<<E\nE', "git -C r stash drop\necho '", 'git -C r stash drop\n\\']
# Claude Code (--claude): exit 3 asks the user, 0 passes, 2 blocks (a block beats an earlier ask)
ASK = ['git push origin main', 'git -C /r push origin main', 'git -C /r commit --amend --no-edit',
       'git update-ref refs/heads/x HEAD', 'git -C /r remote add up https://x', 'ssh box git push',
       'timeout 60 git -C /r push', "git -C /r push origin main # it's ready",
       'git -C /r remote set-url origin https://x', 'git -C /r remote rename a b',
       'git -c user.name=x -C /r commit -m x --amend', 'bash -lc "git -C /r push"',
       'echo "$(echo \'"\')\' # " ; git -C r push origin main',
       'git -C r --attr-source HEAD push origin main', 'git --some-new-option x push',
       'echo `echo a #b` ; git -C r push origin main',
       'echo `echo a #x \\` #z` ; git -C r push origin main', 'echo \\`#a ; git -C r push',
       "echo a\\ #'\n'; git -C r push origin main; echo '\n\\ #'",
       "echo hi # see C:\\\ngit -C r push origin main",
       "echo \"$(echo ')' ; git -C r push origin main)\"",
       "cat <<E\\OF\nx\nEOF\n# it's\ngit -C r push origin main\n# isn't",
       'git -C r 2>&1 push', 'git -C r 2> err.txt push origin main',
       'git -C /r commit -m "an open quote']  # what the guard cannot read is asked
CLAUDE_PASS = ["# don't\ngit -C /r commit -F - <<'EOF'\nit's done # here\nEOF",
               'git -C /r commit -m "push it, then --amend"', 'git -C /r commit -m "--amend"',
               'git log --grep push', 'git -C /r remote -v', 'git -C /r status',
               'git -C /r commit --allow-empty -m "push, clean, update-ref"', 'git push --help',
               'git -C /r commit -m "$(echo \'a "clean" step\')" # don\'t push it', 'git --no-pager log -1',
               "cat <<\\EOF\nit's # push\nEOF", 'git -P diff', 'git -C r -P log --grep clean',
               # quotes nested in "$(…)"; a comment with many `#` words is no nesting
               'git -C r commit -m "$(echo "don\'t")"', 'git -C r commit -m "$(echo "a `b` c")" -- a.md',
               'git -C r status ' + ' '.join('#w%d' % k for k in range(12)) + ' git',
               "git -C r commit -m x -- a.md # it's (fine)", 'echo a\\ #b && git -C r status',
               # a comment's apostrophe and one in a here-document body are no quote pair
               "git -C r add a.md # don't forget\ngit -C r commit -F - <<'EOF'\nDon't use --force\nEOF",
               "git -C r add a.md # don't forget\ngit -C r commit -F - <<'EOF'\n"
               "Docs: don't run git clean -fdx\nEOF",
               'git -C r status 2>&1 | tail -3', 'git -C r log --oneline >/tmp/log.txt',
               'git -C r commit -m "a > b, 2>&1" -- a.md']
# a real comment with an open quote runs nothing; asked only when it names an asked command
CLAUDE_PASS += ["ls  # what's in the git dir", "git -C r log -1  # don't rewrite git history"]
ASK += ['echo `date` # it\'s ; git push',  # the accepted cost: reword the comment
        # seventh review: a case pattern's `)` ends $(…) for the scanner, the rest after its `#`
        # holds a quote the shell had open; the plain search of that rest still finds the git
        'echo "$(case x in a) echo " #"; echo \'"\'; esac)"; git commit --amend -m x']
BLOCK += ['echo "$(case x in a) echo " #"; echo \'"\'; esac)"; git push --force',
          'echo "$(case x in a) echo " #"; echo \'"\'; esac)"; git -C r reset --hard',
          # a redirection's target is any word: a file after >&, a substitution
          'git >&f reset --hard', 'git >$(echo f) push --force', 'git 2>`echo f` -C r reset --hard']
# eighth review: a target's word reader knows an escaped backtick, $(…) and `…` inside double
# quotes and ${…}; a target it cannot close leaves the rest of the text to be judged
BLOCK += ['git >`whoami\\`\\`` reset --hard', 'git 2>`whoami\\`\\`` -C r push --force',
          'echo hi >`whoami\\`\\``; git reset --hard',
          'echo hi 2>`whoami\\`\\``\ngit -C r push --force origin main',
          "git >`echo '\\`'` reset --hard", 'git >&`whoami\\`\\`` clean -fdx',
          'git >"$(echo "x y")" reset --hard', 'git >"$(echo "\'")" reset --hard',
          'echo hi >"$(echo "\'")"; git reset --hard', 'git >${x:-)} reset --hard',
          'git >"`echo f`" reset --hard', 'git >&$(echo 1) push --force']
ASK += ['git >`whoami\\`\\`` push origin main', 'ls >`whoami\\`\\`` && git push',
        'git >"$(echo "x y")" push', 'git >&`echo 1` push']
# ninth review: within "${…}" a quote is a character (zsh, dash); a target that does not close
# ends at the next blank, as before word_end
BLOCK += ['git -C r 2>"${LOG:-it\'s.log}" push --force', 'git -C r 2>"${LOG:-it\'s.log}" reset --hard',
          'git -C r 2>"${LOG:-it\'s.log}" stash drop', 'git -C r <<${ stash drop']
ASK += ['git -C r >"${x:-\'}" push']
CLAUDE_PASS += ['git -C r log 2>"${LOG:-it\'s.log}"', 'git -C r log > "${TMPDIR:-/tmp}/log"']
# the belt (Igor, 2026-11-24, "structureel vangnet"): a git command without a plain subcommand
# word has every subcommand word after a git judged; the -C forms were denied by main's rules
BLOCK += ['echo `echo \\`git stash drop\\``', 'git -C r < <(echo) stash drop',
          'git -C r <<<x stash drop', 'git -C r >$[ 1 ] stash drop', 'git $(true) stash drop',
          'git -c a.b=`:`#x stash drop', 'git "$x" -C r reset --hard', 'git ${s:-} clean -fdx',
          '(git $(true) stash drop)', 'git `true` push --force origin main']
ASK += ['echo `echo \\`git -C r push\\``', 'git -C r < <(echo) push', 'git -C r <<<x push',
        'git $(true) push', 'git "$x" commit --amend -m x']
CLAUDE_PASS += ['git "$cmd" --version', 'git $(echo status) --short', 'git', 'git --version',
                'git "$@"', 'git -C "$repo" log --oneline -5', 'git $sub commit -m "push it" -- a.md']
CLAUDE_PASS += ['git -C r log >"$out" 2>&1', 'git -C r log 2>"$(mktemp)"', 'git -C r log >&"$fd"',
                'git -C r log >`mktemp` 2>&1 && echo ok', 'git -C r diff > >(tee d.txt)',
                'git -C r log >${out:-x.txt}', "git -C r log >'a b.txt' 2>&1"]

# The strict reader (#33, the design of 2026-11-24): exact where bash, zsh and sh read a text the
# same, the former rules (net) from the first construct it does not know. The six misreads the
# module docstring once named, each with a command the old scanner took for a here-document body:
BLOCK += ['echo ${x:-<<E}\ngit -C r stash drop\nE', 'echo $[1<<E]\ngit -C r stash drop\nE',
          'echo $(( ((((1<<E)))) ))\ngit -C r stash drop\nE',
          'echo $(cat <<E)\ngit -C r stash drop\nE', 'x=$(cat <<E\n)\ngit -C r stash drop\nE',
          'cat <<E\nx\\\nE\ngit -C r stash drop\nE',
          'echo "$(case x in a) echo hi;; esac)"; git -C r stash drop',
          'echo $(case x in a) echo hi;; esac) git -C r stash drop',
          # the classes of the tenth review: a redirection in or glued to a word, a
          # substitution of several commands, a default value, an empty substitution in a word,
          # zsh's >!, a continuation inside `git`, trap, coproc
          'git $(true; true) -C r stash drop', 'git -C r stash>/dev/null drop',
          'git>/dev/null -C r stash drop', 'git -C r stash 2>&1 drop', 'git -C r ${x:-stash} drop',
          'git -C r st$()ash drop', 'git -C r >! out stash drop', 'git -C r >>| out stash drop',
          'g\\\nit -C r stash drop', 'git -C r sta\\\nsh drop', "trap 'git -C r stash drop' EXIT",
          'coproc git -C r stash drop', 'time git -C r stash drop', '{ git -C r stash drop; }',
          # found by running random texts in bash 3.2, zsh and dash with a git that logs its
          # words: a word that may be no word, an unknown part glued to `git`, a carriage
          # return (a character of a word), sh's reading of `&>`, bash's `>&-`, zsh's `-` and
          # its `}` that ends a word, a redirection glued to `git`
          'git stash "$@" drop', 'git stash $x drop', '$(true)git stash drop',
          '${x:-}git -C r clean -fd', 'git>| --hard\rgit -C r clean -fd',
          '&> \r git -C r commit -m msg --no-verify;', 'x &> out git -C r clean -fd',
          '>& -git stash drop', '- git -C r commit -m msg --no-verify',
          'git>!2>git-C rdone commit -m msg --no-verify', 'git<<EOF-C $r $(true) push --force',
          "${x:-}git stash <<'EOF' drop git commit[[", 'git -C r ${x:-}clean a[-fd x -fd',
          '{ git push origin -fd} ; echo 2', 'git `true` -c core.hooksPath=/dev/null commit -m x',
          # bash reads a[…]= to its `]` on its own: no comment, no here-document inside it
          "a[1 #'\n']=x; git -C r clean -fd; echo '\n'", 'a[1<<E]=x\ngit -C r clean -fd\nE',
          '[[ a << E ]]\ngit -C r clean -fd\nE', 'if [[ a << E ]]; then :; fi\ngit -C r clean -fd\nE',
          # bash 3.2 (macOS /bin/sh) ends a $(…) by counting parentheses and quotes, without
          # knowing the here-document in it: measured, this body runs its command there
          'echo "$(cat <<\'EOF\'\nx)" ; git -C r clean -fd ; echo "$(echo y\nEOF\n)" end',
          'git -C r commit -m "$(cat <<\'EOF\'\nx)" ; git -C r stash drop ; echo "$(echo y\nEOF\n)"',
          # a here-document body runs its substitutions unless the delimiter is quoted
          'cat <<EOF\n$(git -C r stash drop)\nEOF', 'cat <<EOF\n`git -C r clean -fd`\nEOF',
          # a backslash ends no comment; a word with a literal part is a word; "$@" glued
          'echo a #bash\\\ngit -C r clean -fd2>&1', 'git $(true)stash $(true) drop  << EXIT',
          'git -C fircommit >&-m msg "$@"--no-verify']
ASK += ['git -C r >! out push', 'git $(true; true) -C r push', "trap 'git -C r push' EXIT",
        'git -C r pu\\\nsh origin main', 'x &> out git -C r push', '$(true)git -C r push']
CLAUDE_PASS += [
    # a here-document is data, also inside $(…): parentheses in pairs, an apostrophe that no
    # later quote closes, a `#`
    'git -C r commit -m "$(cat <<\'EOF\'\nA clean step (#33): stash drop, push --force\n\n'
    'It isn\'t a rebase.\nEOF\n)" -- a.md',
    'git -C r commit -F - <<\'EOF\'\nrebase, clean and reset --hard explained (#33)\nEOF',
    'git -C r commit -m "$(cat <<\'EOF\'\nSee #12 (clean) and "push"\nEOF\n)" -- a.md',
    'cat <<EOF\nstash drop $x and clean\nEOF', "cat > notes.md <<'EOF'\n$(git clean -fd)\nEOF",
    # exact words: a rule's word as a value, in another command, after a certain separator
    'git -C r log --grep clean', 'git -C r status && make clean', 'git -C r log; echo stash drop',
    'git -C "$repo" log --grep clean', 'git -C r status &>/dev/null', 'git -C r log 2>&1 >&-',
    'git -C r show HEAD@{1} -- a.md', 'git -C r log --format="%h %s" -5 | cat',
    'cd "$(git -C r rev-parse --show-toplevel)" && git status',
    'git -C r commit -m "fix \\`clean\\` and \\"push\\"" -- a.md',
    'for f in a b; do git -C r add "$f"; done', 'git -C r log\r\n']
# The independent review of the strict reader (2026-11-24), each measured in bash 3.2, zsh,
# dash or sh with a git that logs its words. The shell deletes a backslash-newline before it
# reads tokens, so one inside a token joins it:
BLOCK += ['git 2\\\n>/dev/null stash drop', 'git stash &\\\n>/dev/null drop',
          '(\\\n(x<<EOF))\ngit stash drop\nEOF\n', 'git stash 1\\\n2>/dev/null drop',
          "git stash $\\\n'drop'", 'git $\\\n{x:-stash} drop', 'git stash $\\\nx drop',
          'git stash "$\\\nx" drop',
          # zsh's own syntax; a descriptor of two digits (a word in zsh and sh); `+=`
          '{ true } always { git stash drop }', 'repeat 2 git stash drop',
          'repeat 2 do git stash drop; done', 'coproc X { git stash drop; }',
          'git -C 12>/dev/null stash drop', 'git --namespace 12>/dev/null stash drop',
          'a+=x git stash drop', 'a+=x git push --force',
          # an unknown first word that is empty; an expansion whose value the text half fixes
          "$x sh -c 'git stash drop'", "$x eval 'git stash drop'",
          "$(true) bash -c 'git stash drop'", 'git stash ${u:+x} drop', 'git stash ${u+x} drop',
          'gi${u:+x}t stash drop', 'git ${:-stash} drop', '${:-git} stash drop',
          'git ${x::=stash} drop', 'git stash $=x drop', 'git stash $~x drop',
          # a NUL ends a $'…' word in bash and zsh
          "git stash $'drop\\0zz'", "git stash $'drop\\x00zz'", "git $'stash\\0' drop",
          # an expansion inside the word `git`
          '$1git stash drop', '$9git -C r push --force', 'g${x}it stash drop',
          'gi$@t stash drop', 'gi$(true)t stash drop', 'g$()it stash drop', 'g$1it stash drop',
          'gi"$x"t stash drop', 'g$x""it stash drop',
          # a shell's script after other options, from standard input, another shell
          "bash -c -- 'git stash drop'", "bash -c -x 'git stash drop'", "bash -Cc 'git stash drop'",
          "sh -Cc 'git stash drop'", "bash -co pipefail 'git stash drop'",
          "BASH <<'EOF'\ngit stash drop\nEOF\n", "echo 'git stash drop' | bash -s x",
          "echo 'git stash drop' | bash /dev/stdin", "csh -c 'git stash drop'",
          "tcsh -c 'git stash drop'", "env -u git sh -c 'git stash drop'",
          "find . -name git -o -exec sh -c 'git stash drop' \\;",
          # an uncertain text keeps what the words say: a redirection between them, the
          # environment, gh, an interpreter, a body a piped shell reads
          'echo `date`; git stash 2>/dev/null drop', '[[ -d . ]] && git stash 2>/dev/null drop',
          'echo $((1+1)); git -C r stash 2>&1 drop', 'git stash &>/dev/null drop',
          "cat <<'EOF' | sh\ngit stash >/dev/null drop\nEOF\n",
          'echo $((1)) && GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath '
          'GIT_CONFIG_VALUE_0=/x git commit -m x', 'echo $((1)) && gh alias set co "pr checkout"',
          'echo $((1)) && python3 -c "import subprocess; subprocess.run([\'git\',\'reset\',\'--hard\'])"',
          'git >>| out stash drop', 'git >&| out stash drop', 'git &>| out push --force',
          # [[ … ]] is a command of words; an operator inside it is not read
          '[[ a && git -C r clean -fd ]]', '[[ a =~ b ]] ; git -C r clean -fd',
          # zsh opens a group at `{git`; sh ends a command at the `&` of `&>`
          '\ncoproc {git -C r clean -fd\n-C}', 'x&> --hardgit git -Cr push --force']
# false stops the review measured: a here-document body with backticks or `$(` inside
# "$(cat <<'EOF' …)" (14 of this repository's 391 commit messages), a rule word as a value
# after an uncertain command, [[ … ]] before a commit
CLAUDE_PASS += [
    'git -C r commit -m "$(cat <<\'EOF\'\nDrop `git -C * clean*` and $(x) rules (#33)\n\n'
    'A `git push --force` in a message, ${y} and $[1] too.\nEOF\n)" -- a.md',
    'gh pr create --body "$(cat <<\'EOF\'\nRuns `git push --force` never.\nEOF\n)"',
    '[[ -n x ]] && git grep -n rebase', 'x=$((1+1)); git log --oneline --grep clean',
    '[[ -n x ]] && git log --grep "rebase"', 'echo "`date`"; git branch --list push',
    '[[ -n x ]] && git commit -m "prune"', 'f() { echo hi; }; git commit -m "prune" -- a',
    '[[ -n x ]] && git commit -m "fix (#33): the git restore rule" -- a',
    '[[ -d .git ]] && git status', 'if [[ -f a.md ]]; then git add a.md; fi',
    'git status \\\n  --short \\\n  -b', 'git -C r log && \\\n  git -C r status']
# a text the reader is not certain of reads as the former rules read it: also a message
BLOCK += ['git -C r commit -m "a clean step" -- a.md `date`',
          'echo $((1+1)); git -C r commit -m "do not rebase"']


# The second independent review of the strict reader (2026-11-24): each text ran the refused
# command in bash 3.2, zsh, dash or sh and passed the guard.
BLOCK += [
    # $'…' is read differently by every shell: bash 3.2 knows no \u, an octal number over
    # \377 wraps, zsh knows no \c and ends the word at a NUL, dash reads `$` and a string
    "git branch $'\\u002d\\u002dhelp' -D x", "git tag $'\\u002d\\u002dhelp' -d v1",
    "$'\\547it' stash drop", "git $'\\563tash' drop", "git $'clean\\400' -fd",
    "git $'\\clean' -fd", "git stash $'drop\\0'x", "git $'stash\\0'x drop",
    "git branch $'\\x2d\\x2dhelp' -D x", "git branch $'--help' -D x",
    # zsh's own words after `do`, `then`, `!`, `{`, `if`, and a command after `]]`
    'for x in a; do repeat 1 git stash drop; done', '! repeat 1 git stash drop',
    'if true; then repeat 1 git stash drop; fi', '{ repeat 1 git stash drop; }',
    'if repeat 1 git stash drop; then :; fi', 'while repeat 1 git stash drop; do break; done',
    '! repeat 1 git --no-pager clean -fd', "if [[ a ]] sh -c 'git stash drop'",
    "if [[ a ]] eval 'git stash drop'", "if [[ a ]] env -S 'git stash drop'",
    "if [[ a ]] trap 'git stash drop' EXIT", 'if [[ a ]] git stash drop',
    # a substitution in a here-document body without a quoted delimiter runs
    'cat <<EOF\n$(git --no-pager stash drop)\nEOF', 'cat <<EOF\n$(git --no-pager clean -fd)\nEOF',
    'cat <<EOF\n$(git  -c a=b reset   --hard)\nEOF',
    'cat <<EOF\n${x:-$(git --no-pager stash drop)}\nEOF',
    'cat <<EOF\n`git --no-pager stash drop`\nEOF',
    # sh splits a word at an unquoted $IFS
    'git stash${IFS}drop', 'git${IFS}stash${IFS}drop', 'git$IFS"stash"$IFS\'drop\'',
    'git -C r reset${IFS}--hard',
    # zsh: <-> is a glob for a number, and .(N) a glob qualifier
    'git branch <-> -D x', 'git checkout <-> --force', 'git reset <1-9> --hard',
    'git add .(N)', 'git checkout .(N)', 'git -C r add .(N)', "git add '.'(N)", 'git add .(/)',
    # a short flag with a value attached to its cluster
    'git tag -fmv1.0 v1.0', 'git checkout -fbfix-1', 'git switch -fcfix-1',
    'git push -f4 origin main', 'git push -4f origin main', 'git checkout -Bfix-1 origin/main',
    'git switch -Cfix-1', 'git worktree add -Bfix-1 ../p', 'git pull -r4',
    # unwrapping
    'eval -- git stash drop', "env -vS 'git stash drop'", '$x env -u git git stash drop',
    'env -vSgit -C r stash drop', 'env -iSgit stash drop',
    "$SHELL -c 'git stash drop'", "$0 -c 'git stash drop'", 'env -uGIT_SSH git stash drop',
    "echo 'git stash drop' | bash -o errexit", "echo 'git stash drop' | bash +e",
    "echo 'git stash drop' | zsh -o errexit", ". /dev/stdin <<< 'git stash drop'",
    "echo 'git --no-pager stash drop' | sh",
    # a text that a shell runs although it is not in that shell's own words
    'bash -c "$(cat <<\'EOF\'\ngit stash drop\nEOF\n)"',
    'eval "$(cat <<\'EOF\'\ngit stash drop\nEOF\n)"',
    "source /dev/stdin <<'EOF'\ngit stash drop\nEOF",
    'sh <<< "$(cat <<\'EOF\'\ngit clean -fd\nEOF\n)"',
    # an alias, and history expansion switched on, change how the next lines are read
    "alias x='git stash drop'\nx", "shopt -s expand_aliases\nalias x='git stash drop'\nx",
    'set -o history -o histexpand\necho git stash drop\n!:1-3',
    # The third independent review (2026-11-24). A default or alternative word of a special
    # parameter, and a form of ${…} whose value may be a word of the text
    'git stash ${@:-drop}', 'git reset ${@:---hard}', 'git ${@:-clean} -fd', 'git add ${@:--A}',
    'git commit ${@:--n} -m x', 'git branch ${*:--D} old', 'git tag ${#:+-d} v1',
    'git push ${@:---force}', 'git stash ${!x:-drop}', 'git ${x/#/stash} drop',
    'git stash ${x/#/drop}',
    # $IFS with an operator still expands to its blanks
    'git${IFS%x}stash${IFS%x}drop', 'git stash${IFS:-x}drop', 'git${IFS#x}stash${IFS##x}drop',
    'git stash${IFS:0:1}drop', 'git${IFS?}stash${IFS?}drop',
    # $'…' inside a substitution of an unquoted here-document body
    "cat <<EOF\n$(git stash $'drop')\nEOF", "cat <<EOF\n$(git stash $'dr'op)\nEOF",
    "cat <<EOF\n$(git stash d$'r'op)\nEOF",
    # other names of a shell's standard input
    'echo git stash drop | bash /dev/fd/0', 'echo git stash drop | sh /proc/self/fd/0',
    # an expansion that is nothing inside the word git
    'g`true`it stash drop',
]
ALLOW += [
    'git switch -c fix-1', 'git checkout -b fix', "git tag -a v1 -m 'final'", 'git pull -4',
    'git branch -m old new', 'git checkout -b agent/$n-fix', 'git checkout -b fix/${n%.*}',
    'git -C r commit -m "${msg:-clean}"', 'git log -n ${#} --grep "${1:-clean}"',
    'git -C "${dir:?}" status', 'git fetch origin "${b##*/}"', "git log --format=$'%h\\t%s'",
    "git commit -m $'first line\\nsecond line'",
    "if [[ -f a ]]; then git -C r commit -m 'a clean step'; fi",
    "[[ -n $x ]] && git -C r commit -m 'clean, rebase, reset --hard'",
    'cat <<EOF\nrun $(date) and see git status\nEOF',
    "bash scripts/x.sh && git -C r commit -m 'a clean step'",
    'git -C r commit -m "$(cat <<\'EOF\'\na clean step: $(x) `y` git stash drop\nEOF\n)" -- a.md',
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
# Long inputs go through stdin, as the clients send them: Windows refuses a command line over
# 32,767 characters, so `--check <command>` cannot carry them there.
long_git = 'git status ' + 'x' * 40000
if run_hook(long_git).returncode != 2:
    failures.append('a command over MAX_INPUT that may run git must block')
if run_hook('echo ' + 'x' * 40000).returncode != 0:
    failures.append('a long command without git must pass')
started = time.time()
slow = run_hook('git push x ' + 'a ' * 4300 + "# it's\ngit reset --hard")  # shlex cannot parse it
if slow.returncode != 2 or time.time() - started > 3:
    failures.append('the unparsable 9 KB case must block within 3 s (took %.1f s)'
                    % (time.time() - started))
started = time.time()
ticks = run_hook('git -C r stash drop\n' + '`#`' * 2600 + ' git status')  # sixth review
if ticks.returncode != 2 or time.time() - started > 3:
    failures.append('2,600 backtick comments must block within 3 s (took %.1f s)'
                    % (time.time() - started))
started = time.time()
braces = run_hook('echo ' + '{' * 22000 + '; git -C r clean -fdx')  # the hook timeout is 10 s
if braces.returncode != 2 or time.time() - started > 3:
    failures.append('22,000 braces must block within 3 s (took %.1f s)' % (time.time() - started))
started = time.time()  # the belt reads the text once, however many git commands turn it on
belt = run_hook('git $x status; ' * 2000 + 'git ' + 'stash ' * 4000 + '; git -C r clean -fdx')
if belt.returncode != 2 or time.time() - started > 3:
    failures.append('2,000 unsure git commands must block within 3 s (took %.1f s)'
                    % (time.time() - started))
started = time.time()  # each unclosable target once read to the end would be quadratic
targets = run_hook('>$( ' * 7700 + '; git -C r clean -fdx')
if targets.returncode != 2 or time.time() - started > 3:
    failures.append('7,700 unclosed targets must block within 3 s (took %.1f s)'
                    % (time.time() - started))
# tenth review: each `sh` once had the whole text searched again (17.6 s); and inputs built to
# make the reader, the net or the bash 3.2 count read the text more than once
SLOW = {'3,997 shells': 'sh;:git;' * 3997 + 'git -C r stash drop',
        '2,800 comments': "# it's git\n" * 2800 + 'git -C r stash drop',
        '1,000 here-documents in $(…)': 'echo "$(cat <<\'E\'\n(x\nE\n)"\n' * 1000 + 'git -C r stash drop',
        '6,000 backticks': '`git ' * 6000 + '; git -C r stash drop',
        '10,000 open $(': 'git ' + '$(' * 10000 + ' -C r stash drop',
        # the second, loose reading once read each nesting level again (5.2 s)
        '6,000 open "$(': 'git ' + '"$(a ' * 6000 + '\ngit -C r stash drop'}
# second review: the loose reading read a word that stops at its end again from each of its
# characters (38 s at 32,000 braces, where the hook has 10 s); it now gives up and refuses
SLOW.update({
    '31,900 braces in a word': 'echo ' + '{' * 31900 + '}; git stash drop',
    '1,700 here-documents glued in a word':
        ('git stash drop ' + '$(cat <<EOF\nEOF\n)' * 3000)[:31900],
    "16,000 open $'": ('echo `x`; git stash drop ' + "$'\\" * 16000)[:32000]})
for name, text in SLOW.items():
    started = time.time()
    if run_hook(text).returncode != 2 or time.time() - started > 3:
        failures.append('%s must block within 3 s (took %.1f s)' % (name, time.time() - started))


def run_claude(command):
    return subprocess.run([sys.executable, HOOK, '--claude', '--check', command],
                          capture_output=True, text=True)


for command in ASK:
    if run_claude(command).returncode != 3:
        failures.append('NOT ASKED (--claude): ' + command)
for command in CLAUDE_PASS:
    if run_claude(command).returncode != 0:
        failures.append('WRONGLY STOPPED (--claude): ' + command)
for command in ALLOW:
    # some of these ask under --claude (a push, --amend); none is blocked
    if run_claude(command).returncode == 2:
        failures.append('WRONGLY BLOCKED (--claude): ' + command)
for command in BLOCK + ['git push origin x && git reset --hard']:
    if run_claude(command).returncode != 2:
        failures.append('NOT BLOCKED (--claude): ' + command)
if run('git push origin main').returncode != 0:
    failures.append('without --claude a push is not the guard\'s to ask')
event = {'tool_name': 'Bash', 'tool_input': {'command': 'git -C /r push origin main'}}
out = subprocess.run([sys.executable, HOOK, '--claude'], input=json.dumps(event),
                     capture_output=True, text=True)
try:
    decision = json.loads(out.stdout)['hookSpecificOutput']['permissionDecision']
except (ValueError, KeyError, TypeError):
    decision = None
if out.returncode != 0 or decision != 'ask':
    failures.append('hook contract (--claude): a push must answer "ask" on stdout')
event = {'tool_name': 'mcp__terminal__run_in_terminal', 'tool_input': {'command': 'git -C /r clean -fd'}}
if subprocess.run([sys.executable, HOOK, '--claude'], input=json.dumps(event), capture_output=True,
                  text=True).returncode != 2:
    failures.append('hook contract (--claude): the terminal tool is judged like Bash')

if failures:
    print('\n'.join(failures)); sys.exit(1)
print('OK: %d blocked, %d allowed, %d asked (--claude), hook contract holds'
      % (len(BLOCK), len(ALLOW), len(ASK)))
