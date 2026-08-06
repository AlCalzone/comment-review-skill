#!/usr/bin/env python3
"""Locate comment blocks in one or more files and, in a git repo, attach blame metadata.

Usage:
    find_comments.py PATH [PATH ...] [--since DATE] [--until DATE] [--author PATTERN]
                      [--function NAME] [--ext .py,.js,...]

Output: a JSON array on stdout, one object per comment block:
    {
      "file": "src/foo.ts",
      "start_line": 12,
      "end_line": 13,
      "text": "// Clamp to 0xFF because ...",
      "blame_author": "Jane Doe" | null,
      "blame_date": "2026-07-01" | null,
      "context_before": "<up to 3 lines before the block>",
      "context_after": "<up to 3 lines after the block>"
    }

This only finds comment *locations* and raw text — it does not judge them.
That judgment (leave / remove / reword) is the caller's job, applying the
rules in the active Plain output style.

Comment-block detection is a per-line marker scan, not a real parser, so it
can misfire on a comment marker that appears inside a string literal. Skim
the output before trusting it on a file with lots of string-embedded `//`
or `#` (URLs, regexes) — false positives there are rare but possible.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

LINE_MARKERS = {
    ".py": "#", ".rb": "#", ".sh": "#", ".bash": "#", ".zsh": "#", ".yml": "#", ".yaml": "#",
    ".js": "//", ".jsx": "//", ".ts": "//", ".tsx": "//", ".mjs": "//", ".cjs": "//",
    ".java": "//", ".c": "//", ".h": "//", ".cpp": "//", ".hpp": "//", ".cc": "//",
    ".go": "//", ".rs": "//", ".swift": "//", ".kt": "//", ".cs": "//", ".php": "//",
    ".vue": "//",  # inside <script>; template comments handled by BLOCK_MARKERS below
}

# (open, close) pairs checked in file order; a file can have more than one kind
# (e.g. .vue has both <!-- --> in <template> and /* */ or // in <script>).
BLOCK_MARKERS = {
    ".js": [("/*", "*/")], ".jsx": [("/*", "*/")], ".ts": [("/*", "*/")], ".tsx": [("/*", "*/")],
    ".mjs": [("/*", "*/")], ".cjs": [("/*", "*/")], ".java": [("/*", "*/")], ".c": [("/*", "*/")],
    ".h": [("/*", "*/")], ".cpp": [("/*", "*/")], ".hpp": [("/*", "*/")], ".cc": [("/*", "*/")],
    ".go": [("/*", "*/")], ".rs": [("/*", "*/")], ".swift": [("/*", "*/")], ".kt": [("/*", "*/")],
    ".cs": [("/*", "*/")], ".php": [("/*", "*/")], ".css": [("/*", "*/")], ".scss": [("/*", "*/")],
    ".vue": [("/*", "*/"), ("<!--", "-->")],
    ".html": [("<!--", "-->")], ".htm": [("<!--", "-->")], ".xml": [("<!--", "-->")],
    ".py": [('"""', '"""'), ("'''", "'''")],
}


def find_blocks(lines, ext):
    """Return a list of (start_line, end_line) 1-indexed, in file order."""
    blocks = []
    line_marker = LINE_MARKERS.get(ext)
    block_pairs = BLOCK_MARKERS.get(ext, [])
    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()
        matched = False

        # Chained line comments: consume consecutive lines starting with the marker.
        if line_marker and stripped.startswith(line_marker):
            start = i + 1
            while i < n and lines[i].strip().startswith(line_marker):
                i += 1
            blocks.append((start, i))
            matched = True

        if not matched:
            for open_m, close_m in block_pairs:
                if stripped.startswith(open_m):
                    start = i + 1
                    if close_m in lines[i][lines[i].find(open_m) + len(open_m):]:
                        blocks.append((start, start))
                        i += 1
                    else:
                        j = i + 1
                        while j < n and close_m not in lines[j]:
                            j += 1
                        blocks.append((start, min(j + 1, n)))
                        i = j + 1
                    matched = True
                    break

        if not matched:
            i += 1
    return blocks


def context(lines, start, end, radius=3):
    before = "".join(lines[max(0, start - 1 - radius):start - 1])
    after = "".join(lines[end:min(len(lines), end + radius)])
    return before.rstrip("\n"), after.rstrip("\n")


def git_root(path):
    try:
        out = subprocess.run(
            ["git", "-C", os.path.dirname(os.path.abspath(path)) or ".", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


def blame_range(repo_root, rel_path, start, end):
    """Most recent author+date among the block's lines, or (None, None)."""
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "blame", "--porcelain", "-L", f"{start},{end}", "--", rel_path],
            capture_output=True, text=True, check=True,
        )
    except Exception:
        return None, None
    best_author, best_ts = None, -1
    author = None
    for line in out.stdout.splitlines():
        if line.startswith("author "):
            author = line[len("author "):]
        elif line.startswith("author-time "):
            ts = int(line[len("author-time "):])
            if ts > best_ts:
                best_ts, best_author = ts, author
    if best_ts < 0:
        return None, None
    return best_author, datetime.fromtimestamp(best_ts, tz=timezone.utc).strftime("%Y-%m-%d")


