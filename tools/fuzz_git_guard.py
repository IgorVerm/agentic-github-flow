#!/usr/bin/env python3
"""Checks the git guard's reading against the shells themselves (#33).

Usage: python3 tools/fuzz_git_guard.py <seed> <count> <mutate|random|struct> [<guard.py>]

It builds random shell texts, runs each in bash, zsh, dash and sh with a `git` that only logs
its words (first on PATH, in a temporary folder, nothing else on PATH but /usr/bin and /bin),
and asks the guard about the same text. A logged command that judge_git or ask_git refuses,
for a text the guard passed, is printed: HOLE-CERTAIN when the Reader was certain of the text
(a wrong reading), HOLE-SUPERSET when a former permission rule matched it, `beyond` otherwise.
The texts hold only echo, true, cat, `:` and that git; they write only inside the temporary
folder. Not part of tests/run_all.py: it needs those shells (macOS has bash 3.2 as /bin/sh)."""
import importlib.util, os, random, shutil, signal, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, '..') + os.sep
G = sys.argv[4] if len(sys.argv) > 4 else W + 'plugins/guards/scripts/pre_tool_git_guard.py'
spec = importlib.util.spec_from_file_location('g', G); g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
seed, count, mode = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
rnd = random.Random(seed)
root = tempfile.mkdtemp(prefix='fuzz_git_guard')
bind = os.path.join(root, 'bin'); os.mkdir(bind)
log = os.path.join(root, 'log')
with open(os.path.join(bind, 'git'), 'w') as f:
    f.write('#!/bin/sh\n{ for a in "$@"; do printf "%%s\\037" "$a"; done; printf "\\036"; } >> %s\n' % log)
os.chmod(os.path.join(bind, 'git'), 0o755)
SHELLS = [['/bin/bash', '--noprofile', '--norc', '-c'], ['/bin/zsh', '-f', '-c'], ['/bin/dash', '-c'], ['/bin/sh', '-c']]
WORDS = ['git', 'git', 'git', '-C', 'r', 'stash', 'drop', 'clean', '-fd', 'push', '--force', 'reset', '--hard',
         'echo', 'true', 'x', 'cat', 'EOF', 'commit', '-m', 'msg', ':', 'rebase']
NOISE = ["'", '"', '\\', '\\\n', '$x', '${x}', '${x:-stash}', '${x:-}', '$(', ')', '`', '$((', '))', '((', '[[', ']]',
         '{', '}', ',', '(', '#', '\n', '\n', ';', '&&', '||', '|', '&', '>', '>>', '<', '<<', '<<<', '<<-', '>&',
         '&>', '2>&1', '>!', '>|', '<(', '>(', "$'", '$"', 'case', 'in', 'esac', 'a[', ']', '=', 'EOF\n', "'EOF'",
         '\nEOF\n', 'if', 'then', 'fi', 'do', 'done', 'for', '!', '*', '?', '~', 'time', 'eval', 'trap', 'EXIT',
         'coproc', 'function', 'fn()', '$()', '"$@"', '1', '2', '-', '\t', '\r', '$[', '<<EOF', "<<'EOF'", '$(true)',
         '${', '$', '\\\\', "\\'", '\\"', '#x', ' # ', "it's", '>/dev/null', '2>', 'out', '$(cat <<', '"$(',
         # the second review: what the lists above did not hold
         '$IFS', '${IFS}', "$'\\x2d", "$'\\u002d", "$'\\0'", "$'\\c", "$'\\400'", 'repeat 1', 'alias', '<->', '(N)',
         '[[ a ]]', 'eval --', 'env -vS', '-f4', '-fm']
# not `source` or `bash` before a word: either would read this `git`, a script, as its script
BASES = ['git -C r stash drop', 'git -C r clean -fd', 'git -C r push --force', 'git -C r reset --hard',
         'git stash drop', 'git -C r rebase x', 'git -C r commit -m msg --no-verify', 'git -C r push']

P = ["'", '"', ')', '(', '\\', '#', ' # ', '`', '$(', '\n', '\n', ';', ' ', ' ', 'git -C r clean -fd', 'echo y', 'EOF',
     '\nEOF\n', "it's", ')"', '" ', '$(echo ', 'x', '<<', "<<'EOF'", '<<EOF', 'cat ', 'esac', 'case x in a) ', ';;',
     '\\\n', '{', '}', '$x', '-C r', 'git', 'git ', 'stash drop', ' stash drop', '>', '2>&1', '&', '|', 'bash', "<<-'EOF'",
     '\t', '$((', '))', '[', ']', 'a[1', '=', '<<<', '!', '"$(', "$'", 'eval ', 'sh -c ', 'trap ', ' EXIT', '<(', '${x:-', '&>',
     'git push --force', 'git -C r stash drop']
