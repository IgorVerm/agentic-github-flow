---
name: efficient-design
description: Check that the work a change does per frame, tick, request, render, job run or keystroke grows with what changed, not with all the data - a short checklist for games, web apps, data pipelines and tools. Use when designing or changing code that runs repeatedly (a system, handler, loop, query, scheduled job) or over growing data, when asked whether something is efficient or scales, and when reviewing a change before it lands.
---

# Work grows with what changed, not with all data

A change can be correct and still do its work over everything on every event: every entity each
frame, every row each request, every file each build. Usually a form exists whose work grows with
what changed. Find it while designing, not after someone asks "is this efficient?".

## The checklist

Go through it for each part of the change that runs repeatedly or over data that grows.

1. **Per event, what does the work grow with?** Name the event (frame, tick, request, render, job
   run, keystroke, commit) and what the work grows with: what changed, the input that matters,
   or all the data (all entities, rows, files, users), or faster than the data (every pair, a
   scan inside a scan). All the data where it could be what changed is the finding this skill
   exists for.
2. **Rebuilt every event?** Collections, maps, queries, copies, allocations, sorted lists,
   parsed configuration and derived values that could be kept and updated when their inputs
   change.
3. **Change detection the platform offers.** ECS change filters and events, observers and
   signals, dirty flags, memoisation, database indexes and queries for what changed since a
   mark, incremental builds, caches keyed on content.
4. **Data shaped for the most frequent access.** A map or index instead of a search, a bitmask
   instead of a scan, one lookup per group instead of one per item, one batched query instead of
   one per row.
5. **The cost in one line,** in the size that grows, with that size named:
   `per frame O(changed buildings); full rebuild O(buildings) only at load`. Measured where a
   measurement is cheap: the core rule *Measure instead of guessing*.
6. **Simple stays allowed.** Work over a small, bounded size is fine when the line of item 5
   states the bound and why it holds (`n ≤ 16 inventory slots`, `once per deploy`).

## Hidden whole-data work

The costly loop is often not written as a loop:

- a search inside a loop: `in` or `index` on a list, `find` or `filter` per item, a
  `querySelectorAll` per element;
- a query per item: an ORM's lazy load in a loop (the N+1 query), one HTTP call per row;
- a whole recompute set off by identity: a UI tree re-rendered because a new object or function
  is made on every render, a cache key that changes every time;
- a full scan behind a convenience call: counting, sorting or serialising everything to read one
  value; re-reading or re-parsing a file or configuration on every call; loading a whole table
  or file to use one page of it.

## Gotchas

- A cache or incremental update must stay correct when its inputs change. Name what invalidates
  it, and test that case: a stale result is a defect, a slow one is only a cost.
- Do not add a cache, index or dirty flag for a size that item 6 already bounds; it adds a way
  to be wrong for nothing.

## At design

Write the line of item 5 in the design note or the issue before building; it becomes the
`Efficient design:` line of the pull request body or the landing comment.

## At review

The reviewer goes through the checklist on the diff and checks the author's `Efficient design:`
line against it, one entry per part that runs repeatedly, and corrects or rejects it, for
example:

`Efficient design: building colours per frame O(changed buildings) via change filter; tooltip
lookup O(1) map; full rebuild O(buildings) at load only.`

What goes back before the change lands is set by the core rule *Work grows with what changed*.
A finding names the event, what the work grows with now, and the form whose work grows with what
changed.
