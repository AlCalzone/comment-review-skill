---
name: comment-review
description: Reviews existing code comments against the "Comments" rules in the user's active Plain output style (falling back to a bundled copy of those rules if the user has none configured) and decides, per comment, whether to leave it, remove it, or reword/split it. Scope can be a single function, one or more files, or a whole directory, optionally narrowed to comments touched within a timespan or by an author (via git blame). Use this whenever the user asks to review, audit, clean up, or tighten comments — "review the comments in X", "are these comments any good", "clean up the comments Alice added last week", "does this file have any dead-weight comments" — not for reviewing code logic, correctness, or design (use /code-review or /deep-review for that).
---

# Comment review

This skill judges *existing* comments, one at a time, against the rules the
user has written down for what a good comment looks like. It does not review
logic, naming, or design. It only reviews comments.

Read the rules fresh every run. Don't trust anything memorized about them.
Use `~/.claude/output-styles/plain.md` if it exists. Otherwise use the
bundled copy at `${CLAUDE_SKILL_DIR}/references/plain-comments-style.md`.
Either file can change between runs, and a stale copy of the rules would
silently drift from what they actually say.

## Phase 0 — Resolve scope and any filter

Figure out, from the user's request, what's in scope:

- **A function** — a file path plus a function/method name.
- **One or more files** — explicit paths.
- **A directory** — everything under it.

