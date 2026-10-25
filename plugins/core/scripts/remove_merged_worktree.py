#!/usr/bin/env python3
"""Remove MERGED task worktrees without losing data (the cleanup-merged skill).

Usage: python3 remove_merged_worktree.py [--dry-run] [--no-fetch]
                                         [--approved "<the user's words>"] <worktree>...
       python3 remove_merged_worktree.py --sweep [--dry-run] [--no-fetch]

Run it from the repository's primary checkout, outside the worktrees it removes. Raw
`git worktree remove` deletes ignored files without asking, so the guards refuse it and this
script is the agents' way to remove a worktree. Per worktree, every check must hold, otherwise
the worktree is KEPT and the reasons, files and processes are printed:

  merged    its branch tip (or detached HEAD) is in the default branch: origin's after a fetch
            (refs/remotes/origin/HEAD, else origin/main), or local main in a repo without origin;
            or the tip is exactly the head commit of a merged pull request
            (`gh pr list --head <branch> --state merged`), which covers squash and rebase merges.
            GitHub keeps a merged pull request's commits, so they are not lost with the branch
  clean     `git status --porcelain` is empty, and no index entry hides local edits
            (assume-unchanged or skip-worktree in `git ls-files -v`)
  ignored   every ignored entry PROVES it is regenerable (below); anything else, including data
            no one has generated yet, keeps the worktree
  no strays every commit the worktree's own history records (HEAD, ORIG_HEAD, its HEAD reflog
            and the reflog of a branch that will be deleted) is reachable from a ref that
            survives, or from the merged pull request's head; no per-worktree refs and no git
            operation in progress. A commit made on a detached HEAD, or dropped by a reset or a
            branch recreation, keeps the worktree: give it a branch (`git branch <name> <sha>`)
            if it matters, then rerun. Only a commit that `commit --amend` replaced, and that
            was not restored as a tip since, is exempt
  unlocked  `git worktree list --porcelain` shows no lock
  idle      no other process has an open file or its working directory inside (`lsof`). On
            Windows there is no lsof; Windows itself refuses to delete an open file, and a
            removal that stops halfway is reported

--sweep checks every linked worktree of the repository. A fresh worktree is always "in main", so
a sweep also needs reflog evidence that the branch has commits of its own (a `commit…`,
`cherry-pick`, `revert` or non-fast-forward `merge …` entry). A fresh, fast-forwarded or
detached worktree, or one whose reflog has expired, is kept and named. Kept worktrees are normal
in a sweep; it exits 1 when a removal fails or the default branch cannot be established.

Proof that an ignored entry is regenerable. Default deny: nothing lists known data, so a file
type added to .gitignore later is protected without any change here.
  - a symlink: removal unlinks it and never touches its target;
  - a `.DS_Store` file, or a `.pyc` file;
  - `__pycache__/` holding only `.pyc` files;
  - a directory with a CACHEDIR.TAG carrying the standard signature (bford.info/cachedir) whose
    top level matches a layout measured for its tool. The tag proves only the tool's own output:
      cargo `target/`: CACHEDIR.TAG, .rustc_info.json, an EMPTY tmp/ (tests may keep any data
        there), profile directories and target-triple directories of profiles. A profile holds
        .cargo-lock and other `.cargo-*lock` files; .fingerprint, build, deps, examples and
        incremental holding only cargo's hash-named entries (examples also its uplifted
        binaries); and artifacts proven by a same-size `deps/<stem>-<hash>` copy or by a
        `<stem>.d` naming them (see unproven_uplifts);
      `.pytest_cache/`: CACHEDIR.TAG, README.md, .gitignore, and v/cache/ holding files.
    A declared child (`target/gate/`) is accepted; anything else keeps the worktree;
  - `node_modules/` with a package-manager state file (.package-lock.json, .modules.yaml,
    .yarn-state.yml), a tracked package.json beside it, and only packages, @scopes, symlinks,
    .bin, .cache, .pnpm, .vite and state files at its top level;
  - a pattern in the repo's tracked `.worktree-disposable` AS IT IS ON THE DEFAULT BRANCH, for
    a cache that cannot prove itself (Godot `.godot/`). Every line names who approved it:
      <pattern>  # <who approved> YYYY-MM-DD #<issue>
    A directory pattern ends in `/` and is fully literal: a name at any depth (`.godot/`) or a
    path from the repository root (`target/gate/`). A file pattern is a literal name or
    `*.<ext>`. Anything else (`*`, `*a*/`) is refused. The annotation is typed text: the real
    safeguard is review of every change to that file.
Trust boundary: inside a proven tool folder, the tool's own subtrees are trusted rather than
proven file by file: cargo's build/<crate>-<hash>/out/ (a build script's OUT_DIR),
.fingerprint/ and incremental/ directories, and in node_modules/ each package's contents and
.bin, .cache, .pnpm, .vite. A program that saves user data there loses it.
One walk of the whole worktree also keeps it when it finds a nested repository (a `.git`, or a
bare repository's HEAD, objects/ and refs/) or a directory git could not empty, which would make
`git worktree remove` stop halfway after deleting the worktree's link.

Limit: a process that starts writing ignored files between these checks and the removal is not
seen; the checks run immediately before `git worktree remove`.

--approved waives only the merged check, for work the user decided to abandon; every other
check still holds and the branch is never deleted in that mode.
Removal: `git worktree remove <path>` (never --force), then the local branch is deleted with
`git update-ref -d refs/heads/<branch> <proven tip>`, which refuses if the branch moved since the
check; a branch still checked out in another worktree is kept. The remote branch and the issue
stay with the caller (the cleanup-merged skill). AGENTIC_GITHUB_FLOW_GH, a JSON list, replaces
the `gh` command (tests use it). Exit 0: every worktree removed (with --dry-run: would be);
1: at least one kept; 2: usage error. With --sweep, see above.
"""
import argparse
from fnmatch import fnmatchcase
import json
import os
import re
import shutil
import subprocess
import sys

