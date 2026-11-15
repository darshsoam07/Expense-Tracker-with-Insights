#!/usr/bin/env python3
"""Verify the legacy relocation preserved file contents and Git history.

Read-only. Standard library only. Works the same in PowerShell and Git Bash:

    python scripts/verify_relocation.py          (Windows: py scripts/verify_relocation.py)

Checks:
  1. Tag legacy-v1 exists, is an annotated tag, and is an ancestor of HEAD.
  2. Every file at the tag exists under legacy/expense-tracker/ with an
     identical blob hash (content is byte-identical).
  3. The first commit after the tag changes nothing except 100% renames.
  4. `git log --follow` still lists every original commit for legacy/app.py.
"""
import subprocess
import sys

TAG = "legacy-v1"
PREFIX = "legacy/expense-tracker/"
results = []


def git(*args):
    p = subprocess.run(["git", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout.strip()


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def tree(rev):
    out = git("ls-tree", "-r", rev, "--format=%(objectname)\t%(path)")
    return {path: blob for blob, path in (l.split("\t", 1) for l in out.splitlines())}


try:
    check("tag legacy-v1 is an annotated tag", git("cat-file", "-t", TAG) == "tag")
    base = git("rev-list", "-n1", TAG)
    anc = subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"]).returncode == 0
    check("baseline commit is an ancestor of HEAD", anc, base[:7])

    before, after = tree(TAG), tree("HEAD")
    missing = [p for p in before if PREFIX + p not in after]
    changed = [p for p in before if PREFIX + p in after and after[PREFIX + p] != before[p]]
    check(f"all {len(before)} baseline files exist under {PREFIX}", not missing, ", ".join(missing))
    check("blob hashes identical (content byte-identical)", not changed, ", ".join(changed))

    first = git("rev-list", "--reverse", "--ancestry-path", f"{base}..HEAD").splitlines()[0]
    diff = git("diff", "--name-status", "-M100%", base, first).splitlines()
    non_r100 = [l for l in diff if not l.startswith("R100")]
    check("relocation commit contains only 100% renames", not non_r100 and len(diff) == len(before),
          f"{len(diff)} renames in {first[:7]}")

    orig = set(git("log", "--format=%h", base, "--", "app.py").split())
    followed = set(git("log", "--format=%h", "--follow", "--", PREFIX + "app.py").split())
    check("git log --follow keeps every original commit of app.py", orig <= followed,
          f"{len(orig)} original, {len(followed)} followed (+1 is the relocation commit)")
except Exception as exc:  # noqa: BLE001 - report any failure clearly
    check("verification ran without error", False, str(exc))

print("\nRESULT:", "ALL CHECKS PASSED" if all(results) else "FAILED")
sys.exit(0 if all(results) else 1)
