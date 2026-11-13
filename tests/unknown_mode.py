"""Helper of the caller tests (push_branch.py, merge_pr.py): run a script with landing.py's mode
unknown, as when GitHub cannot be asked from inside the Claude Code sandbox.

Those tests use a folder as origin, which is not GitHub, so landing.py never asks gh there. The
wrapper runs the script with landing.decide() answering `unknown` with the cause line landing.py
prints for a gh that cannot read its configuration; tests/landing.py checks that landing.py
gives that answer itself. Not a test of its own.
"""
import os

CAUSE = ('gh could not run here (its configuration is unreadable, as inside a sandbox): run '
         'landing.py outside the sandbox, or set the `landing` row in HANDOFF.md '
         '\N{SECTION SIGN}Landing settings')

WRAPPER = r'''import os, runpy, sys
tool = sys.argv[1]
sys.path.insert(0, os.path.dirname(tool))
import landing
real = landing.decide
def decide(path='.'):
    mode, branch, checks = real(path)
    return landing.UNKNOWN, branch, checks[:1] + [os.environ['UNKNOWN_MODE_CAUSE']]
landing.decide = decide
sys.argv = sys.argv[1:]
runpy.run_path(tool, run_name='__main__')
'''


def wrapper(folder):
    """The path of the wrapper, written into <folder>: run `python3 <it> <script> <args>` with
    UNKNOWN_MODE_CAUSE=CAUSE in the environment."""
    path = os.path.join(folder, 'unknown_mode_wrapper.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(WRAPPER)
    return path
