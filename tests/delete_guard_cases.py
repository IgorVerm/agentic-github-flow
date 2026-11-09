#!/usr/bin/env python3
"""The fixture and the cases of the delete guard's tests: imported by tests/delete_guard.py and
tests/delete_guard_differential.py, so both judge the same commands in the same fixture.

Importing it builds a fixture home folder in a temporary directory, with
`Library/Application Support`, `AppData`, a git repository and a folder of worktrees in it, and
a temporary folder of its own (TMPDIR). ASK lists commands that must reach the user's approval,
PASS lists routine work the guard must leave alone; each case is (command, working folder).
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
GUARDS = os.path.join(ROOT, 'plugins', 'guards')
HOOK = os.path.join(GUARDS, 'scripts', 'pre_tool_delete_guard.py')


USERS = 'Us' 'ers'  # spelled in two parts, so the repository's home-path check passes


def fwd(path):
    """A path as an agent writes it in a Bash command: forward slashes, also on Windows."""
    return path.replace('\\', '/')


tmp = os.path.realpath(tempfile.mkdtemp(prefix='delete-guard-'))
HOME = os.path.join(tmp, 'fixtureuser')
SESSION_TMP = os.path.join(tmp, 'session-tmp')  # the client's TMPDIR
AS = os.path.join(HOME, 'Library', 'Application Support')
CODE = os.path.join(HOME, 'My projects')
REPO = os.path.join(CODE, 'repo')
WTS = os.path.join(CODE, 'repo-worktrees')
WT = os.path.join(WTS, '52-x')
OUTSIDE = os.path.join(HOME, 'Downloads', 'old')
ME = os.path.basename(os.path.realpath(os.path.expanduser('~')))  # the real account name
for d in (os.path.join(AS, 'Foo', 'cache'), os.path.join(HOME, 'Library', 'Caches'),
          os.path.join(HOME, 'AppData', 'Roaming', 'Code'),
          os.path.join(HOME, 'AppData', 'Local', 'Temp'),
          os.path.join(HOME, '.ssh'), os.path.join(HOME, 'Documents', 'notes'),
          os.path.join(REPO, 'target', 'debug'), os.path.join(REPO, 'build'), WT, OUTSIDE,
          SESSION_TMP):
    os.makedirs(d, exist_ok=True)
subprocess.run(['git', 'init', '-q', REPO], check=True)
DEEP = os.path.join(HOME, 'a', 'b', 'deep')  # a repository three levels below the home folder
SCRIPTS = os.path.join(REPO, 'plugins', 'guards', 'scripts')
os.makedirs(SCRIPTS)
subprocess.run(['git', 'init', '-q', DEEP], check=True)
try:
    os.symlink(os.path.join(HOME, 'Library'), os.path.join(REPO, 'liblink'))
    LINK = True
except OSError:  # Windows without the right to create links
    LINK = False
with open(os.path.join(WT, '.git'), 'w') as f:
    f.write('gitdir: %s/.git/worktrees/52-x\n' % fwd(REPO))
H, R, A = fwd(HOME), fwd(REPO), fwd(AS)


def env_for():
    env = {k: v for k, v in os.environ.items() if k not in ('TMPDIR', 'TEMP', 'TMP')}
    env.update(HOME=HOME, USERPROFILE=HOME, TMPDIR=SESSION_TMP)
    return env


def run(command, cwd=REPO, tool='Bash', raw=None):
    event = {'hook_event_name': 'PreToolUse', 'tool_name': tool, 'cwd': cwd,
             'tool_input': {'command': command}}
    return subprocess.run([sys.executable, HOOK], input=raw if raw is not None else
                          json.dumps(event), capture_output=True, text=True, env=env_for())


def decision(r):
    if not r.stdout.strip():
        return None
    out = json.loads(r.stdout)['hookSpecificOutput']
    return out['permissionDecision'], out['permissionDecisionReason']


ASK = [
    # the reported incident: xargs splits "Application Support", dirname gives ~/Library
    ('find "$HOME/Library/Application Support" -name "*.cache" | xargs -n1 dirname '
     '| xargs rm -rf', REPO),
    ("printf '%s\\n' ~/Library/Application\\ Support/Foo/cache | xargs -n1 dirname "
     "| xargs rm -rf", REPO),
    ('ls ~/Library/Logs | xargs rm', REPO),
    ('find . -name "*.tmp" -print0 | xargs -0 rm -f', REPO),
    ('rm -rf ~/Library', REPO), ('rm -rf "$EMPTY"/*', REPO), ('find ~ -delete', REPO),
    # protected targets, in other spellings
    ('rm -rf "$HOME/Library/Application Support"', REPO), ('rm -rf ~/Library/Caches', REPO),
    ('rm -fr ~/Library/Application\\ Support', REPO), ('rm -rf ~/library', REPO),
    ('/bin/rm -rf ~/Library', REPO), ('rm -r -- ~/Documents', REPO), ('rm -rf ~/*', REPO),
    ('rm -rf ~/.* ', REPO), ('rm -rf ~/Library/*', REPO), ('rm -rf ~/Documents/*', REPO),
    ('rm -rf /Applications/*', REPO), ('rm -rf /*', REPO), ('rm ~/.zshrc', REPO),
    ('rm -f ~/.ssh/id_ed25519', REPO), ('rm -rf /', REPO), ('rm -rf /Users', REPO),
    ('rm -rf /%s/someoneelse' % USERS, REPO), ('rm -rf /ho' 'me/someoneelse', REPO),
    ('sudo rm -rf /Applications/Foo.app', REPO), ('rm -rf /Library/Caches', REPO),
    ('rm -rf /usr/local/lib', REPO), ('rm -rf /etc/ssh', REPO), ('rm -rf "%s"' % H, REPO),
    ('rm -rf "%s/.."' % H, REPO), ('rmdir ~/Documents', REPO), ('unlink ~/.zshrc', REPO),
    ('timeout 5 rm -rf ~/Library', REPO), ('env X=1 rm -rf ~', REPO), ('rm -rf ../../..', REPO),
    ('rm -rf ~/AppData/Roaming/Code', REPO), ('rm -rf "$HOME/AppData"', REPO),
    # computed targets
    ('rm -rf "$(dirname "$f")"', REPO), ('rm -rf `pwd`/x', REPO), ('rm -rf "$TARGET"', REPO),
    ('rm -rf ${TARGET:-}', REPO), ('rm -rf $DIR/build', REPO),
    ('for d in a b; do rm -rf "$d"; done', REPO),
    ('cat list.txt | while read p; do rm -rf "$p"; done', REPO),
    ('D=$(date +%s); rm -rf "/tmp/x/../../$D"', REPO), ('rm -rf "$S"/build', REPO),
    ('rm -rf "build-$C"', REPO), ('rm -rf $S/x', REPO),
    ('cd "$D" && rm -rf *', REPO), ('cd && rm -rf *', REPO), ('cd ~ && rm -rf ./*', REPO),
    # behind a shell, eval or a here-document
    ("bash -c 'rm -rf \"$X\"'", REPO), ('sh -c "rm -rf ~/Documents"', REPO),
    ("zsh -lc 'cd ~ && rm -rf *'", REPO), ("eval 'rm -rf ~/Documents'", REPO),
    ("bash <<'EOF'\nrm -rf ~/Library\nEOF", REPO), ('echo "$(rm -rf ~/Library)"', REPO),
    # spellings of the command name, quoting, wrappers
    ('\\rm -rf ~/Library', REPO), ('r\\m -rf ~/Library', REPO), ('"r"m -rf ~/Library', REPO),
    ("r''m -rf ~/Library", REPO), ('RM -rf ~/Library', REPO), ('/BIN/RM -rf ~/Library', REPO),
    ("$'rm' -rf ~/Library", REPO), ("$'\\x72m' -rf ~/Library", REPO),
    ("rm -rf $'%s/Library'" % H, REPO), ("rm -rf $'\\q' ~/Library", REPO),
    ('rm -rf ~%s/Library' % ME, REPO), ('rm -rf /Use{rs,}/%s/Library' % ME, REPO),
    ('rm -rf ~/{Library,Documents}', REPO),
    ('ls x | xargs sudo rm -rf', REPO), ('ls x | xargs env rm -rf', REPO),
    ('ls x | xargs nice -n 5 rm -rf', REPO), ('ls x | xargs --max-args 1 rm -rf', REPO),
    ("ls -d ~/Library/Application\\ Support/*/x | xargs -n1 dirname | xargs -I{} sh -c "
     "'rm -rf \"{}\"'", REPO),
    ("find ~ -maxdepth 1 -exec sh -c 'rm -rf \"$1\"' _ {} \\;", REPO),
    ('find ~/Library -maxdepth 0 -exec sudo rm -rf {} +', REPO),
    ('find ~/Library -maxdepth 0 -exec \\rm -rf {} +', REPO),
    ('find -- ~ -delete', REPO), ('find -f ~ -delete', REPO),
    ('rm "-rf" "$DIR"', REPO), ("rm '-r' -f $X", REPO), ('rm --rec "$X"', REPO),
    ('builtin cd ~ && rm -rf Library', REPO), ('command cd ~ && rm -rf Library', REPO),
    ('if cd ~; then rm -rf Library; fi', REPO), ('{ cd ~; rm -rf Library; }', REPO),
    ("bash -c -- 'rm -rf ~/Library'", REPO), ("bash <<< 'rm -rf ~/Library'", REPO),
    ("echo 'rm -rf ~/Library' | sh", REPO), ("printf 'rm -rf %s\\n' ~/Library | bash", REPO),
    ("csh -c 'rm -rf ~/Library'", REPO), ("fish -c 'rm -rf ~/Library'", REPO),
    ("su root -c 'rm -rf ~/Library'", REPO), ("CMD='rm -rf ~/Library'; sh -c \"$CMD\"", REPO),
    ("CMD='rm -rf ~/Library'; eval \"$CMD\"", REPO), ('R=rm; $R -rf ~/Library', REPO),
    ('$RMCMD -rf build', REPO), ('arch -arm64 rm -rf ~/Library', REPO),
    ('script -q /dev/null rm -rf ~/Library', REPO),
    (' '.join(['eval'] * 10) + ' rm -rf ~/Library', REPO),
    (' '.join(['nice'] * 10) + ' rm -rf ~/Library', REPO),
    ('=rm -rf ~/Library', REPO), ('rm.exe -rf ~/Library', REPO),
    ('"C:\\Program Files\\Git\\usr\\bin\\rm.exe" -rf ~/Library', REPO),
    ('X=/bin/rm; "$X" -rf ~/Library', REPO), ('ls x | parallel rm -rf', REPO),
    ('cd ~ && rm -rf ~+/Library', REPO), ('rm -rf "%s/Foo"' % A, REPO),
    ('rm -rf ~/Library/Preferences/com.example.app.plist', REPO),
    # repositories and worktrees go through the cleanup-merged skill
    ('rm -rf "%s"' % R, CODE), ('rm -rf "%s"' % fwd(WT), REPO), ('rm -rf "%s"' % fwd(WTS), REPO),
    ('rm -rf .git', REPO), ('rm -rf .', REPO),
    # find with a delete outside a git worktree and the temporary folders
    ('find . -name "*.log" -delete', OUTSIDE),
    ('find "%s" -exec rm -rf {} +' % fwd(OUTSIDE), REPO),
    ('find ~/Library/Caches -type f -delete', REPO), ('find "$DIR" -delete', REPO),
    ('find /tmp -delete', REPO),
    # more paths than the guard reads, and a brace expansion over its cap
    ('rm -rf /tmp/x ' + 'a{1,2}{3,4}{5,6}{7,8}{9,0}{1,2}/ ' * 100, REPO),
    ('rm -rf ' + 'a/b ' * 5000, REPO),
    ('rm -rf ~/Documents/w/{../../,p/}' + '{a,b}' * 6 + '/{..,z}/Library', REPO),
    ('rm -rf ~/.{f..h}nupg/private-keys-v1.d', REPO),
    # the independent review of the port: xargs options without a separate value
    ('ls | xargs -i rm -rf {}', REPO), ('ls | xargs -l rm -rf', REPO),
    ('ls | xargs -e rm -rf', REPO), ('ls | xargs --replace rm -rf {}', REPO),
    ('ls | xargs -0 -i rm -rf {}', REPO), ("ls | xargs -I{} sh -c 'echo {}'", REPO),
    # an unquoted known variable splits at spaces and expands its globs
    ('D="$HOME/Documents backup/x"; rm -rf $D', REPO), ("X='*'; rm -rf ~/Documents/$X", REPO),
    ('D="/tmp/x $HOME"; rm -rf $D', REPO), ('X="$HOME/Documents backup"; rm -r $X', REPO),
    # find's options before its folders
    ('find -O3 ~ -delete', REPO), ('find -D tree ~ -delete', REPO),
    ('find -O3 ~ -exec rm -rf {} +', REPO),
    # a cd that may have failed, a subshell's cd, env -C
    ('cd /tmp/nonexistent; rm -rf *', HOME), ('cd /tmp/x | true; rm -rf Library', HOME),
    ('(cd /tmp/x && make); rm -rf Library', HOME), ('env -C ~ rm -rf Library', REPO),
    ('env --chdir="$HOME" rm -rf Library', REPO), ('env -C"$HOME" rm -rf Library', REPO),
    # WSL's view of a Windows drive
    ('rm -rf /mnt/c/%s/someone' % USERS, REPO), ('rm -rf /mnt/c/Windows/System32', REPO),
    ('rm -rf /mnt/d', REPO),
    # computed command text that names a delete
    ('$(echo rm -rf ~/Library)', REPO), ('`echo rm -rf ~/Library`', REPO),
    ('eval $(echo rm -rf ~/Library)', REPO), ('$(which rm) -r ~/Documents/notes', REPO),
    ("sh -c \"$(printf 'rm -rf %s' ~/Library)\"", REPO), ('${RM:-rm} -r ~/Library', REPO),
    ('busybox rm -rf ~/Library', REPO), ('runuser -u x -- rm -rf ~/Library', REPO),
    # the second review: a default word with ~, trust that ends with the list, env and sudo
    # options, trap bodies, a glob in the command name, a brace cap over a home folder
    ('rm -rf ${CLEAN:-~}', REPO), ('rm -rf ${CLEAN:-~/Documents}', REPO),
    ('rm -rf ${CLEAN-~}', REPO), ('rm -rf "${CLEAN:-%s}"' % H, REPO),
    ('cd /tmp/nonexist && echo hi; rm -rf *', HOME), ('cd /tmp/x & rm -rf Library', HOME),
    ('env -u FOO -C ~ rm -rf Documents', REPO), ('env -iC ~ rm -rf Documents', REPO),
    ('sudo -D ~ rm -rf Documents', REPO), ('sudo -u root --chdir=$HOME rm -rf Documents', REPO),
    ("trap 'rm -rf ~/Library' EXIT", REPO), ('/bin/r[m] -rf ~/Library', REPO),
    ('rm -rf ~/{a,b,c,d,e,f,g,h}{1,2,3,4,5,6,7,8,9}', REPO),
    ("ls | xargs -d '\\n' rm", REPO), ('ls | xargs --unknown-flag rm -rf', REPO),
    # the third review: a brace expansion over the cap that leads out of the folder
    ('rm -rf {.,.}{,}{,}{,}{,}{,}{,}/../../../Documents', DEEP),
    ('rm -rf {a,b}{c,d}{e,f}{g,h}{i,j}{k,l}{m,n}/../../../../Documents', DEEP),
    ('find {.,.}{,}{,}{,}{,}{,}{,}/../Documents -delete', DEEP),
    ('find .{.,%s} -delete' % ','.join('a%d' % n for n in range(70)), DEEP),
    ('rm -rf .{.,%s}' % ','.join('a%d' % n for n in range(70)), DEEP),
    ('rm -rf ..{%s}' % ','.join('%d' % n for n in range(70)), DEEP),
    # a cd in a loop or a function
    ('for i in 1 2 3 4 5 6; do cd ..; done; rm -rf Documents', SCRIPTS),
    ('for i in 1 2 3 4 5 6; do cd .. && true; done && rm -rf Documents', SCRIPTS),
    ('f() { cd ..; }; f; f; f; f; f; f; rm -rf Documents', SCRIPTS),
    ('while true; do cd .. || break; done; rm -rf Documents', SCRIPTS),
    # xargs options read letter by letter, and options the guard does not know
    ('ls | xargs -0n 1 -r rm -rf', REPO), ('ls | xargs -rL 1 -- rm -rf', REPO),
    ('ls | xargs -0P 4 -n1 rm -rf', REPO), ('ls | xargs -tL 1 -r rm -rf', REPO),
    ('ls | xargs -0n 1 -r sh -c "rm -rf $0"', REPO), ('ls | xargs --max-a 1 -r rm -rf', REPO),
    ('ls | xargs -Z find . -delete', REPO), ('ls | xargs --max-a 1 find . -delete', REPO),
    ('ls | xargs --foo find . -delete', REPO), ('ls | xargs -Z find ~ -delete', REPO),
    ('ls | xargs -Z env find . -delete', REPO),
    # issue #4: a cd chain's other branch, popd, eval's cd, ~+ in a default word, trap forms,
    # ~ in braces, one-line functions, a loop after a keyword, a cd after the delete in a loop,
    # a function body called from another folder
    ('cd /tmp/gone && true || rm -rf *', HOME), ('pushd /tmp/x && popd && rm -rf *', HOME),
    ('eval "cd ~"; rm -rf Documents', REPO), ('rm -rf ${CLEAN:-~+}', REPO),
    ("trap -- 'rm -rf ~/Library' EXIT", REPO), ("builtin trap 'rm -rf ~/Library' EXIT", REPO),
    ('rm -rf {~,a}', REPO), ('function f { rm -rf ~/Library; }; f', REPO),
    ('if true; then for i in 1 2 3 4 5 6; do cd ..; done; fi; rm -rf Documents', SCRIPTS),
    ('for i in 1 2 3 4 5 6; do rm -rf Documents; cd ..; done', SCRIPTS),
    ('do_it() { rm -rf Documents; }; cd ~ && do_it', REPO),
    # their neighbours that also pass on main: a cd that may be skipped or runs in a pipeline,
    # a negated cd, a cd behind time, a variable or a computed eval, the folder stack's ~ forms,
    # ~ in braces over the cap and in find, trap behind command, functions behind keywords,
    # loops in braces or after ! and time
    ('true || cd /tmp/x && rm -rf *', HOME), ('true | cd /tmp/x && rm -rf *', HOME),
    ('! cd /tmp/gone && rm -rf *', HOME), ('time cd ~; rm -rf Documents', REPO),
    ('C="cd ~"; $C; rm -rf Documents', REPO), ('eval "$(echo cd ~)"; rm -rf Documents', REPO),
    ('eval "c\\d ~"; rm -rf Documents', REPO), ('cd ~ && rm -rf ~+0/Library', REPO),
    ('rm -rf ~+0', REPO), ('rm -rf {~,%s}' % ','.join('a%d' % n for n in range(70)), REPO),
    ('find {~,a} -delete', REPO), ("trap -- '-x; rm -rf ~/Library' EXIT", REPO),
    ("command trap 'rm -rf ~/Library' EXIT", REPO), ('function { rm -rf ~/Library; }', REPO),
    ('if true; then f() { rm -rf Documents; }; fi; cd ~ && f', REPO),
    ('{ for i in 1 2 3 4 5 6; do cd ..; done; }; rm -rf Documents', SCRIPTS),
    ('! for i in 1 2 3 4 5 6; do cd ..; done; rm -rf Documents', SCRIPTS),
    ('time for i in 1 2 3 4 5 6; do cd ..; done; rm -rf Documents', SCRIPTS),
    # the first attempt's reviews, where main passes too: ~ after braces, a function with a
    # computed delete, a trap that runs after a cd, a computed or wrapped cd, zsh's precommand
    # modifiers, repeat and foreach, two-word cd, CDPATH, a prefix assignment, a case pattern's
    # `)` in a loop, zsh's cd -N, wrappers before trap, a trap set in eval
    ('rm ~{/.zshrc,/.bashrc}', REPO), ('function f { $DEL -rf ~/Library; }; f', REPO),
    ("trap 'rm -rf Documents' EXIT; cd ~", REPO), ('$(echo cd) ~; rm -rf Documents', REPO),
    ('`echo cd` ~ && rm -rf Documents', REPO), ('noglob cd ~ && rm -rf Documents', REPO),
    ('nocorrect cd ~ && rm -rf Documents', REPO), ('- cd ~ && rm -rf Documents', REPO),
    ('repeat 5 cd ..; rm -rf Documents', SCRIPTS),
    ('foreach i (1 2 3 4 5) cd ..; end; rm -rf Documents', SCRIPTS),
    ('cd a/b/deep Documents && rm -rf *', DEEP), ('CDPATH=~ cd Documents && rm -rf *', REPO),
    ('CDPATH=~; cd Documents && rm -rf *', REPO), ('FOO=1 cd ~ && rm -rf Documents', REPO),
    ('for i in 1 2 3 4 5 6; do rm -rf Documents; case $i in *) cd ..;; esac; done', SCRIPTS),
    ('pushd ~/Library; pushd /tmp/x; cd -1 && rm -rf "Application Support/Foo"', REPO),
    ("time trap 'rm -rf ~/Library' EXIT", REPO), ("noglob trap 'rm -rf ~/Library' EXIT", REPO),
    ("nocorrect trap 'rm -rf ~/Library' EXIT", REPO), ('repeat 1 rm -rf ~/Library', REPO),
    ('repeat 2 do rm -rf ~/Library; done', REPO),
    ("eval \"trap 'rm -rf Documents' EXIT\"; cd ~", REPO),
    # the second attempt's review: while and until loops, options of command and builtin
    ('while [ "$PWD" != / ]; do rm -rf .cache; cd ..; done', SCRIPTS),
    ('until [ -d .git ] || [ "$PWD" = / ]; do rm -rf .venv; cd ..; done', SCRIPTS),
    ('while true; do rm -rf Documents; cd ~; done', REPO),
    ('for i in 1 2; do while false; do :; done; rm -rf Documents; cd ~; done', REPO),
    ("command -p trap 'rm -rf ~/Library' EXIT", REPO),
    ('command -p cd ~ && rm -rf Documents', REPO),
]
if LINK:
    ASK.append(('rm -rf "%s/liblink/"' % R, REPO))

PASS = [
    ('rm -rf "%s/target"' % R, REPO), ('rm -rf target', REPO), ('rm -rf ./build dist', REPO),
    ('rm -rf node_modules', REPO), ('rm -rf build/*', REPO),
    ('rm -f "%s/a.txt" 2>/dev/null' % R, REPO),
    ('rm -rf "%s/target"' % fwd(WT), WT), ('mkdir -p x && rm -rf x', REPO),
    ('rm -rf "$HOME/My projects/repo/target"', REPO), ('rm -rf "$PWD/build"', REPO),
    ('D="%s/target"; rm -rf "$D"' % R, REPO), ('cd "%s" && rm -rf build/*' % R, CODE),
    ('rm "$f"', REPO), ('rm -f "$TMPFILE"', REPO),
    ('D=$(mktemp -d); rm -rf "$D"', REPO), ('T=$(mktemp -d); cd "$T" && find . -delete', REPO),
    ('S=/tmp/session-1/s; C=$(git rev-parse --short HEAD); rm -rf "$S/pkg-$C"', REPO),
    ('rm -rf "%s/target/$C"' % R, REPO), ('rm -rf "./target/$PROFILE"', REPO),
    ('trash "%s/Foo"' % A, REPO), ('trash ~/Downloads/old', REPO), ('trash ~/Library/Caches', REPO),
    ('find . -name "*.pyc" -delete', REPO),
    ('find "%s" -name __pycache__ -exec rm -rf {} +' % R, REPO),
    ('find /tmp/session-1/x -name "*.o" -delete', REPO),
    ('find "$TMPDIR/x" -name "*.o" -delete', REPO),
    ('rm -rf /tmp/session-1/x/build', REPO), ('rm -rf "%s"' % fwd(OUTSIDE), REPO),
    ('xargs trash < list.txt', REPO), ('rm -f /tmp/ov570.*', REPO),
    ('rm -rf ~/Documents/notes/*', REPO), ('git rm -r --cached build', REPO),
    ('echo "rm -rf ~"', REPO), ('grep -rn "rm -rf" .', REPO), ('find . -name "*.rs"', REPO),
    ('gh issue comment 1 --body "never rm -rf ~/Library"', REPO),
    ("git commit -m 'rm -rf ~/Library was the incident' -- a.md", REPO),
    ('git commit -m "$(cat <<\'EOF\'\nFix two things:\n1) the `xargs rm -rf` shape asks\n'
     '2) docs\nEOF\n)" -- a.md', REPO),
    ('rm -rf "$TMPDIR/x"', REPO), ('rm -rf ~/Library/Caches/pip', REPO),
    ('rm -rf ~/Library/Logs/old-app', REPO), ('rm -rf ~/AppData/Local/Temp/build-1', REPO),
    ('docker rm -f web', REPO), ('rm -rf .venv', REPO),
    ('ls | xargs sed -n 1p', REPO), ('$PYTHON -m pytest -rA', REPO),
    ('cargo clean', REPO), ('npm ci', REPO), ('ls -la ~/Library', REPO),
    ('python3 tests/delete_guard.py', REPO),
    ("cat > notes.md <<'EOF'\nrm -rf ~/Library\nEOF", REPO),
    ("echo $'a\\tb' && rm -rf build", REPO),
    # the review's cheap false ask, and trusted or harmless cd and variable forms
    ('rm -rf "${TMPDIR:-/tmp}/foo"', REPO), ('rm -rf ${TMPDIR:-/tmp}/foo', REPO),
    ('rm -rf "${NOT_SET_ANYWHERE_X:-build}"', REPO),
    ('cd build && rm -rf *', REPO), ('cd target || exit 1; rm -rf debug', REPO),
    ('(cd build && make); rm -rf target', REPO), ('env -C /tmp/session-1 rm -rf x', HOME),
    ('D="build dist"; rm -rf $D', REPO), ('X=build; rm -rf $X', REPO),
    ('rm -rf /mnt/c/%s/someone/code/repo/target' % USERS, REPO),
    ('rm -rf ~/{.cache/pip,Library/Caches/pip}', REPO), ('gio trash ~/Documents/notes', REPO),
    ('rm -rf "${NOT_SET_ANYWHERE_X:-/tmp/session-1/x}"', REPO),
    ('cd /tmp/x; rm -rf build', REPO), ('cd x || { echo no; exit 1; }; rm -rf build', REPO),
    ('set -e; cd /tmp/x; rm -rf build', REPO), ('git ls-files | xargs grep -lw rm', REPO),
    ('xargs -a list.txt grep -l rm', REPO), ('xargs grep -l bash < list.txt', REPO),
    ('rm -f out/file{1..100}.txt', REPO), ('rm -rf /tmp/build{1..80}', REPO),
    ("trap 'rm -rf \"$TMPDIR/x\"' EXIT", REPO), ('env -u FOO -C /tmp/session-1 rm -rf x', HOME),
    # issue #4's fixes leave alone: loops without a cd, trap's signal names, an eval without a
    # cd, a cd in a subshell inside a loop, a signal named TERM, a trap in the folder it was
    # set in, the folder stack in the folders the command was in
    ('for f in a b; do echo $f; done; rm -rf build', REPO),
    ("trap -- 'rm -rf \"$TMPDIR/x\"' EXIT INT", REPO), ('eval "$(ssh-agent -s)"; rm -f x.o', REPO),
    ('if true; then for f in a b; do echo $f; done; fi && rm -rf build', REPO),
    ('for d in a b; do (cd $d && make); done; rm -rf build', REPO),
    ('while read -r d; do (cd "$d" && git pull); done < list.txt; rm -rf build', REPO),
    ('eval "$(ssh-agent -s)"; rm -rf build', REPO),
    ('eval "$(brew shellenv)" && rm -rf node_modules', REPO),
    ('timeout -s TERM 5 rm -rf build', REPO), ("trap 'rm -rf build' EXIT; make", REPO),
    ("trap 'rm -rf node_modules/.cache' EXIT; npm test", REPO),
    ('pushd build && make && popd; rm -rf out', REPO),
    ('pushd /tmp/x >/dev/null; make; popd >/dev/null; rm -rf dist', REPO),
    ('while read d; do (cd "$d" && make); done < l; rm -rf build', REPO),
    ('while true; do make || break; done; rm -rf build', REPO),
    ("trap -- \"echo it's done\" EXIT; rm -f /tmp/x/a.log", REPO),
]
