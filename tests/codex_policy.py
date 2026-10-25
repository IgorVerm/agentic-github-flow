#!/usr/bin/env python3
"""Usage: python3 tests/codex_policy.py   (exits non-zero on any mismatch; CODEX=<path> overrides the binary)

Checks every command below with `codex execpolicy check` against the guards plugin's
policy/git-safety.rules ALONE and COMBINED with ~/.codex/rules/default.rules (when present; only
read). Exits 77 (skipped) when no codex command is found.
  CASES: alone must equal the expected decision; combined must keep forbidden/prompt, and "none"
         may only become "allow" (default.rules' accumulated approvals).
  GAPS:  option-order and `git -C` cases prefix rules cannot see. Expected = the ACTUAL decision,
         alone and combined, so the matrix records each gap and fails if it ever changes. The tag
         names what does cover it.
Run before committing any change to git-safety.rules: one failing match/not_match example stops
the whole file from loading.
"""
import json, os, shlex, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.join(HERE, "..", "plugins", "guards", "policy", "git-safety.rules")
DEFAULT = os.path.expanduser("~/.codex/rules/default.rules")
BUNDLED = ("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",)  # macOS app
CODEX = (os.environ.get("CODEX") or shutil.which("codex")
         or next((p for p in BUNDLED if os.path.exists(p)), BUNDLED[0]))

CASES = [
("git push --force origin main","forbidden"),("git push -f","forbidden"),("git push --force-with-lease","forbidden"),
("git push --delete origin x","prompt"),("git push -d origin x","prompt"),("git push --mirror","forbidden"),("git push --prune origin","forbidden"),
("git push --no-verify origin main","forbidden"),
("git reset --hard HEAD","forbidden"),("git branch -D x","forbidden"),("git branch -f main HEAD~1","forbidden"),("git branch --force main x","forbidden"),
("git clean -fd","forbidden"),("git restore a.txt","forbidden"),("git restore --staged a.txt","forbidden"),
("git checkout -- a.txt","forbidden"),("git checkout .","forbidden"),("git checkout -f main","forbidden"),("git switch -f main","forbidden"),("git switch --discard-changes main","forbidden"),
("git stash drop","forbidden"),("git stash clear","forbidden"),("git rebase main","forbidden"),
("git tag -d v1","forbidden"),("git tag -f v1","forbidden"),("git worktree remove --force ../wt","forbidden"),
("git filter-branch --tree-filter x","forbidden"),("git filter-repo --path x","forbidden"),("git replace a b","forbidden"),("git prune","forbidden"),
("git reflog expire --all","forbidden"),("git reflog delete HEAD@{1}","forbidden"),("git gc --prune=now","forbidden"),("git gc --prune","forbidden"),
("git update-ref -d refs/heads/x","forbidden"),("git update-ref refs/heads/main abc","prompt"),
("git commit --amend -m x","prompt"),("git commit --no-verify -m x","forbidden"),("git commit -n -m x","forbidden"),("git commit -a -m x","forbidden"),("git commit --all -m x","forbidden"),
("git add -A","forbidden"),("git add --all","forbidden"),("git add .","forbidden"),("git add -f .env","forbidden"),("git add --force x","forbidden"),
("git -c core.hooksPath=/dev/null commit -m x","prompt"),
("git config --global user.email x","forbidden"),("git config --system x y","forbidden"),("git config --local core.bare true","forbidden"),("git config --unset user.name","forbidden"),
("git config core.hooksPath /dev/null","forbidden"),("git config credential.helper x","forbidden"),("git config user.email x","forbidden"),("git config user.name x","forbidden"),
("git remote add up x","prompt"),("git remote set-url origin x","prompt"),("git remote remove origin","prompt"),("git remote rm origin","prompt"),("git remote rename a b","prompt"),
("gh repo delete o/r","forbidden"),("gh repo archive o/r","forbidden"),("gh repo edit --visibility public","forbidden"),("gh repo rename x","forbidden"),
("gh release delete v1","forbidden"),("gh issue delete 5","forbidden"),("gh label delete x","forbidden"),
("gh secret set X","forbidden"),("gh ssh-key add k.pub","forbidden"),("gh auth token","forbidden"),("printenv","forbidden"),("printenv GITHUB_TOKEN","forbidden"),
("gh auth status","prompt"),("gh auth refresh -s delete_repo","prompt"),("gh api repos/o/r","prompt"),("gh api -X DELETE repos/o/r/git/refs/heads/x","prompt"),
("gh repo create x --private","prompt"),("gh pr merge 3","prompt"),("gh release create v1","prompt"),("gh gist create f","prompt"),
("git push origin main","prompt"),("git push origin main --force","prompt"),("git push origin +main","prompt"),("git push origin :feature","prompt"),
# must stay usable: no rule in git-safety.rules
("git status","none"),("git add src/main.rs","none"),("git commit -m x -- a.txt","none"),("git diff","none"),("git log --oneline","none"),
("git checkout main","none"),("git switch -c lane/x","none"),("git branch -d x","none"),("git stash push -m wip -- a","none"),("git merge --no-ff lane/x","none"),
("git worktree add ../wt -b lane/x","none"),("git worktree remove ../wt","forbidden"),("git worktree prune","none"),
("python3 remove_merged_worktree.py ../wt","none"),("git config --get user.email","none"),("git remote -v","none"),("git reflog","none"),
("git gc","none"),("git tag v2","none"),("git reset -q -- a.txt","none"),("gh issue view 3","none"),("gh issue close 3 --comment x","none"),("gh issue list","none"),("gh label list","none"),
("git add -A","forbidden"),
("git checkout --detach --force HEAD","forbidden"),
]