CACHEDIR_SIGNATURE = b'Signature: 8a477f597d28d172789f06886806bc55'
PACKAGE_STATE = {'.package-lock.json', '.modules.yaml', '.yarn-state.yml'}
NODE_EXTRAS = PACKAGE_STATE | {'.bin', '.cache', '.pnpm', '.vite', '.DS_Store'}
CARGO_TOP = {'CACHEDIR.TAG', '.rustc_info.json', '.DS_Store'}  # regular files
BUILD_SCRIPT_FILES = {'build-script-build', 'invoked.timestamp', 'output', 'root-output',
                      'stderr'}  # measured in build/<crate>-<hash>/, beside the out/ folder
CARGO_PROFILE_DIRS = {'.fingerprint', 'build', 'deps', 'examples', 'incremental'}
PYTEST_TOP = {'CACHEDIR.TAG', 'README.md', '.gitignore', 'v'}
DEPS_ARTIFACT = re.compile(r'^(.+)-[0-9a-f]{16}(\.[^.]+)?$')  # cargo's deps/<stem>-<hash>[.ext]
HASHED = re.compile(r'^.+-[0-9a-f]{16}(\..+)?$')  # cargo's names in deps/, build/, ...
INCREMENTAL = re.compile(r'^.+-[0-9a-z]{13}$')  # cargo's names in incremental/
OWN_WORK = re.compile(r'^(?:commit|cherry-pick|revert)\b|^merge [^:]*: (?!Fast-forward)')
ANNOTATION = re.compile(r'^(\S+)\s+#\s*[^#\s][^#]*?\s+\d{4}-\d{2}-\d{2}\s+#\d+\b')
# a literal directory name or root path; a literal file name or `*.<ext>`
DIR_PATTERN = re.compile(r'^[^*?\[\]]+/$')
FILE_PATTERN = re.compile(r'^(?:[^*?\[\]/]*/)*(?:[^*?\[\]/]+|\*\.[^*?\[\]/.]+)$')


def git(cwd, *args):
    return subprocess.run(['git', '-C', cwd, *args], text=True, capture_output=True)


def declared_patterns(text):
    """(patterns, refused lines) from .worktree-disposable."""
    patterns, refused = [], []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        found = ANNOTATION.match(line)
        pattern = found and found.group(1).lstrip('/')
        if pattern and pattern not in ('/', '*') and (
                DIR_PATTERN.match(pattern) or FILE_PATTERN.match(pattern)):
            patterns.append(pattern)
        else:
            refused.append(line)
    return patterns, refused


