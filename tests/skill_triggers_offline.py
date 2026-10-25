#!/usr/bin/env python3
"""Offline checks of tests/skill_triggers.py: probe failures and scoring; never starts a model client."""
import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skill_triggers as triggers  # noqa: E402


class ProbeTests(unittest.TestCase):
    def test_failures_cannot_pass_a_negative_case(self):
        failures = [
            subprocess.TimeoutExpired('client', 240),
            FileNotFoundError('client'),
            PermissionError('client'),
            subprocess.CompletedProcess([], 1, 'NONE\n', 'failed'),
            subprocess.CompletedProcess([], 0, '', ''),
            subprocess.CompletedProcess([], 0, 'ERROR', ''),
            subprocess.CompletedProcess([], 0, 'I would use NONE', ''),
            subprocess.CompletedProcess([], 0, 'spec-first\nNONE', ''),
            subprocess.CompletedProcess([], 0, 'unknown-skill', ''),
        ]
        cases = {'spec-first': {'should': [], 'should_not': ['missing source file']}}
        for failure in failures:
            with self.subTest(failure=failure):
                kwargs = ({'side_effect': failure} if isinstance(failure, Exception)
                          else {'return_value': failure})
                with patch.object(triggers, 'CASES', cases), \
                     patch.object(triggers.subprocess, 'run', **kwargs), \
                     patch.object(triggers.sys, 'argv', ['skill_triggers.py']), \
                     contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(triggers.main(), 1)
                    self.assertIn('0 of 1', output.getvalue())
                    self.assertIn('ERROR:', output.getvalue())

    def test_valid_choices_and_configured_defaults(self):
        for client in ('claude', 'codex'):
            for answer in ('NONE', 'spec-first', 'ship-change'):
                with self.subTest(client=client, answer=answer):
                    result = subprocess.CompletedProcess([], 0, '\n' + answer + '\n', '')
                    with patch.object(triggers.subprocess, 'run', return_value=result) as run:
                        self.assertEqual(triggers.ask(client, 'request'), answer)
                    command = run.call_args.args[0]
                    if client == 'claude':
                        self.assertEqual(command.count('--plugin-dir'), len(triggers.plugin_dirs()))
                    self.assertNotIn('--model', command)
                    self.assertNotIn('--effort', command)
                    self.assertNotIn('-c', command)

    def test_explicit_model_and_effort(self):
        result = subprocess.CompletedProcess([], 0, 'NONE', '')
        for client, model in (('codex', 'gpt-5'), ('claude', 'opus')):
            with self.subTest(client=client):
                with patch.object(triggers.subprocess, 'run', return_value=result) as run:
                    triggers.ask(client, 'request', model=model, effort='high')
                command = run.call_args.args[0]
                self.assertEqual(command[command.index('--model') + 1], model)
                if client == 'codex':
                    self.assertEqual(command[command.index('-c') + 1], 'model_reasoning_effort="high"')
                else:
                    self.assertEqual(command[command.index('--effort') + 1], 'high')

    def test_valid_choice_scoring(self):
        for kind, answer, expected in (
            ('should', 'spec-first', 0), ('should', 'NONE', 1),
            ('should_not', 'NONE', 0), ('should_not', 'ship-change', 0),
            ('should_not', 'spec-first', 1),
        ):
            with self.subTest(kind=kind, answer=answer):
                cases = {'spec-first': {'should': [], 'should_not': []}}
                cases['spec-first'][kind] = ['request']
                with patch.object(triggers, 'CASES', cases), \
                     patch.object(triggers, 'ask', return_value=answer), \
                     patch.object(triggers.sys, 'argv', ['skill_triggers.py']), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(triggers.main(), expected)

    def test_live_probe_budget(self):
        for skill, cases in triggers.CASES.items():
            with self.subTest(skill=skill):
                self.assertEqual(len(cases['should']), 1)
                self.assertEqual(len(cases['should_not']), 1)


if __name__ == '__main__':
    unittest.main()
