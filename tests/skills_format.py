#!/usr/bin/env python3
"""Checks the always-loaded rules and the skills: python3 tests/skills_format.py.

Both clients (Claude Code, Codex) read the same skill files, so the checks keep them inside what
both accept: the Agent Skills frontmatter (name, description) plus the one Claude Code extension
allowed here, and the size limits past which adherence drops or a client truncates. Skill names
are unique across all plugins, and every skill, path or link the rules name exists. No Claude
skill file and not rules/core.md names Codex: Codex's side lives in the codex plugin and in
rules/codex.md, which only a Codex install loads (#98). The standard
and where these checks are stricter: plugins/core/skills/repo-docs/skill-standard.md.

The skill budget (#125): BODY_BUDGET holds the bytes of each SKILL.md body (after the
frontmatter) and DESCRIPTIONS_BUDGET the bytes of all descriptions together, as they were when
last set. A change that grows a body or the sum past its number fails here until the same change
raises the number, so the growth shows in the diff; a change that trims a skill lowers its number
to the new size. A new skill gets its row in the change that adds it.
"""
import os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ALLOWED = {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools',
           'disable-model-invocation'}
RULES_LIMIT = 8000
LINK = re.compile(r'\]\(([^)#]+)(?:#[^)]*)?\)')
CHARS_PER_TOKEN = 4  # an estimate: no tokenizer here, and the bound is a recommendation
PLAIN_NEVER_FIRST = '[]{}>|*&!%@`,?-#'  # YAML indicators that cannot start a plain value
# bytes; set 2026-11-23 (#125). Raise a number only in the change that grows the skill.
BODY_BUDGET = {
    'archive-finished-chats': 6157, 'check-web-deploy': 5275, 'cleanup-merged': 7737,
    'codex-issue-chats': 7232, 'codex-worker': 9437, 'efficient-design': 3676,
    'issue-handover': 19051, 'open-issue': 3784, 'repo-docs': 3563, 'requirements': 7196,
    'review-change': 7078, 'review-security': 5732, 'ship-change': 13539, 'spec-first': 1313,
    'verify': 3695,
}
DESCRIPTIONS_BUDGET = 5972
errors = []


def fail(msg):
    errors.append(msg)


def relative_links(text):
    return [link for link in LINK.findall(text) if not link.startswith(('http', '/'))]


CODEX_RULES_LIMIT = 2000  # rules/codex.md: inlined after core.md in Codex's block only (#98)
rules_path = os.path.join(ROOT, 'rules', 'core.md')
with open(rules_path, 'rb') as f:
    rules_bytes = f.read()
rules = rules_bytes.decode('utf-8')
if len(rules_bytes) >= RULES_LIMIT:
    fail(f'rules/core.md is {len(rules_bytes)} bytes; keep it under {RULES_LIMIT}')
if rules.count('⛔'):
    fail('rules/core.md uses a stop sign; state the rule and its reason instead')