def pieces(a, b):
    return ''.join(rnd.choice(P) for _ in range(rnd.randint(a, b)))
def struct():
    k = rnd.randint(1, 5)
    if k == 1: return 'echo "$(cat <<\'EOF\'\n' + pieces(0, 8) + '\nEOF\n)"' + pieces(0, 6)
    if k == 2: return 'echo a ' + pieces(0, 3) + '#' + pieces(0, 4) + '\n' + pieces(0, 6)
    if k == 3: return pieces(1, 12)
    if k == 4: return 'git -C r commit -m "$(cat <<\'EOF\'\n' + pieces(0, 8) + '\nEOF\n)" -- a.md' + pieces(0, 6)
    return pieces(0, 3) + 'cat <<' + rnd.choice(['EOF', "'EOF'", '-EOF', '"EOF"', '\\EOF', 'E"O"F']) + pieces(0, 3) + '\n' + pieces(0, 6) + '\nEOF\n' + pieces(0, 6)
def make():
    if mode == 'struct': return struct()
    if mode == 'mutate':
        toks = rnd.choice(BASES).split(' ')
        out = []
        for t in toks:
            if rnd.random() < 0.5:
                out.append(rnd.choice(NOISE)); out.append(rnd.choice(['', ' ']))
            out.append(t); out.append(rnd.choice([' ', ' ', '']) if rnd.random() < 0.3 else ' ')
        pre = ''.join(rnd.choice(NOISE + WORDS) + rnd.choice(['', ' ']) for _ in range(rnd.randint(0, 4)))
        post = ''.join(rnd.choice(['', ' ']) + rnd.choice(NOISE + WORDS) for _ in range(rnd.randint(0, 5)))
        return pre + ''.join(out) + post
    body = [rnd.choice(NOISE + WORDS + WORDS) + rnd.choice(['', ' ', ' ']) for _ in range(rnd.randint(2, 12))]
    body.insert(rnd.randint(0, len(body)), rnd.choice(BASES) + rnd.choice(['', ' ', '\n', ';']))
    return ''.join(body)

def run(shell, text):
    if os.path.exists(log): os.remove(log)
    work = os.path.join(root, 'w'); shutil.rmtree(work, ignore_errors=True); os.mkdir(work)
    try:
        p = subprocess.Popen(shell + [text], cwd=work, env={'PATH': bind + ':/usr/bin:/bin', 'HOME': work},
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        try: p.wait(timeout=3)
        except subprocess.TimeoutExpired: pass
        try: os.killpg(p.pid, signal.SIGKILL)
        except OSError: pass
    except OSError:
        return []
    if not os.path.exists(log): return []
    data = open(log, errors='replace').read()
    return [rec.split('\037')[:-1] for rec in data.split('\036') if rec]

holes = 0
import json, re
sp = importlib.util.spec_from_file_location('m', W + 'plugins/guards/scripts/pre_tool_sandbox_network.py'); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
FORMER = json.load(open(W + 'tests/claude_git_rules_former.json'))
RX = {k: [m.pattern_regex(r[5:-1], False) for r in FORMER[k]] for k in FORMER}
def main_stops(text):
    parts = [text] + re.split(r'&&|\|\||[;|\n&]', text)
    try: parts += [' '.join(t) for t in g.split_commands(text)]
    except ValueError: pass
    parts = [re.sub(r'[ \t]+', ' ', p.strip()) for p in parts]
    return any(rx.fullmatch(p) for k in RX for rx in RX[k] for p in parts)
beyond = globonly = 0
stats = {'ran': 0, 'refused': 0, 'stopped_texts': 0}
for k in range(count):
    text = make()
    if '\0' in text: continue
    blocked = g.check(text)
    asked = blocked or g.check_ask(text)
    stats['stopped_texts'] += bool(asked)
    for shell in SHELLS:
        for argv in run(shell, text):
            b, a = g.judge_git(argv), g.ask_git(argv)
            stats['ran'] += 1; stats['refused'] += bool(b or a)
            if b and not blocked or a and not asked:
                certain = g.Reader(text).uncertain is None
                kind = 'HOLE-CERTAIN' if certain else 'HOLE-SUPERSET' if main_stops(text) else 'beyond'
                if kind == 'beyond':
                    beyond += 1
                    if beyond > 3: break
                else: holes += 1
                print(kind, os.path.basename(shell[0]), repr(text), argv, flush=True)
                break
print('beyond', beyond)
print('done seed', seed, 'count', count, 'mode', mode, 'holes', holes, stats)
shutil.rmtree(root, ignore_errors=True)
