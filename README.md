# comment-review

A Claude Code skill that reviews existing code comments and judges each one: leave it, remove it, or reword it.

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

Copy the `comment-review` folder into `~/.claude/skills/` for personal use across every project. Or copy it into `<repo>/.claude/skills/` to scope it to one project.

```bash
git clone https://github.com/AlCalzone/comment-review-skill.git
cp -r comment-review-skill/comment-review ~/.claude/skills/
```

## Scope

Review one function, one or more files, or a whole directory. Narrow the scope to comments touched in a timespan or by an author, using git blame: "the comments Alice added last week."

The skill reports every finding first. It asks before applying anything.

## Rules

The skill judges comments against a bundled copy of the ["Plain" output style](comment-review/references/plain-comments-style.md)'s Comments section. Drop your own copy at `~/.claude/output-styles/plain.md` to override this. Then you can tune the rules without editing the skill itself.
