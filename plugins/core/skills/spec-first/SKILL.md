---
name: spec-first
description: Turn a large or loosely defined request into a written specification before building. Use when work will span several components or more than one session and its requirements, edge cases or trade-offs are not settled yet.
---

# Specification before large work

Time spent making the specification precise pays back more than time spent watching the build.

1. Read what already exists for this area: the code, the issue, the design document.
2. Interview the user. Ask about the hard parts they may not have considered: implementation
   choices, interface and behaviour, edge cases, trade-offs, what must not change. Skip
   questions whose answer is obvious or that you can read from the code. Use the client's
   question tool if it has one, a few questions per round, until nothing material is open.
3. Write the specification on the issue so it stands on its own:
   - what changes: the files and interfaces involved;
   - what is out of scope;
   - the end-to-end check that proves the whole thing works, as a command or a concrete
     observation.
4. The user, or the maintainer the repository names, confirms the specification. That
   confirmation is the approved scope.
5. Build in a fresh session that starts from the specification, so the context holds the plan
   and not the discussion that led to it.
