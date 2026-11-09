#!/usr/bin/env python3
"""Checks plugins/issue-chats/scripts/chat_archivable.py in a scratch repository:
python3 tests/chat_archivable.py.

The repository has a bare origin whose default branch is main, and worktrees in each state a
finished chat can leave behind. Every "keep" case is a way archiving a chat could lose work or
take work off the sidebar that is only on this machine (changes, untracked files, a merge in
progress, commits never pushed, a local landing in pull-request mode); every "ok" case is a finished chat that would
otherwise clutter the sidebar for good (the worktree gone, HEAD in the default branch, the
branch pushed, a merge on GitHub seen only after the fetch, a landing on local main in local-main
mode, with the setting or without a remote). Offline: origin is a local folder.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'issue-chats', 'scripts', 'chat_archivable.py')


class ChatArchivable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='chat-archivable-')
        root = os.path.realpath(cls.tmp)
        cls.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                       GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t.invalid',
                       GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t.invalid')
        for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
            cls.env.pop(key, None)
        cls.root = root
        cls.origin = os.path.join(root, 'origin.git')
        cls.repo = os.path.join(root, 'repo')
        cls.git(root, 'init', '-q', '--bare', '-b', 'main', cls.origin)
        cls.git(root, 'init', '-q', '-b', 'main', cls.repo)
        cls.git(cls.repo, 'remote', 'add', 'origin', cls.origin)
        with open(os.path.join(cls.repo, '.gitignore'), 'w') as f:
            f.write('build/\n')
        with open(os.path.join(cls.repo, 'f.txt'), 'w') as f:
            f.write('one\n')
        cls.git(cls.repo, 'add', '.gitignore', 'f.txt')
        cls.git(cls.repo, 'commit', '-q', '-m', 'init')
        cls.git(cls.repo, 'push', '-q', 'origin', 'main')
        cls.git(cls.repo, 'fetch', '-q', 'origin')
        cls.git(cls.repo, 'remote', 'set-head', 'origin', 'main')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def git(cls, cwd, *args):
        return subprocess.run(['git', '-C', cwd, *args], check=True, capture_output=True,
                              text=True, env=cls.env).stdout.strip()

    def worktree(self, name, base='origin/main'):
        path = os.path.join(self.root, 'repo-worktrees', name)
        self.git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/' + name, path, base)
        return path

    def commit(self, wt, text='more\n'):
        with open(os.path.join(wt, 'f.txt'), 'a') as f:
            f.write(text)
        self.git(wt, 'commit', '-q', '-am', 'work')

    def check(self, path, *extra, env=None):
        r = subprocess.run([sys.executable, TOOL, path, *extra], capture_output=True, text=True,
                           env=dict(self.env, **(env or {})))
        return r.returncode, r.stdout.strip()

    def assertOk(self, path, *extra, env=None):
        code, line = self.check(path, *extra, env=env)
        self.assertEqual(code, 0, line)
        self.assertTrue(line.startswith('ok'), line)
        return line

    def assertKeep(self, path, reason, *extra, env=None):
        code, line = self.check(path, *extra, env=env)
        self.assertEqual(code, 1, line)
        self.assertTrue(line.startswith('keep: '), line)
        self.assertIn(reason, line)

    def test_gone(self):
        self.assertIn('gone', self.assertOk(os.path.join(self.root, 'never-made')))

    def test_clean_on_the_default_branch(self):
        wt = self.worktree('clean')
        os.makedirs(os.path.join(wt, 'build'))
        with open(os.path.join(wt, 'build', 'out.o'), 'w') as f:
            f.write('ignored build output\n')
        self.assertIn('in origin/main', self.assertOk(wt))

    def test_changes_and_untracked_files_keep(self):
        wt = self.worktree('dirty')
        with open(os.path.join(wt, 'f.txt'), 'a') as f:
            f.write('unsaved\n')
        self.assertKeep(wt, 'changed or untracked')
        wt = self.worktree('untracked')
        with open(os.path.join(wt, 'new.txt'), 'w') as f:
            f.write('new\n')
        self.assertKeep(wt, 'new.txt')

    def test_untracked_files_hidden_by_configuration_keep(self):
        # status.showUntrackedFiles=no would hide them from a plain `git status --porcelain`
        wt = self.worktree('hidden-untracked')
        self.git(wt, 'config', 'status.showUntrackedFiles', 'no')
        try:
            os.makedirs(os.path.join(wt, 'deep', 'er'))
            with open(os.path.join(wt, 'deep', 'er', 'new.txt'), 'w') as f:
                f.write('new\n')
            self.assertKeep(wt, 'deep/er/new.txt')
        finally:
            self.git(wt, 'config', '--unset', 'status.showUntrackedFiles')

    def test_assume_unchanged_and_skip_worktree_keep(self):
        for flag, name in (('--assume-unchanged', 'assumed'), ('--skip-worktree', 'skipped')):
            wt = self.worktree(name)
            self.git(wt, 'update-index', flag, 'f.txt')
            with open(os.path.join(wt, 'f.txt'), 'a') as f:
                f.write('a change git status does not show\n')
            self.assertEqual(self.git(wt, 'status', '--porcelain'), '', flag)
            self.assertKeep(wt, 'hidden from git status')

    def test_a_folder_without_its_git_link_is_not_judged_by_the_enclosing_checkout(self):
        # a worktree made inside the primary checkout loses its .git link: git would answer for
        # the enclosing checkout, which is clean and on GitHub, and the work inside would go
        inner = os.path.join(self.repo, 'inner-wt')
        self.git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/inner', inner, 'origin/main')
        os.remove(os.path.join(inner, '.git'))
        with open(os.path.join(self.repo, '.git', 'info', 'exclude'), 'a') as f:
            f.write('inner-wt/\n')  # so the enclosing checkout itself stays clean
        self.assertKeep(inner, 'not the top of its own git worktree')
        # outside any checkout, the same folder is no worktree at all
        wt = self.worktree('lost-link')
        os.remove(os.path.join(wt, '.git'))
        code, line = self.check(wt)
        self.assertEqual(code, 1, line)

    def test_commit_not_pushed_keeps_until_the_branch_is_pushed(self):
        wt = self.worktree('ahead')
        self.commit(wt)
        self.assertKeep(wt, 'not on GitHub')
        self.git(wt, 'push', '-q', 'origin', 'agent/ahead')
        self.assertIn('origin/agent/ahead', self.assertOk(wt))
        # a later commit that was not pushed keeps it again
        self.commit(wt, 'later\n')
        self.assertKeep(wt, '1 commit(s) of agent/ahead')

    def test_a_merge_on_github_is_seen_after_the_fetch(self):
        wt = self.worktree('merged')
        self.commit(wt, 'merged\n')
        # someone merges it on GitHub: origin's main moves, nothing here knows yet
        self.git(self.origin, 'fetch', '-q', self.repo, 'agent/merged:main')
        self.assertKeep(wt, 'not on GitHub', '--no-fetch')
        self.assertIn('origin/main', self.assertOk(wt))

    def test_a_deleted_remote_branch_still_counts_as_pushed(self):
        wt = self.worktree('deleted')
        self.commit(wt, 'deleted\n')
        self.git(wt, 'push', '-q', 'origin', 'agent/deleted')
        self.git(self.origin, 'branch', '-D', 'agent/deleted')  # GitHub deleted it after merge
        self.assertIn('origin/agent/deleted', self.assertOk(wt))

    def test_detached_head(self):
        wt = self.worktree('detached')
        self.git(wt, 'switch', '-q', '--detach', 'origin/main')
        self.assertOk(wt)
        self.commit(wt, 'probe\n')
        self.assertKeep(wt, 'detached HEAD')

    def test_operation_in_progress_keeps(self):
        wt = self.worktree('merging')
        self.commit(wt, 'side a\n')
        other = self.worktree('other')
        self.commit(other, 'side b\n')
        subprocess.run(['git', '-C', wt, 'merge', 'agent/other'], capture_output=True,
                       env=self.env)  # conflicts on f.txt
        self.assertKeep(wt, 'in progress (MERGE_HEAD)')

    def test_no_origin_lands_on_local_main(self):
        # without a remote the repository lands on local main (landing.py rule 2): landed work
        # may leave the sidebar, unlanded work keeps its chat
        lone = os.path.join(self.root, 'lone')
        self.git(self.root, 'init', '-q', '-b', 'main', lone)
        self.git(lone, 'commit', '-q', '--allow-empty', '-m', 'x')
        self.assertIn('landed on local main', self.assertOk(lone))
        wt = os.path.join(self.root, 'lone-worktrees', 'task')
        self.git(lone, 'worktree', 'add', '-q', '-b', 'agent/task', wt, 'main')
        self.git(wt, 'commit', '-q', '--allow-empty', '-m', 'unlanded')
        self.assertKeep(wt, 'no remote origin')
        self.git(lone, 'merge', '-q', '--ff-only', 'agent/task')
        self.assertIn('landed on local main', self.assertOk(wt))

    def test_local_main_setting(self):
        # a landing on local main that is not pushed yet: ok only in local-main mode
        origin = os.path.join(self.root, 'lm-origin.git')
        repo = os.path.join(self.root, 'lm')
        self.git(self.root, 'init', '-q', '--bare', '-b', 'main', origin)
        self.git(self.root, 'init', '-q', '-b', 'main', repo)
        self.git(repo, 'remote', 'add', 'origin', origin)
        with open(os.path.join(repo, 'HANDOFF.md'), 'w') as f:
            f.write('# H\n\n## Landing settings\n\n| Setting | Value |\n|---|---|\n'
                    '| landing | `local main` |\n')
        self.git(repo, 'add', 'HANDOFF.md')
        self.git(repo, 'commit', '-q', '-m', 'init')
        self.git(repo, 'push', '-q', 'origin', 'main')
        self.git(repo, 'fetch', '-q', 'origin')
        self.git(repo, 'remote', 'set-head', 'origin', 'main')
        wt = os.path.join(self.root, 'lm-worktrees', 'task')
        self.git(repo, 'worktree', 'add', '-q', '-b', 'agent/task', wt, 'main')
        self.git(wt, 'commit', '-q', '--allow-empty', '-m', 'work')
        self.assertKeep(wt, 'not on GitHub')
        self.git(repo, 'merge', '-q', '--ff-only', 'agent/task')
        self.assertIn('landed on local main', self.assertOk(wt))
        with open(os.path.join(repo, 'HANDOFF.md'), 'w') as f:
            f.write('# H\n')
        self.git(repo, 'commit', '-q', '-am', 'auto: a folder remote is not GitHub, so PR')
        self.git(repo, 'push', '-q', 'origin', 'main')
        wt2 = os.path.join(self.root, 'lm-worktrees', 'task2')
        self.git(repo, 'worktree', 'add', '-q', '-b', 'agent/task2', wt2, 'main')
        self.git(wt2, 'commit', '-q', '--allow-empty', '-m', 'work')
        self.git(repo, 'merge', '-q', '--ff-only', 'agent/task2')
        self.assertKeep(wt2, 'not on GitHub')

    def test_a_successor_s_pushed_branch_holds_a_handed_over_chat(self):
        # #14: a chat hands its unfinished issue to a fresh chat whose branch starts from its
        # head; once that branch is on GitHub, the predecessor holds nothing GitHub does not
        pred = self.worktree('pred')
        self.commit(pred, 'pred\n')
        succ = self.worktree('succ', base='agent/pred')
        self.commit(succ, 'succ\n')
        self.assertKeep(pred, 'not on GitHub')  # the successor's branch is local only
        self.git(succ, 'push', '-q', 'origin', 'agent/succ')
        self.assertIn('held by origin/agent/succ', self.assertOk(pred))
        # the successor archived itself after its push: its worktree is gone, GitHub holds it
        self.git(self.repo, 'worktree', 'remove', succ)
        self.assertIn('held by origin/agent/succ', self.assertOk(pred))

    def test_a_successor_does_not_cover_commits_only_the_predecessor_s_history_holds(self):
        pred = self.worktree('pred-reflog')
        self.commit(pred, 'kept\n')
        self.commit(pred, 'dropped\n')
        self.git(pred, 'reset', '-q', '--hard', 'HEAD~1')  # "dropped" is in the reflog only
        succ = self.worktree('succ-reflog', base='agent/pred-reflog')
        self.commit(succ, 'succ\n')
        self.git(succ, 'push', '-q', 'origin', 'agent/succ-reflog')
        self.assertKeep(pred, 'only this worktree')

    def test_a_successor_branch_github_deleted_unmerged_keeps(self):
        # the fetch does not prune: a tracking ref of a branch GitHub no longer has proves nothing
        pred = self.worktree('pred-stale')
        self.commit(pred, 'pred\n')
        succ = self.worktree('succ-stale', base='agent/pred-stale')
        self.git(succ, 'push', '-q', 'origin', 'agent/succ-stale')
        self.git(self.origin, 'branch', '-D', 'agent/succ-stale')  # closed unmerged, deleted
        self.git(pred, 'fetch', '-q', 'origin')
        self.assertEqual(self.git(pred, 'rev-parse', '-q', '--verify',
                                  'refs/remotes/origin/agent/succ-stale'),
                         self.git(pred, 'rev-parse', 'HEAD'))  # the stale ref is still here
        self.assertKeep(pred, 'not on GitHub')

    def test_every_ok_runs_the_reflog_proof(self):
        # a commit dropped by a reset is held only by this worktree's reflog: archiving the
        # worktree would lose it, whatever branch holds HEAD
        wt = self.worktree('pushed-dropped')
        self.commit(wt, 'kept\n')
        self.commit(wt, 'dropped\n')
        self.git(wt, 'reset', '-q', '--hard', 'HEAD~1')
        self.git(wt, 'push', '-q', 'origin', 'agent/pushed-dropped')
        self.assertKeep(wt, 'only this worktree')
        # a branch for the dropped commit (a scratch branch) keeps it, and the chat may go
        dropped = self.git(wt, 'rev-parse', 'HEAD@{1}')
        self.git(wt, 'branch', 'scratch/1-dropped', dropped)
        self.assertOk(wt)

    def test_landed_runs_the_reflog_proof(self):
        wt = self.worktree('side-detached')
        self.commit(wt, 'side\n')
        self.git(wt, 'push', '-q', 'origin', 'agent/side-detached')
        head = self.git(wt, 'rev-parse', 'HEAD')
        merged = self.fake_gh([{'number': 7, 'headRefOid': head, 'baseRefName': 'main'}])
        self.assertOk(wt, '--landed', env={'AGENTIC_GITHUB_FLOW_GH': merged})
        self.git(wt, 'switch', '-q', '--detach')
        self.commit(wt, 'after the merge, on a detached HEAD\n')
        self.git(wt, 'switch', '-q', 'agent/side-detached')
        self.assertKeep(wt, 'only this worktree', '--landed',
                        env={'AGENTIC_GITHUB_FLOW_GH': merged})

    def test_a_live_local_successor_alone_keeps(self):
        # a successor's branch that is only on this machine is not on GitHub, in either mode
        pred = self.worktree('pred-local')
        self.commit(pred, 'pred\n')
        succ = self.worktree('succ-local', base='agent/pred-local')
        self.commit(succ, 'succ\n')
        self.assertKeep(pred, '1 commit(s) of agent/pred-local are not on GitHub')

    def fake_gh(self, pulls):
        """AGENTIC_GITHUB_FLOW_GH for a gh whose `pr list` answers `pulls`."""
        script = os.path.join(self.root, 'fake_gh_%d.py' % len(os.listdir(self.root)))
        with open(script, 'w') as f:
            f.write('import json, sys\nprint(json.dumps(%r))\n' % (pulls,))
        return json.dumps([sys.executable, script])

    def test_landed_requires_the_landing_branch_or_a_merged_pull_request(self):
        # #18: a side chat leaves only once its work landed or its pull request merged, so a
        # follow-up still reaches it while the pull request is open
        wt = self.worktree('side')
        self.commit(wt, 'side\n')
        self.git(wt, 'push', '-q', 'origin', 'agent/side')
        self.assertOk(wt)  # on GitHub: an issue chat may go
        head = self.git(wt, 'rev-parse', 'HEAD')
        none = self.fake_gh([])
        self.assertKeep(wt, 'not landed', '--landed', env={'AGENTIC_GITHUB_FLOW_GH': none})
        # a squash merge: main does not hold HEAD, the merged pull request's head is HEAD
        squash = self.fake_gh([{'number': 7, 'headRefOid': head, 'baseRefName': 'main'}])
        self.assertIn('pull request #7 merged',
                      self.assertOk(wt, '--landed', env={'AGENTIC_GITHUB_FLOW_GH': squash}))
        # merged into another branch (stacked) proves nothing about the landing branch
        stacked = self.fake_gh([{'number': 8, 'headRefOid': head, 'baseRefName': 'agent/x'}])
        self.assertKeep(wt, 'not landed', '--landed', env={'AGENTIC_GITHUB_FLOW_GH': stacked})
        # a pull request whose head is not this HEAD (a later commit was not part of it)
        older = self.fake_gh([{'number': 9, 'headRefOid': '0' * 40, 'baseRefName': 'main'}])
        self.assertKeep(wt, 'not landed', '--landed', env={'AGENTIC_GITHUB_FLOW_GH': older})
        # no gh: a squash merge cannot be proven, and the chat stays
        self.assertKeep(wt, 'not landed', '--landed', env={'AGENTIC_GITHUB_FLOW_GH': '"x"'})
        # a merge on GitHub: origin's main holds HEAD, no pull request needed
        self.git(self.origin, 'fetch', '-q', self.repo, 'agent/side:main')
        self.assertIn('in origin/main', self.assertOk(wt, '--landed', env={
            'AGENTIC_GITHUB_FLOW_GH': none}))

    def test_landed_does_not_count_a_successor(self):
        pred = self.worktree('pred-landed')
        self.commit(pred, 'pred\n')
        succ = self.worktree('succ-landed', base='agent/pred-landed')
        self.git(succ, 'push', '-q', 'origin', 'agent/succ-landed')
        self.assertKeep(pred, 'not landed', '--landed',
                        env={'AGENTIC_GITHUB_FLOW_GH': self.fake_gh([])})

    def test_landed_on_local_main(self):
        lone = os.path.join(self.root, 'lone-landed')
        self.git(self.root, 'init', '-q', '-b', 'main', lone)
        self.git(lone, 'commit', '-q', '--allow-empty', '-m', 'x')
        wt = os.path.join(self.root, 'lone-landed-worktrees', 'side')
        self.git(lone, 'worktree', 'add', '-q', '-b', 'agent/side', wt, 'main')
        self.git(wt, 'commit', '-q', '--allow-empty', '-m', 'unlanded')
        self.assertKeep(wt, 'no remote origin', '--landed')
        self.git(lone, 'merge', '-q', '--ff-only', 'agent/side')
        self.assertIn('landed on local main', self.assertOk(wt, '--landed'))

    def test_not_a_worktree_and_usage(self):
        plain = os.path.join(self.root, 'plain')
        os.makedirs(plain, exist_ok=True)
        if not os.path.exists(os.path.join(self.root, '.git')):
            self.assertKeep(plain, 'not a git worktree')
        r = subprocess.run([sys.executable, TOOL], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        r = subprocess.run([sys.executable, TOOL, 'a', 'b'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        r = subprocess.run([sys.executable, TOOL, 'a', '--landd'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_a_failed_fetch_judges_on_the_refs_as_last_fetched(self):
        wt = self.worktree('offline')
        self.commit(wt, 'offline\n')
        self.git(wt, 'push', '-q', 'origin', 'agent/offline')
        moved = self.origin + '.away'
        os.rename(self.origin, moved)
        try:
            line = self.assertOk(wt)
            self.assertIn('fetch failed', line)
            self.commit(wt, 'unpushed\n')
            self.assertKeep(wt, 'fetch failed')
        finally:
            os.rename(moved, self.origin)


class Copy(unittest.TestCase):
    def test_issue_chats_copy_of_work_proof_is_identical(self):
        owner = os.path.join(ROOT, 'plugins', 'core', 'scripts', 'work_proof.py')
        copy = os.path.join(os.path.dirname(TOOL), 'work_proof.py')
        with open(owner, 'rb') as a, open(copy, 'rb') as b:
            self.assertEqual(a.read(), b.read(), 'copy plugins/core/scripts/work_proof.py to %s'
                             % os.path.relpath(copy, ROOT))


if __name__ == '__main__':
    unittest.main(verbosity=1)