Also figure out whether they mentioned a filter: a timespan ("from the last
week", "since Tuesday"), an author ("that Alice wrote", "in my commits"), or
both. Don't ask about a filter if they didn't mention one. Review everything
in scope by default.

Run the bundled finder to locate every comment block in scope. This avoids
re-deriving comment boundaries and blame info by hand each time:

```
python3 ${CLAUDE_SKILL_DIR}/scripts/find_comments.py <path>... \
  [--function NAME] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--author PATTERN]
```

It prints a JSON array of comment blocks with file, line range, text, blame
author/date, and a few lines of surrounding code for context. Read
`${CLAUDE_SKILL_DIR}/scripts/find_comments.py --help` if you need the exact
flags again. Don't re-derive them from memory.

This is a line-marker scan, not a real parser. String-embedded `//`, `#`, or
`<!--` inside a URL, a regex, or an HTML string can trip it up. Skim its
output on a file with a lot of those before trusting every entry. A rare
false positive there is possible. If it finds nothing in scope, say so and
stop. Don't invent findings.

## Phase 1 — Load the current rules

Read `~/.claude/output-styles/plain.md` in full if it exists. If it
doesn't, read `${CLAUDE_SKILL_DIR}/references/plain-comments-style.md`
instead. The `## Comments` section is the authoritative rule set. The
file's opening paragraph sets tone and audience, and the `## Plain
language` section informs borderline calls. Don't paraphrase from memory.
The wording of a rule, like what counts as "X, not Y" framing, matters for
applying it consistently.

## Phase 2 — Judge each comment

For a single function or a small handful of files, do this yourself, inline,
reading the files directly. No need for subagents on a small scope.

For a whole directory or many files, fan out. Use one `Agent` call per file,
or a small batch of files that together hold few comments, running in
parallel. Give each agent the full text of the Comments section from
Phase 1, its assigned slice of the `find_comments.py` output, and
instructions to return one verdict per comment. Each agent needs
`Bash`/`Grep` on the repo, not just its own file, for the consistency check
below. A comment can only be judged "generic knowledge" by checking
whether comparable code elsewhere actually lacks the same kind of comment.
Collect every agent's verdicts into one list before moving on. Don't
present findings file-by-file as agents finish. The consistency check for
one file can depend on what another file's agent finds.

Before the full checklist, make one fast first pass over every comment.
Check only redundancy (question 1) and mood (question 6). Both are cheap,
binary checks with no judgment call involved, and both have a history of
getting lost once attention moves to chaining, jargon, and placement.

Redundancy here means restating the *one specific line* right next to it:
a prop name and type, the very next `v-if`, a selector. It's not the same
thing as summarizing a multi-line block. That's a navigation bookmark
instead. See plain.md's bookmark exception and its bookmark-vs-redundant
test. Apply that test here before marking anything redundant just because
it sits above a block.

Apply the rest of the checklist to what's left, and to what this pass
already caught. A mood-fixed comment can still need a chaining or jargon
fix too.

For every remaining comment, walk through these questions in order. They're
the condensed form of the Comments-section rules in plain.md. That file
holds the full reasoning and examples for each one. Don't re-derive from
memory. These numbers exist to make the judgment read as one pass, saving
you from re-deriving that reasoning each time:

1. Would deleting it lose a fact the code can't otherwise show? Check
   fact by fact, not by overall shape. A comment can share its subject
   with an adjacent declaration, making it look like pure restatement. It
   can still carry one distinct, unverified claim buried in it, though.
   Verify that claim against where the value actually comes from before
   concluding there's nothing left to keep. If only part is redundant,
   reword to keep the surviving fact rather than removing the whole thing.
2. Is it explaining common language, API, or framework knowledge, rather
   than a domain fact or spec guarantee the code's correctness actually
   depends on? Check comparable code nearby for consistency.
3. Does it narrate the failure being avoided instead of stating the rule
   positively?
4. Does it use "X, not Y" or "X rather than Y" contrast?
5. Does it exist to stop a "helpful" simplification, but state it as a
   neutral observation instead of a requirement ("must")?
6. If it narrates a specific action the code takes right there, is it in
   imperative mood? A general design fact is exempt.
7. Is it one clause per sentence? Count every distinct fact chained
   together however it's joined: comma, colon, semicolon, and, so,
   because, which. One opening fact plus one trailing why is fine. Three
   or more chained facts is not.
8. When a split is genuinely needed, does it use the fewest sentences
   that keep the facts, action leading and consequence trailing?
9. Is it placed next to the line it explains, as a complete sentence with
   an explicit subject and verb? It shouldn't lean on an adjacent
   declaration, and it shouldn't just staple a name before a colon.
10. Jargon, or an idiom that doesn't map to the literal action?
11. Mechanical nits: capitalization, trailing period, NOT/NONE emphasis,
    right marker. If this is the *only* issue, file it under `[NIT]`
    (Phase 3) instead of its own `[REWORD]`. If it rides along with a
    substantive fix, fold it into that `[REWORD]` instead.
12. Redundant with an adjacent comment, or with code right next to it?
    This includes a "why" clause on its own that states nothing beyond
    what's already self-evident, in a design or class-doc comment as much
    as an action comment.

Three cross-cutting checks. Each is easy to skip, because nothing above
names it directly:

- **Re-read the result, not just the trigger.** Fixing one flagged issue,
  like a chain to split or a mood to swap, is a draft, not the finish
  line. A split that satisfies question 7 can still leave jargon behind
  that question 10 should catch, because judging the *original* text
  against each question isn't the same as judging the *rewritten* text.
  After any fix, re-read the result fresh and ask whether it's the
  plainest way to say the thing.
- **Cite the line, don't generalize.** A verdict's `why` must point at the
  specific line(s) that prove it. "The catch never logs anything" next to
  a `console.error(...)` call is a wrong verdict from an unverified claim.
  Citing the exact line would have caught it. This applies most to a
  `remove` grounded in an absence, like "it never X's": re-read what the
  claim depends on before finalizing. It doesn't apply to a claim about an
  external dependency's contract that the file legitimately can't show,
  like a library's behavior or a browser API's guarantee. That's normal
  for an integration-constraint comment, not a reason to doubt it.
- **Check consistency within the scope.** When question 1 turns on
  legitimate design rationale versus unnecessary broader-system
  explanation, check other comments already judged in this same scope for
  the same shape. Two functions each stating an external fact plus a
  consequence should get the same answer on that question. This doesn't
  mean they land on the same final verdict, though: each still needs
  every other question run against it independently, and one might have a
  chaining or contrast problem the other doesn't.

Land on exactly one verdict: **leave as is**, **remove**, or **reword**. For
reword, state the replacement text. Split is a form of reword where the
replacement is more than one comment in more than one place. Say where
each piece goes.

Don't invent findings to look thorough. A comment that's already clean
gets "leave as is" and doesn't need a novel justification. Most real
codebases have plenty of those, and the report should reflect that rather
than manufacture nitpicks.

## Phase 3 — Report

Reports commonly get read in a plain-text viewer or terminal that doesn't
render markdown. Free-form prose paragraphs turn into a wall of text
that's hard to scan or grep there. Use this fixed, tagged shape instead,
one block per file:

```
## <relative/path/to/file>

[REMOVE] <line>-<line>
  <current text>
  why: <one line>

[REWORD] <line>-<line>
  - <current text, one line per source line>
  + <replacement text, one line per source line>
  why: <one line>

[MOVE] <line>-<line> -> <new location>
  - <current text>
  + <replacement text, at the new location>
  why: <one line>

[NIT] <line>: <trailing period | capitalize first word | NOT/NONE emphasis | wrong marker>
[NIT] <line>: <...>

<file>: N left as is, N mechanical-only nits
```

`[REMOVE]`, `[REWORD]`, or `[MOVE]` is always the first token on the line,
immediately followed by `file:line`. A split is a reword that also
relocates. It becomes `[MOVE]`, with each resulting piece as its own `+`
line and a note on where it goes. This lets a reader `grep` by verdict or by
file/line instead of parsing prose. Skip "leave as is" comments
individually. End each file's block with a single count instead.

`[NIT]` entries are for comments whose only flaw is mechanical, per
checklist item 11. Skip the `why` and the before/after block. Just give
the location and which nit, one line each. Don't give these the same
weight as a `[REMOVE]`/`[REWORD]`: they don't change what the comment
says, and a reader shouldn't have to wade through a page of "drop the
period" lines to
find the fixes that do. If a file's nits are all the same kind, condense
further to one line: "[NIT] lines 291, 294, 298, 335: trailing period."

End the whole report with a one-line grand total: "N reviewed: N reworded,
N removed, N left as is, N mechanical-only nits."

## Phase 4 — Ask how to proceed

`[NIT]` entries never go through this step. They don't need the user's
review. Apply them directly in Phase 5, regardless of which mode is
chosen below. This question is only about the `[REMOVE]`/`[REWORD]`/`[MOVE]`
entries.

Don't apply anything yet. Ask the user, in one question:

- **Step by step** — walk through each change for confirmation, the way a
  human reviewer would go comment by comment: revise, skip, or confirm
  each, applying as you go.
- **Apply everything now** — make all the reword/remove edits directly,
  then ask whether to also stage, commit, and/or push. Offer these as one
  follow-up, not three separate ones. A commit message should describe the
  comment cleanup, not restate every individual change.

If the user's original request already made this clear, skip asking and
proceed. "Clean these up and commit" implies apply-everything. "Let's go
through them" implies step by step. Don't force a redundant confirmation
when the answer is already in what they said.

## Phase 5 — Apply

Whichever mode: edit what was reworded or marked for removal, plus every
`[NIT]` regardless of mode. Check whether the project has a lint or
typecheck script, in `package.json` or a `Makefile`, and run it as a sanity
check that nothing was mangled. These are comment-only edits, but a botched
removal can still break a block comment's open/close pairing. In
apply-everything mode, only proceed to stage/commit/push if that check
passes, or none exists. Surface a failure and stop rather than committing
broken code.