def function_bounds(lines, name):
    """Heuristic: first line whose text contains the name followed by `(`,
    or a Vue/JS arrow-function assignment `name = (` / `name(...) {`. Extends
    to the matching closing brace by indentation-agnostic brace counting from
    that line onward. Returns (start, end) 1-indexed, or None."""
    pat = re.compile(r"\b" + re.escape(name) + r"\b\s*[:=]?\s*\(")
    start = None
    for idx, line in enumerate(lines):
        if pat.search(line):
            start = idx
            break
    if start is None:
        return None
    depth = 0
    started = False
    for idx in range(start, len(lines)):
        depth += lines[idx].count("{") - lines[idx].count("}")
        if "{" in lines[idx]:
            started = True
        if started and depth <= 0:
            return start + 1, idx + 1
    return start + 1, len(lines)


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--since", help="only comments last touched on/after this date (YYYY-MM-DD)")
    ap.add_argument("--until", help="only comments last touched on/before this date (YYYY-MM-DD)")
    ap.add_argument("--author", help="substring match against the git blame author")
    ap.add_argument("--function", help="scope to one function's body plus its header comment (single-file only)")
    ap.add_argument("--ext", help="comma-separated extensions to include when a path is a directory")
    args = ap.parse_args()

    exts = set(e if e.startswith(".") else "." + e for e in args.ext.split(",")) if args.ext else None

    files = []
    for p in args.paths:
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "dist", "build")]
                for name in names:
                    ext = os.path.splitext(name)[1]
                    if ext in LINE_MARKERS or ext in BLOCK_MARKERS:
                        if exts is None or ext in exts:
                            files.append(os.path.join(root, name))
        else:
            files.append(p)

    if args.function and len(files) != 1:
        print("--function requires exactly one file", file=sys.stderr)
        sys.exit(1)

    since = parse_date(args.since) if args.since else None
    until = parse_date(args.until) if args.until else None

    results = []
    for path in files:
        ext = os.path.splitext(path)[1]
        if ext not in LINE_MARKERS and ext not in BLOCK_MARKERS:
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        allowed_range = None
        if args.function:
            bounds = function_bounds(lines, args.function)
            if bounds is None:
                print(f"function {args.function!r} not found in {path}", file=sys.stderr)
                sys.exit(1)
            fstart, fend = bounds
            allowed_range = (max(1, fstart - 5), fend)

        root = git_root(path)
        rel = os.path.relpath(path, root) if root else None

        for start, end in find_blocks(lines, ext):
            if allowed_range and not (allowed_range[0] <= start <= allowed_range[1]):
                continue
            author, date = (blame_range(root, rel, start, end) if root else (None, None))
            if args.author and (not author or args.author.lower() not in author.lower()):
                continue
            if (since or until) and date:
                d = parse_date(date)
                if since and d < since:
                    continue
                if until and d > until:
                    continue
            elif since or until:
                continue

            before, after = context(lines, start, end)
            results.append({
                "file": path,
                "start_line": start,
                "end_line": end,
                "text": "".join(lines[start - 1:end]).rstrip("\n"),
                "blame_author": author,
                "blame_date": date,
                "context_before": before,
                "context_after": after,
            })

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