def declared(entry, patterns):
    """The pattern that declares this ignored entry disposable, or None."""
    is_dir, path = entry.endswith('/'), entry.rstrip('/')
    for pattern in patterns:
        if pattern.endswith('/') != is_dir:
            continue
        pat = pattern.rstrip('/')
        target = path if '/' in pat else path.rsplit('/', 1)[-1]
        if fnmatchcase(target, pat):
            return pattern
    return None


def tree_problem(tree):
    """What would make `git worktree remove` lose data or stop halfway, found by one walk."""
    errors = []
    for root, dirs, files in os.walk(tree, onerror=errors.append):
        rel = os.path.relpath(root, tree)
        if rel != '.' and ('.git' in dirs or '.git' in files):
            return f'holds a git repository at {rel}/.git'
        if rel != '.' and 'HEAD' in files and {'objects', 'refs'} <= set(dirs):
            return f'holds a bare git repository at {rel}'
        if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
            return f'{rel}/ cannot be emptied (permissions): removal would stop halfway'
    return f'unreadable: {errors[0]}' if errors else None


def is_file(path):
    return os.path.isfile(path) and not os.path.islink(path)


def is_dir(path):
    return os.path.isdir(path) and not os.path.islink(path)


def reraise(error):
    raise error


def has_tag(directory):
    try:
        with open(os.path.join(directory, 'CACHEDIR.TAG'), 'rb') as tag:
            return tag.read(len(CACHEDIR_SIGNATURE)) == CACHEDIR_SIGNATURE
    except OSError:
        return False


def unproven_uplifts(directory, copies, names):
    """Of `names` in `directory`, those not proven to be cargo's uplifted artifacts.

    An artifact (a regular file) is proven by a same-size copy `<stem>-<16 hex>[.ext]` in
    `copies` or by its `<stem>.d`, whose first line cargo starts with the artifact's absolute
    path. A target copied from another checkout keeps the old root, so that path must end in
    `/<directory name>/<artifact>`. A `.d` counts only beside an artifact it belongs to. Every
    folder is unproven, `.dSYM` included (no measured target holds one).
    """
    sizes = {}
    for name in os.listdir(copies) if os.path.isdir(copies) else []:
        found, full = DEPS_ARTIFACT.match(name), os.path.join(copies, name)
        if found and os.path.isfile(full) and not os.path.islink(full):
            sizes.setdefault((found.group(1), found.group(2) or ''), set()).add(
                os.path.getsize(full))

    def regular(name):
        full = os.path.join(directory, name)
        return os.path.isfile(full) and not os.path.islink(full)

    def names_itself(depinfo, artifact):
        try:
            with open(os.path.join(directory, depinfo), encoding='utf-8', errors='replace') as f:
                first = f.readline()
        except OSError:
            return False
        target = first.split(': ', 1)[0] if ': ' in first else ''
        suffix = f'/{os.path.basename(directory)}/{artifact}'.replace(' ', '\\ ')
        return target.startswith('/') and target.endswith(suffix)

    def proven(name):
        if not regular(name) or name.endswith('.d'):
            return False
        stem = name.split('.')[0]
        size = os.path.getsize(os.path.join(directory, name))
        key = (stem.replace('-', '_'), name[len(stem):])
        return (size in sizes.get(key, ()) or
                (regular(f'{stem}.d') and names_itself(f'{stem}.d', name)))

    artifacts = {n for n in names if proven(n)}
    return [n for n in names if not (
        n in artifacts
        or (n.endswith('.d') and regular(n) and any(
            a.split('.')[0] == n[:-2] and names_itself(n, a) for a in artifacts)))]