# (command, alone, combined, what covers it)
GAPS = [
("git add example.txt -A", "none", "allow", "known-gap:Claude deny; git guard hook"),
("git add example.txt --all", "none", "allow", "known-gap:Claude deny; git guard hook for Codex"),
("git add src -f", "none", "allow", "known-gap:Claude deny; git guard hook for Codex"),
("git commit -m probe --no-verify", "none", "allow", "known-gap:Claude deny; git guard hook for Codex"),
("git commit -m probe -n", "none", "allow", "known-gap:Claude deny; git guard hook for Codex"),
("git commit -m probe --amend", "none", "allow", "known-gap:Claude ask; pre-push hook if the commit was pushed; else git guard hook for Codex"),
("git commit -m probe -a", "none", "allow", "known-gap:Claude deny; git guard hook for Codex"),
("git reset HEAD~1 --hard", "none", "none", "known-gap:Claude deny; git guard hook for Codex"),
("git -C /tmp push origin main", "none", "none", "known-gap:Claude ask; Codex push not prompted; pre-push hook refuses force and unmerged deletes only; the written rule"),
("git -C /tmp push --force origin main", "none", "none", "known-gap:pre-push hook; Claude deny"),
("git -C /tmp commit --no-verify -m x", "none", "none", "known-gap:Claude deny; git guard hook for Codex"),
("git -C /tmp tag -d x", "none", "none", "known-gap:Claude deny (git -C twin); git guard hook for Codex"),
("git -C /tmp worktree remove ../wt", "none", "none", "known-gap:Claude deny; git guard hook for Codex"),
]

def decide(rule_files, cmd):
    args = [CODEX, "execpolicy", "check"]
    for r in rule_files:
        args += ["--rules", r]
    p = subprocess.run(args + ["--"] + shlex.split(cmd), capture_output=True, text=True)
    if p.returncode:
        return "LOAD-ERROR: " + p.stderr.strip().splitlines()[-1]
    return json.loads(p.stdout).get("decision", "none")

def main():
    if not (os.path.exists(CODEX) or shutil.which(CODEX)):
        print("SKIP: no codex command (install Codex, or set CODEX=<path>)")
        return 77
    combined = os.path.exists(DEFAULT)
    fails = 0
    for cmd, expected in CASES:
        exp = expected.split(" ")[0]
        alone = decide([RULES], cmd)
        ok = alone == exp
        comb = decide([RULES, DEFAULT], cmd) if combined else "-"
        if combined:
            ok = ok and (comb == exp or (exp == "none" and comb == "allow"))
        if not ok:
            fails += 1
            print(f"FAIL  {cmd!r}: expected {expected}, alone={alone}, combined={comb}")
    for cmd, alone_exp, comb_exp, tag in GAPS:
        alone = decide([RULES], cmd)
        comb = decide([RULES, DEFAULT], cmd) if combined else comb_exp
        if alone != alone_exp or comb != comb_exp:
            fails += 1
            print(f"GAP CHANGED  {cmd!r}: expected alone={alone_exp} combined={comb_exp}, got {alone}/{comb} ({tag})")
    n = len(CASES) + len(GAPS)
    print(f"{n - fails}/{n} pass" + ("" if combined else " (default.rules absent: alone only)"))
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
