# comment-review

A portable agent skill that reviews existing code comments and judges each one: leave it, remove it, or reword it.

## Example

```
[REMOVE] cache.js:1
  // Increment the counter
  why: the function name and body already say this

[REWORD] payment.ts:1-2
  - // Round to the nearest cent, not the nearest dollar, so a $0.005 rounding
  - // error never accumulates across a large batch of transactions
  + // Round to the nearest cent so a $0.005 rounding error never accumulates
  + // across a large batch of transactions
  why: drops the "not the nearest dollar" contrast, keeps the batch-accumulation reason
```

## Install

Copy the `comment-review` folder into your agent's skills directory — `~/.claude/skills/` for Claude Code, for personal use across every project. Or copy it into `<repo>/.claude/skills/` to scope it to one project.

```bash
git clone https://github.com/AlCalzone/comment-review-skill.git
cp -r comment-review-skill/comment-review ~/.claude/skills/
```

To share one copy between several agents, keep it in `~/.agents/skills/` and symlink it into each agent's skills directory:

```bash
cp -r comment-review-skill/comment-review ~/.agents/skills/
ln -s ~/.agents/skills/comment-review ~/.claude/skills/comment-review
```

## Scope

Review one function, one or more files, or a whole directory. Narrow the scope to comments touched in a timespan or by an author, using git blame: "the comments Alice added last week."

A plain cleanup request gets fixed autonomously, then reported. Say "just give me the report" for a report-only pass, or "let's go through them" to confirm each change one at a time. After anything gets applied, the skill asks whether to leave it staged or commit and push.

## Rules

The skill judges comments against a bundled copy of the ["I'm only human"](comment-review/references/im-only-human-comments-style.md) rules' Comments section. Override it with your own copy, and tune the rules without editing the skill itself. The first of these that exists wins:

1. `~/.agents/im-only-human.md`
2. `~/.claude/output-styles/im-only-human.md`
3. the bundled copy

Recommended companion: install [im-only-human](https://github.com/AlCalzone/im-only-human) as your global instructions or output style. It applies the same rules to everyday answers and prose, on top of what this skill checks in comments.