def unknown_in_profile(directory):
    """Entries of a cargo profile directory that cargo did not demonstrably write, or None.

    Measured on real targets: every entry cargo writes in deps/, build/, .fingerprint/ and
    examples/ ends its stem in 16 hex digits, in incremental/ in 13 base-36 characters;
    examples/ adds uplifted example binaries.
    """
    if not os.path.isfile(os.path.join(directory, '.cargo-lock')):
        return None
    unknown, rest = [], []
    for name in os.listdir(directory):
        full = os.path.join(directory, name)
        if name in CARGO_PROFILE_DIRS and os.path.isdir(full) and not os.path.islink(full):
            entries = os.listdir(full)
            shape = INCREMENTAL if name == 'incremental' else HASHED
            loose = [e for e in entries if not shape.match(e)]
            if name == 'examples':
                loose = unproven_uplifts(full, full, loose)
            if name in ('deps', 'examples'):  # measured: files only
                loose += [e for e in entries if e not in loose
                          and not is_file(os.path.join(full, e))]
            elif name == 'build':  # measured: <crate>-<hash>/ with a fixed set of entries
                for e in entries:
                    inner = os.path.join(full, e)
                    if e in loose:
                        continue
                    if not is_dir(inner):
                        loose.append(e)
                    else:
                        loose += [f'{e}/{x}' for x in os.listdir(inner) if not (
                            (x == 'out' and is_dir(os.path.join(inner, x)))
                            or ((x in BUILD_SCRIPT_FILES or HASHED.match(x))
                                and is_file(os.path.join(inner, x))))]
            else:  # .fingerprint, incremental: cargo's own directories, trusted inside
                loose += [e for e in entries if e not in loose
                          and not is_dir(os.path.join(full, e))]
            unknown += [f'{name}/{e}' for e in loose]
        elif os.path.isfile(full) and not os.path.islink(full) and (
                name == '.DS_Store' or (name.startswith('.cargo-') and name.endswith('lock'))):
            continue
        else:
            rest.append(name)
    return unknown + unproven_uplifts(directory, os.path.join(directory, 'deps'), rest)


def unknown_in_tagged(directory, entry, patterns):
    """Entries of a tagged directory that its tool's known layout does not explain."""
    names = os.listdir(directory)
    if os.path.basename(directory) == '.pytest_cache':
        unknown = [n for n in names if not (
            (n == 'v' and is_dir(os.path.join(directory, n)))
            or (n in PYTEST_TOP and n != 'v' and is_file(os.path.join(directory, n))))]
        v = os.path.join(directory, 'v')
        if is_dir(v):
            unknown += [f'v/{n}' for n in os.listdir(v)
                        if not (n == 'cache' and is_dir(os.path.join(v, n)))]
            cache = os.path.join(v, 'cache')
            if is_dir(cache):
                unknown += [f'v/cache/{n}' for n in os.listdir(cache)
                            if not is_file(os.path.join(cache, n))]
        return unknown
    unknown = []
    for name in names:
        full = os.path.join(directory, name)
        child = f"{entry.rstrip('/')}/{name}" + ('/' if os.path.isdir(full) else '')
        if (name in CARGO_TOP and is_file(full)) or declared(child, patterns):
            continue
        if name == 'tmp' and os.path.isdir(full) and not os.listdir(full):
            continue  # CARGO_TARGET_TMPDIR: tests may keep any data there, so only empty
        inside = unknown_in_profile(full) if os.path.isdir(full) else None
        if inside is None and os.path.isdir(full) and os.listdir(full):
            # a target-triple directory holds only profile directories
            parts = [unknown_in_profile(os.path.join(full, p)) for p in os.listdir(full)]
            if all(part is not None for part in parts):
                inside = [f'{p}/{u}' for p, part in zip(os.listdir(full), parts) for u in part]
        if inside is None:
            unknown.append(name)
        else:
            unknown += [f'{name}/{u}' for u in inside]
    return unknown


def unknown_in_node_modules(directory):
    unknown = []
    for name in os.listdir(directory):
        full = os.path.join(directory, name)
        if os.path.islink(full) or (name in PACKAGE_STATE | {'.DS_Store'} and is_file(full)):
            continue
        if name in NODE_EXTRAS - PACKAGE_STATE - {'.DS_Store'} and is_dir(full):
            continue  # .bin, .cache, .pnpm, .vite: the package manager's and tools' own
        if name.startswith('@') and os.path.isdir(full):
            if all(os.path.islink(os.path.join(full, p))
                   or os.path.isfile(os.path.join(full, p, 'package.json'))
                   for p in os.listdir(full)):
                continue
        elif os.path.isfile(os.path.join(full, 'package.json')):
            continue
        unknown.append(name)
    return unknown


