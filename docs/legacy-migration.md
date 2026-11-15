# Legacy relocation record and verification guide

**What happened (PR 1):** the original Expense Tracker (baseline commit `e1b3984`, tag `legacy-v1`) was moved into `legacy/expense-tracker/` with a rename-only commit. No legacy file content was changed. See [ADR-0006](architecture/adr/0006-strangler-migration.md).

Commands below work in **PowerShell** and **Git Bash** unless marked. **There are no Bash-only scripts in this repository.** The verification scripts are Python (standard library only) so they behave identically on Windows, macOS and Linux. Use `py` on Windows (or `python`); use `python3` on Linux/macOS.

## 1. Safety checks before relocating (preflight)

These were run before the relocation. Repeat them on any other clone *before* applying PR 1. All are read-only.

| Check | Command | Expected |
|---|---|---|
| Clean working tree | `git status --porcelain --untracked-files=all` | no output |
| Correct branch | `git branch --show-current` | `main` |
| Correct baseline | `git rev-parse --short HEAD` | `e1b3984` |
| Nothing unpushed or behind | `git fetch origin` then `git status -sb` | `## main...origin/main`, no `ahead`/`behind` |
| Tag not yet taken | `git tag -l legacy-v1` | no output |
| No conflicting target | PowerShell: `Test-Path legacy` / Git Bash: `test -e legacy && echo EXISTS` | `False` / no output |

If any check does not match, **stop** and resolve it first. Do not force-push or rewrite published history at any point.

## 2. What the relocation did

1. Created the annotated tag `legacy-v1` on `e1b3984` and confirmed it points at that commit.
2. Created branch `chore/relocate-legacy`.
3. `git mv` of all 13 tracked files into `legacy/expense-tracker/` (same relative paths), committed on their own as **rename only**.
4. A second commit adds the new root files, documentation, ADRs and scripts.

## 3. Verify (any machine)

From the repository root:

```
py scripts/verify_relocation.py
```

Expected: six `[PASS]` lines and `ALL CHECKS PASSED`. It confirms the tag is annotated and an ancestor of `HEAD`, all 13 files exist under the new path with **identical blob hashes**, the relocation commit contains only 100% renames, and `git log --follow` still lists every original commit of `app.py`.

Manual equivalents (identical in both shells):

```
git log --oneline --grep "rename only"                     # find the relocation commit hash
git diff --name-status -M100% legacy-v1 <relocation-commit>   # every line starts with R100
git log --oneline --follow -- legacy/expense-tracker/app.py
```

The `--follow` history shows the original commits plus the relocation commit. That extra line is correct.

Runtime smoke test of the legacy app (needs Python 3.10+, internet for `pip`, and port 4949 free):

```
py scripts/verify_legacy.py
```

It copies the legacy app to a temporary folder, installs its requirements in a temporary virtualenv, starts it on `127.0.0.1:4949` with a generated secret (debug off), and checks: start-up, signup, add expense, summary total, Excel export, cross-user delete is refused, logout, API requires login. Nothing in your repository is modified. Add `--use-current-env` to skip the virtualenv if Flask and openpyxl are already installed.

> Windows note: these scripts use only portable Python (`pathlib`, `subprocess` with argument lists, no shell). They were tested on Linux. **They have not been run on Windows.** Please report any failure.

## 4. Docker verification on Windows (not yet verified by the author)

Requires Docker Desktop. Run from the repository root.

```
docker --version
docker compose version
docker compose -f legacy/expense-tracker/docker-compose.yml config
docker compose -f legacy/expense-tracker/docker-compose.yml up --build -d
docker compose -f legacy/expense-tracker/docker-compose.yml ps
```

Check the app responds. In **PowerShell** use `curl.exe` (plain `curl` is an alias for another command):

```
curl.exe -s -o NUL -w "%{http_code}" http://localhost:4949/
```

In **Git Bash**: `curl -s -o /dev/null -w "%{http_code}" http://localhost:4949/`. Expected output: `200`. Then open <http://localhost:4949>, sign up, add an expense.

Stop it:

```
docker compose -f legacy/expense-tracker/docker-compose.yml down        # keeps the data volume
docker compose -f legacy/expense-tracker/docker-compose.yml down -v     # also deletes the data
```

Please report: the output of `config` (success or error), the `ps` output, and the HTTP status code.

**Known Docker caveats caused by the move:**

- The compose file sets a fixed `container_name: expense-tracker`. If an old container with that name still exists, `up` fails with a name conflict. Stop and remove the old one first (`docker rm -f expense-tracker`).
- Docker Compose derives its **project name from the folder containing the compose file**. It is now `expense-tracker`, so the data volume is named differently from any volume created by earlier runs from the old folder. Data in an old volume will not appear. List volumes with `docker volume ls`.
- The compose file contains a placeholder secret (`change-this-to-a-strong-secret-key`). It is public in the repository and must never be used on a networked deployment.

## 5. Local (non-Docker) data

The legacy SQLite file `instance/expenses.db` is git-ignored, so Git does not move it. If you previously ran the app from the repository root, your data is still in that old `instance/` folder. To keep it, copy it into `legacy/expense-tracker/instance/` before running the relocated app. Legacy data migration into LedgerOps is **not required**.

## 6. Rollback

| Situation | Action |
|---|---|
| PR 1 not yet merged | Delete the branch (`git branch -D chore/relocate-legacy`). Nothing on `main` changed |
| PR 1 merged, want to undo | `git revert -m 1 <merge-commit>` (a new commit; no history rewrite) |
| Want the original app exactly as it was | `git checkout legacy-v1` |

Never use force-push on `main`.

## 7. Retirement criteria for the legacy app

Archive the directory and tag `legacy-final` only after the new customer journey (register, open account, deposit, transfer, statement) passes automated end-to-end tests. Until then it stays runnable and unmodified.