skills = {}  # name -> folder
descriptions_bytes = 0
plugins_dir = os.path.join(ROOT, 'plugins')
for plugin in sorted(os.listdir(plugins_dir)):
    skills_dir = os.path.join(plugins_dir, plugin, 'skills')
    if not os.path.isdir(skills_dir):
        continue
    for name in sorted(os.listdir(skills_dir)):
        folder = os.path.join(skills_dir, name)
        if not os.path.isdir(folder):
            continue
        if name in skills:
            fail(f'{plugin}/{name}: a skill of that name is already in {skills[name]}')
        skills[name] = os.path.relpath(folder, ROOT)
        path = os.path.join(folder, 'SKILL.md')
        if not os.path.isfile(path):
            fail(f'{plugin}/{name}: no SKILL.md'); continue
        with open(path, encoding='utf-8') as f:
            text = f.read()
        m = re.match(r'---\n(.*?)\n---\n', text, re.S)
        if not m:
            fail(f'{plugin}/{name}: frontmatter must open the file'); continue
        head = re.sub(r'^metadata:[ \t]*\n(?:[ \t].*\n?|\n)+', 'metadata:\n', m.group(1), flags=re.M)
        front = dict(line.split(':', 1) for line in head.splitlines() if ':' in line)
        front = {k.strip(): v.strip() for k, v in front.items()}
        for key in front:
            if key not in ALLOWED:
                fail(f'{plugin}/{name}: frontmatter key {key!r} is not one both clients accept')
            value = front[key]
            quoted = value[:1] in ('"', "'") or (
                key in ('allowed-tools', 'metadata') and value[:1] in ('[', '{'))
            if not quoted and (re.search(r':(\s|$)', value) or re.search(r'\s#', value)
                               or (value and value[0] in PLAIN_NEVER_FIRST)):
                fail(f'{plugin}/{name}: frontmatter {key} needs quotes: in a plain YAML value '
                     '": " or a final ":" is an error, " #" starts a comment, and it may not '
                     'start with one of ' + PLAIN_NEVER_FIRST)
        if front.get('name') != name:
            fail(f'{plugin}/{name}: frontmatter name {front.get("name")!r} differs from the folder')
        if not re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', name) or len(name) > 64:
            fail(f'{plugin}/{name}: name must be lowercase words joined by hyphens, at most 64')
        desc = front.get('description', '')
        if not 40 <= len(desc) <= 500:
            fail(f'{plugin}/{name}: description is {len(desc)} characters; keep it 40 to 500')
        if desc.startswith(('"', "'")):
            fail(f'{plugin}/{name}: description must be a plain YAML scalar, without quotes')
        if 'compatibility' in front and not 1 <= len(front['compatibility']) <= 500:
            fail(f'{plugin}/{name}: compatibility is {len(front["compatibility"])} characters; '
                 '1 to 500 if present')
        body = text[m.end():]
        descriptions_bytes += len(desc.encode('utf-8'))
        body_bytes = len(body.encode('utf-8'))
        if name not in BODY_BUDGET:
            fail(f'{plugin}/{name}: no row in BODY_BUDGET (tests/skills_format.py); add '
                 f'{name!r}: {body_bytes}')
        elif body_bytes > BODY_BUDGET[name]:
            fail(f'{plugin}/{name}: SKILL.md body is {body_bytes} bytes, over its budget of '
                 f'{BODY_BUDGET[name]}; trim it, or raise BODY_BUDGET[{name!r}] in '
                 'tests/skills_format.py in this change')
        if text.count('\n') >= 500:
            fail(f'{plugin}/{name}: SKILL.md has {text.count(chr(10))} lines, not under 500; '
                 'move detail to a reference file')
        if len(body) // CHARS_PER_TOKEN >= 5000:
            fail(f'{plugin}/{name}: SKILL.md body is about {len(body) // CHARS_PER_TOKEN} tokens, '
                 'not under 5000; move detail to a reference file')
        direct = {os.path.normpath(link) for link in relative_links(body)}
        for link in relative_links(body):
            if not os.path.exists(os.path.join(folder, link)):
                fail(f'{plugin}/{name}: link to missing file {link}')
        linked_md = {r for r in direct
                     if r.endswith('.md') and os.path.isfile(os.path.join(folder, r))}
        top_md = {p for p in os.listdir(folder) if p.endswith('.md') and p != 'SKILL.md'}
        for md in sorted(linked_md | top_md):
            with open(os.path.join(folder, md), encoding='utf-8') as f:
                content = f.read()
            for link in relative_links(content):
                target = os.path.normpath(os.path.join(os.path.dirname(md), link))
                if not os.path.exists(os.path.join(folder, target)):
                    fail(f'{plugin}/{name}/{md}: link to missing file {link}')
                elif md in direct and not target.startswith('..') and \
                        target not in direct | {'SKILL.md'}:
                    fail(f'{plugin}/{name}/{md}: links to {target}, which SKILL.md does not: '
                         'keep references one level deep')
        manual = front.get('disable-model-invocation', '').lower() == 'true'
        yaml_path = os.path.join(folder, 'agents', 'openai.yaml')
        codex_manual = os.path.isfile(yaml_path) and \
            'allow_implicit_invocation: false' in open(yaml_path, encoding='utf-8').read()
        if manual != codex_manual:
            fail(f'{plugin}/{name}: user-only invocation must be set for both clients '
                 '(disable-model-invocation in SKILL.md and allow_implicit_invocation: false '
                 'in agents/openai.yaml)')

for name in sorted(set(BODY_BUDGET) - set(skills)):
    fail(f'BODY_BUDGET in tests/skills_format.py has a row for {name}, which is no skill')
if descriptions_bytes > DESCRIPTIONS_BUDGET:
    fail(f'the descriptions of all skills are {descriptions_bytes} bytes together, over the budget '
         f'of {DESCRIPTIONS_BUDGET}; shorten one, or raise DESCRIPTIONS_BUDGET in '
         'tests/skills_format.py in this change')
for skill in re.findall(r'`([a-z0-9-]+)` skill', rules):
    if skill not in skills:
        fail(f'rules/core.md names a skill that does not exist: {skill}')
if 'codex' in rules.lower():
    fail('rules/core.md names Codex; Codex\'s side goes in rules/codex.md, which only Codex loads')
with open(os.path.join(ROOT, 'rules', 'codex.md'), 'rb') as f:
    codex_bytes = f.read()
if len(codex_bytes) >= CODEX_RULES_LIMIT:
    fail(f'rules/codex.md is {len(codex_bytes)} bytes; keep it under {CODEX_RULES_LIMIT}')
for skill in re.findall(r'`([a-z0-9]+(?:-[a-z0-9]+)+)`', codex_bytes.decode('utf-8')):
    if skill not in skills:  # every hyphenated name in backticks there is a skill
        fail(f'rules/codex.md names a skill that does not exist: {skill}')
for name, folder in skills.items():  # Claude's skills carry no Codex text (#98)
    if folder.startswith(os.path.join('plugins', 'codex') + os.sep):
        continue
    for base, _, files in os.walk(os.path.join(ROOT, folder)):
        for file in files:
            with open(os.path.join(base, file), 'rb') as f:  # a binary asset reads too
                if b'codex' in f.read().lower():
                    fail(f'{folder}/{file} names Codex; it belongs in the codex plugin or '
                         'rules/codex.md, which only a Codex install loads')
for link in LINK.findall(rules):
    if not link.startswith('http') and not os.path.exists(os.path.join(ROOT, link)):
        fail(f'rules/core.md links to a missing file: {link}')

if errors:
    print('\n'.join(errors)); sys.exit(1)
print(f'OK: rules/core.md {len(rules_bytes)} bytes; {len(skills)} skills within their budgets '
      f'(descriptions {descriptions_bytes} of {DESCRIPTIONS_BUDGET} bytes): '
      + ', '.join(sorted(skills)))