def proof(tree, entry, patterns):
    """(why it may go, None) or (None, why it must stay) for one ignored entry."""
    full = os.path.join(tree, entry.rstrip('/'))
    name = os.path.basename(entry.rstrip('/'))
    if os.path.islink(full):
        return 'a symlink (only the link is removed)', None
    pattern = declared(entry, patterns)
    if pattern:
        return f'declared by `{pattern}`', None
    if not entry.endswith('/'):
        if name == '.DS_Store' or name.endswith('.pyc'):
            return 'generated file', None
        return None, 'not proven regenerable'
    try:
        if has_tag(full):
            unknown = unknown_in_tagged(full, entry, patterns)
            if unknown:
                return None, 'tagged cache also holds ' + ', '.join(sorted(unknown)[:5])
            return 'tagged cache with a known layout', None
        if name == '__pycache__':
            if any(d or any(not f.endswith('.pyc') for f in fs)
                   for _, d, fs in os.walk(full, onerror=reraise)):
                return None, 'holds more than .pyc files'
            return 'bytecode cache', None
        if name == 'node_modules':
            parent = os.path.relpath(os.path.dirname(full), tree)
            manifest = 'package.json' if parent == '.' else f'{parent}/package.json'
            if not PACKAGE_STATE & set(os.listdir(full)):
                return None, 'no package-manager state file'
            if git(tree, 'ls-files', '--error-unmatch', '--', manifest).returncode:
                return None, f'{manifest} is not tracked'
            unknown = unknown_in_node_modules(full)
            if unknown:
                return None, 'also holds ' + ', '.join(sorted(unknown)[:5])
            return 'installed packages', None
    except OSError as error:
        return None, f'unreadable: {error}'
    return None, 'not proven regenerable'


def gh_command():
    """The gh command as a list, or None when gh is not installed."""
    raw = os.environ.get('AGENTIC_GITHUB_FLOW_GH')
    if raw:
        try:
            command = json.loads(raw)
        except ValueError:
            return None
        return command if isinstance(command, list) and command else None
    found = shutil.which('gh')
    return [found] if found else None


def merged_pull_request(primary, branch, tip):
    """(number, problem): a merged pull request whose head commit is exactly `tip`."""
    gh = gh_command()
    if not gh:
        return None, 'gh is not installed, so a squash or rebase merge cannot be proven'
    try:
        result = subprocess.run(gh + ['pr', 'list', '--head', branch, '--state', 'merged',
                                      '--json', 'number,headRefOid', '--limit', '50'],
                                cwd=primary, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f'gh failed: {error}'
    if result.returncode:
        return None, 'gh pr list failed: ' + (result.stderr.strip().splitlines() or ['?'])[0]
    try:
        pulls = json.loads(result.stdout or '[]')
    except ValueError:
        return None, 'gh pr list gave no JSON'
    for pull in pulls:
        if isinstance(pull, dict) and pull.get('headRefOid') == tip:
            return pull.get('number'), None
    return None, None


def sweep_evidence(primary, branch):
    """Why the sweep must keep this branch's worktree, from its reflog; None when it may go.

    A fresh worktree is always in main, so the sweep needs evidence that the branch has commits
    of its own. Commits dropped by a reset or rewrite are caught by stranded_commits.
    """
    log = git(primary, 'reflog', 'show', '--format=%gs', f'refs/heads/{branch}')
    subjects = log.stdout.splitlines()
    if log.returncode or not subjects:
        return 'no reflog evidence (expired or missing)'
    if not any(OWN_WORK.match(subject) for subject in subjects):
        return 'no commits of its own in the reflog (fresh worktree?)'
    return None


def stranded_commits(primary, tree, branch_goes, merged_head=None):
    """(reason to keep or None): commits only this worktree's own history still holds.

    `git worktree remove` deletes the worktree's HEAD reflog, ORIG_HEAD and per-worktree refs,
    and `git branch -d` deletes the branch's reflog. A commit that only those record (made on a
    detached HEAD, or dropped by a reset or a branch recreation) would become unreachable. Every
    old and new id in those reflogs must be reachable from a ref that survives, or from the head
    of the merged pull request (GitHub keeps it); the commit a `commit --amend` replaced is
    superseded, not lost.
    """
    path, branch = tree['path'], tree['branch']
    if git(path, 'rev-parse', '--show-ref-format').stdout.strip() != 'files':
        return 'cannot read reflogs (ref format is not `files`)'
    refs = git(path, 'for-each-ref', '--format=%(refname)', 'refs/worktree', 'refs/bisect',
               'refs/rewritten').stdout.split()
    if refs:
        return 'has per-worktree refs: ' + ', '.join(refs[:5])
    for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'REBASE_HEAD', 'BISECT_LOG',
                   'rebase-merge', 'rebase-apply'):
        if os.path.lexists(git(path, 'rev-parse', '--path-format=absolute', '--git-path',
                               marker).stdout.strip()):
            return f'a git operation is in progress ({marker})'
    logs = [(path, 'logs/HEAD')] + ([(primary, f'logs/refs/heads/{branch}')]
                                    if branch and branch_goes else [])
    ids, amended = set(), set()
    for cwd, name in logs:
        log = git(cwd, 'rev-parse', '--path-format=absolute', '--git-path', name).stdout.strip()
        try:
            with open(log, encoding='utf-8', errors='replace') as handle:
                lines = handle.read().splitlines()
        except FileNotFoundError:
            continue
        except OSError as error:
            return f'cannot read {name}: {error}'
        for line in lines:  # oldest first
            head, _, message = line.partition('\t')
            old, new = (head.split(' ') + ['', ''])[:2]
            ids.update((old, new))
            amended.discard(new)  # restored as a tip: no longer superseded
            if message.startswith('commit (amend)'):
                amended.add(old)
    ids -= amended
    for name in ('HEAD', 'ORIG_HEAD'):  # current tips are never exempt
        tip = git(path, 'rev-parse', '-q', '--verify', f'{name}^{{commit}}')
        if not tip.returncode:
            ids.add(tip.stdout.strip())
    known = subprocess.run(['git', '-C', primary, 'cat-file', '--batch-check'], text=True,
                           input=''.join(f'{i}\n' for i in sorted(ids) if i.strip('0')),
                           capture_output=True)
    commits = [line.split()[0] for line in known.stdout.splitlines()
               if line.split()[1:2] == ['commit']]  # an id already gone has nothing to lose
    if not commits:
        return None
    # for --branches the pattern is relative to refs/heads/ (measured)
    exclude = [f'--exclude={branch}'] if branch and branch_goes else []
    merged = [merged_head] if merged_head else []
    left = git(primary, 'rev-list', *commits, '--not', *merged, *exclude,
               '--branches', '--tags', '--remotes')
    if known.returncode or left.returncode:
        return 'cannot establish which commits stay reachable: ' + left.stderr.strip()[:200]
    lost = set(left.stdout.split())
    stranded = [commit[:12] for commit in commits if commit in lost]
    if stranded:
        return ('commits only this worktree\'s history holds would become unreachable: '
                + ', '.join(stranded[:5]) + (' …' if len(stranded) > 5 else ''))
    return None


