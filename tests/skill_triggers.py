#!/usr/bin/env python3
"""Does each skill's description make a client pick it for the right requests?

Usage: python3 tests/skill_triggers.py [--client claude|codex] [--skill NAME] [--model MODEL]
       [--effort EFFORT]

A small check, kept small on purpose: tests/skill_triggers.json holds one request that should
pick each skill and one that should not. For each, this starts the client non-interactively with
this checkout's skills loaded (Claude: `--plugin-dir` per plugin; Codex: a temporary folder whose
.agents/skills/<name> point at the skills, used as its working directory) and asks which one skill
it would load first, or NONE. It measures the choice the description produces, not the work the
skill then does. It spends tokens and needs a logged-in client, so it is not part of the offline
gate: run it after changing a skill's description. Exit 1 if any request goes wrong, including
client or response failures. Model and effort default to the client's; pass them for
reproducible runs.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
CASES = json.load(open(os.path.join(HERE, 'skill_triggers.json'), encoding='utf-8'))
CODEX = (os.environ.get('CODEX') or shutil.which('codex')
         or '/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex')
QUESTION = ('Do not do anything and do not use any tool. A user sends the request quoted below. '
            'Which ONE of the following available skills would you load first to handle it: '
            + ', '.join(CASES) + '? '
            'Answer with only the skill name, or NONE if none of these skills fits.\n\nRequest: "%s"')


class ProbeError(Exception):
    """The client did not produce a usable skill choice."""


def plugin_dirs():
    base = os.path.join(ROOT, 'plugins')
    return [os.path.join(base, p) for p in sorted(os.listdir(base))
            if os.path.isdir(os.path.join(base, p, 'skills'))]


def codex_folder():
    """A temporary folder whose .agents/skills/<name> are copies of this checkout's skills."""
    folder = tempfile.mkdtemp(prefix='skill-triggers-')
    target = os.path.join(folder, '.agents', 'skills')
    os.makedirs(target)
    for plugin in plugin_dirs():
        for name in os.listdir(os.path.join(plugin, 'skills')):
            shutil.copytree(os.path.join(plugin, 'skills', name), os.path.join(target, name))
    return folder


def ask(client, request, model=None, effort=None, folder=None):
    prompt = QUESTION % request.replace('"', "'")
    if client == 'claude':
        cmd = ['claude', '-p', prompt, '--max-turns', '1']
        for plugin in plugin_dirs():
            cmd += ['--plugin-dir', plugin]
        if effort:
            cmd += ['--effort', effort]
    else:
        cmd = [CODEX, 'exec', '--skip-git-repo-check']
        if effort:
            cmd += ['-c', 'model_reasoning_effort=' + json.dumps(effort)]
        if folder:
            cmd += ['-C', folder]
        cmd.append(prompt)
    if model:
        cmd += ['--model', model]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=240,
                           cwd=folder or os.path.expanduser('~'))
    except subprocess.TimeoutExpired as exc:
        raise ProbeError('client timed out') from exc
    except OSError as exc:
        raise ProbeError('client could not start: ' + type(exc).__name__) from exc
    if r.returncode != 0:
        raise ProbeError('client exited with status %s' % r.returncode)
    answer = r.stdout.strip()
    if answer not in {*CASES, 'NONE'}:
        raise ProbeError('empty or malformed response; expected one listed skill or NONE')
    return answer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--client', choices=['claude', 'codex'], default='claude')
    ap.add_argument('--skill')
    ap.add_argument('--model', help='explicit client model; otherwise keep its configured model')
    ap.add_argument('--effort', choices=['low', 'medium', 'high', 'xhigh', 'max'],
                    help='explicit client effort; otherwise keep its configured effort')
    a = ap.parse_args()
    print('client: %s; model: %s; effort: %s' %
          (a.client, a.model or 'client-configured', a.effort or 'client-configured'))
    folder = codex_folder() if a.client == 'codex' else None
    total = right = 0
    try:
        for skill, kinds in CASES.items():
            if a.skill and skill != a.skill:
                continue
            for kind in ('should', 'should_not'):
                for request in kinds[kind]:
                    try:
                        answer = ask(a.client, request, a.model, a.effort, folder)
                        ok = (answer == skill) if kind == 'should' else (answer != skill)
                    except ProbeError as exc:
                        answer = 'ERROR: ' + str(exc)
                        ok = False
                    total += 1; right += ok
                    print('%s %-16s %-10s %-34s <- %s' % ('ok  ' if ok else 'MISS', skill, kind,
                                                          answer, request[:60]))
    finally:
        if folder:
            shutil.rmtree(folder, ignore_errors=True)
    if not total:
        print('no cases'); return 1
    print('%d of %d (%.0f%%) on %s' % (right, total, 100.0 * right / total, a.client))
    return 0 if right == total else 1


if __name__ == '__main__':
    sys.exit(main())