def worktrees(primary):
    """[{path, branch, locked, prunable}] from `git worktree list --porcelain`, primary first."""
    out, current = [], None
    for line in git(primary, 'worktree', 'list', '--porcelain').stdout.splitlines():
        if line.startswith('worktree '):
            current = {'path': os.path.realpath(line[9:]), 'branch': None,
                       'locked': None, 'prunable': False}
            out.append(current)
        elif line.startswith('branch refs/heads/'):
            current['branch'] = line[len('branch refs/heads/'):]
        elif line == 'locked' or line.startswith('locked '):
            current['locked'] = line[7:] or 'locked'
        elif line.startswith('prunable'):
            current['prunable'] = True
    return out


def default_ref(primary, fetch):
    """(ref, error): the fetched default branch of origin, else local main/master."""
    if 'origin' in git(primary, 'remote').stdout.split():
        if fetch:
            result = git(primary, 'fetch', '--quiet', 'origin')
            if result.returncode:
                return None, 'git fetch origin failed: ' + result.stderr.strip()
        head = git(primary, 'symbolic-ref', '-q', 'refs/remotes/origin/HEAD').stdout.strip()
        for ref in (head, 'refs/remotes/origin/main'):
            if ref and not git(primary, 'rev-parse', '-q', '--verify', ref).returncode:
                return ref, None
        return None, 'origin has no default branch (refs/remotes/origin/HEAD or origin/main)'
    for ref in ('refs/heads/main', 'refs/heads/master'):
        if not git(primary, 'rev-parse', '-q', '--verify', ref).returncode:
            return ref, None
    return None, 'no main or master branch'


def processes_inside(path):
    """(descriptions, error): other processes with an open file or working directory inside."""
    if os.name == 'nt':
        return [], None  # no lsof; Windows refuses to delete an open file during the removal
    try:
        result = subprocess.run(['lsof', '-nP', '-Fpn'], text=True, capture_output=True)
    except FileNotFoundError:
        return None, 'lsof not found: cannot prove the worktree is idle'
    if result.returncode or not result.stdout:
        return None, f'lsof failed (exit {result.returncode}): cannot prove the worktree is idle'
    pids, pid = set(), None
    for line in result.stdout.splitlines():
        if line.startswith('p'):
            pid = int(line[1:])
        elif line.startswith('n/') and pid != os.getpid():
            name = os.path.realpath(line[1:])
            if name == path or name.startswith(path + os.sep):
                pids.add(pid)
    described = []
    for pid in sorted(pids):
        ps = subprocess.run(['ps', '-o', 'ppid=,etime=,comm=', '-p', str(pid)],
                            text=True, capture_output=True).stdout.split(None, 2)
        if len(ps) == 3:
            orphan = ', orphan' if ps[0] == '1' else ''
            command = os.path.basename(ps[2].strip())
            described.append(f'{pid} ({command}, running {ps[1]}{orphan})')
        else:
            described.append(str(pid))
    return described, None


def check(primary, tree, ref, patterns, approved):
    """(reasons to keep, proofs for what goes, proven tip); no reasons means it may go."""
    path, branch, reasons, proofs = tree['path'], tree['branch'], [], []
    if tree['prunable'] or not os.path.isdir(path):
        return ['its directory is missing: use `git worktree prune`'], proofs, None
    tip = f'refs/heads/{branch}' if branch else git(path, 'rev-parse', 'HEAD').stdout.strip()
    sha = git(primary, 'rev-parse', '-q', '--verify', tip + '^{commit}').stdout.strip()
    merged_head = None
    if branch and (branch in ('main', 'master') or ref.endswith('/' + branch)):
        reasons.append(f'it has the default branch {branch} checked out')
    elif not approved and git(primary, 'merge-base', '--is-ancestor', tip, ref).returncode:
        number, problem = merged_pull_request(primary, branch, sha) if branch else (None, None)
        if number is not None:
            merged_head = sha
            proofs.append(f'branch: its tip is the head of merged pull request #{number}')
        else:
            reasons.append(f'not merged: {branch or tip} is not in {ref}'
                           + (f' ({problem})' if problem else
                              ' and is not the head of a merged pull request'))
    # normal (not all): ignored directories stay collapsed, so `target/` is one entry
    status = git(path, 'status', '--porcelain=v1', '-z', '--untracked-files=normal',
                 '--ignored=traditional')
    flags = git(path, 'ls-files', '-v', '-z')
    if status.returncode or flags.returncode or status.stderr.strip():
        # git status skips an unreadable directory with only a warning; never guess past it
        problem = (status.stderr or flags.stderr).strip().splitlines() or ['failed']
        return reasons + ['git status: ' + problem[0]], proofs, sha
    records = [r for r in status.stdout.split('\0') if r]
    dirty = [r[3:] for r in records if not r.startswith('!! ')]
    dirty += [f'{r[2:]} (hidden by {"skip-worktree" if r[0] == "S" else "assume-unchanged"})'
              for r in flags.stdout.split('\0') if r and (r[0] == 'S' or r[0].islower())]
    if dirty:
        reasons.append('not clean: ' + ', '.join(dirty[:5]) + (' …' if len(dirty) > 5 else ''))
    blocked = []
    for entry in (r[3:] for r in records if r.startswith('!! ')):
        why, problem = proof(path, entry, patterns)
        if problem:
            blocked.append(f'{entry} ({problem})')
        else:
            proofs.append(f'{entry}: {why}')
    if blocked:
        reasons.append('ignored files that are not proven regenerable: ' + ', '.join(blocked[:10])
                       + (f' (+{len(blocked) - 10} more)' if len(blocked) > 10 else ''))
    for problem in (tree_problem(path), stranded_commits(primary, tree, not approved,
                                                          merged_head)):
        if problem:
            reasons.append(problem)
    if tree['locked']:
        reasons.append(f"locked: {tree['locked']}")
    processes, error = processes_inside(path)
    if error:
        reasons.append(error)
    elif processes:
        reasons.append('in use by process ' + ', '.join(processes))
    return reasons, proofs, sha


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('worktrees', nargs='*')
    parser.add_argument('--sweep', action='store_true',
                        help='check every linked worktree of the current repository')
    parser.add_argument('--dry-run', action='store_true', help='check and report; remove nothing')
    parser.add_argument('--no-fetch', action='store_true', help='use origin as last fetched')
    parser.add_argument('--approved', metavar='WORDS',
                        help="the user's words approving removal of unmerged work (waives 'merged')")
    args = parser.parse_args(argv)
    if args.approved is not None and not args.approved.strip():
        print("--approved needs the user's words", file=sys.stderr)
        return 2
    if args.sweep == bool(args.worktrees):
        print('name the worktrees, or use --sweep (not both)', file=sys.stderr)
        return 2
    if args.sweep and args.approved is not None:
        print('--approved names one worktree; it does not combine with --sweep',
              file=sys.stderr)
        return 2
    start = os.path.abspath(args.worktrees[0]) if args.worktrees else os.getcwd()
    top = git(start, 'rev-parse', '--show-toplevel')
    if top.returncode:
        print(f'not a git worktree: {start}', file=sys.stderr)
        return 2
    trees = worktrees(top.stdout.strip())
    primary = trees[0]['path']
    ref, error = default_ref(primary, fetch=not args.no_fetch)
    listed = git(primary, 'show', f'{ref}:.worktree-disposable') if ref else None
    patterns, refused = declared_patterns(listed.stdout if listed and not listed.returncode else '')
    for line in refused:
        print(f'.worktree-disposable: refused (needs "# <who> YYYY-MM-DD #n" and a name): {line}')
    if args.approved:
        print(f'The user approved: "{args.approved.strip()}" (merged check waived, '
              'branches kept)')
    by_path = {t['path']: t for t in trees}
    targets = [t['path'] for t in trees[1:]] if args.sweep else args.worktrees
    kept = removed = failed = 0
    for arg in targets:
        path = os.path.realpath(arg)
        tree, proofs, sha = by_path.get(path), [], None
        if tree is None:
            reasons = ['not a linked worktree of this repository']
        elif path == primary:
            reasons = ['the primary checkout is never removed']
        elif error:
            reasons = [error]
        else:
            reasons, proofs, sha = check(primary, tree, ref, patterns, bool(args.approved))
            if args.sweep and not tree['branch']:
                reasons.insert(0, 'detached HEAD: name it explicitly')
            elif args.sweep:
                evidence = sweep_evidence(primary, tree['branch'])
                if evidence:
                    reasons.insert(0, evidence)
        if reasons:
            kept += 1
            print(f'KEPT {path}: ' + '; '.join(reasons))
            continue
        branch = None if args.approved else tree['branch']
        for line in proofs:
            print(f'  {line}' if line.startswith('branch: ') else f'  ignored {line}')
        if args.dry_run:
            print(f'WOULD REMOVE {path}' + (f' and branch {branch}' if branch else ''))
            continue
        result = git(primary, 'worktree', 'remove', path)
        if result.returncode:
            kept += 1
            failed += 1
            if any(t['path'] == path for t in worktrees(primary)):
                print(f'KEPT {path}: git worktree remove refused: {result.stderr.strip()}')
            else:
                print(f'PARTLY REMOVED {path}: git deleted its worktree link and some files, then '
                      f'failed ({result.stderr.strip()}); the directory is orphaned: ask the user')
            continue
        note = ''
        if branch:
            if any(t['branch'] == branch for t in worktrees(primary)):
                result = subprocess.CompletedProcess([], 1, '', 'checked out in another worktree')
            else:  # deleted against the proven tip: refuses if the branch moved since the check
                result = git(primary, 'update-ref', '-d', f'refs/heads/{branch}', sha)
            note = (f' and branch {branch}' if not result.returncode
                    else f'; branch {branch} KEPT: {result.stderr.strip()}')
            kept += bool(result.returncode)
            failed += bool(result.returncode)
        removed += 1
        print(f'REMOVED {path}{note}')
    verb = 'would be removed' if args.dry_run else 'removed'
    print(f'default branch: {ref or "unknown"}; worktrees {verb}: '
          f'{len(targets) - kept if args.dry_run else removed}; kept: {kept}'
          + (f' (sweep of {len(targets)})' if args.sweep else ''))
    if args.sweep:
        return 1 if failed or error else 0
    return 1 if kept else 0


if __name__ == '__main__':
    sys.exit(main())
