#!/usr/bin/env python3
"""Smoke-test the relocated legacy Expense Tracker. Standard library only.

    python scripts/verify_legacy.py          (Windows: py scripts/verify_legacy.py)

What it does (nothing in your repo is modified):
  * copies legacy/expense-tracker/ to a temp folder,
  * creates a temp virtualenv and installs its requirements.txt,
  * starts the app on 127.0.0.1:4949 with a freshly generated secret
    (debug off, reloader off) and exercises the main flows,
  * stops the app and deletes the temp folder.

Needs: Python 3.10+, internet access for pip, and port 4949 free.
Use --use-current-env to skip the venv if Flask and openpyxl are installed.
"""
import argparse
import http.cookiejar
import json
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PORT = 4949
BASE = f"http://127.0.0.1:{PORT}"
LEGACY = Path(__file__).resolve().parent.parent / "legacy" / "expense-tracker"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # surface 302s instead of following them
        return None


def client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)


def call(opener, method, path, form=None, js=None):
    data, headers = None, {}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
    if js is not None:
        data, headers = json.dumps(js).encode(), {"Content-Type": "application/json"}
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        resp = opener.open(req, timeout=15)
    except urllib.error.HTTPError as e:
        resp = e
    return resp.status if hasattr(resp, "status") else resp.code, resp.headers, resp.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-current-env", action="store_true")
    args = ap.parse_args()
    if not (LEGACY / "app.py").exists():
        sys.exit(f"Cannot find {LEGACY / 'app.py'}")
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            sys.exit(f"Port {PORT} is already in use. Stop the other process and retry.")

    tmp = Path(tempfile.mkdtemp(prefix="ledgerops-legacy-"))
    proc = None
    try:
        work = tmp / "app"
        shutil.copytree(LEGACY, work, ignore=shutil.ignore_patterns("instance", "__pycache__"))
        if args.use_current_env:
            py = sys.executable
        else:
            print("Creating temp virtualenv and installing requirements (needs internet)...")
            subprocess.run([sys.executable, "-m", "venv", str(tmp / "venv")], check=True)
            bindir = "Scripts" if sys.platform.startswith("win") else "bin"
            py = str(tmp / "venv" / bindir / ("python.exe" if bindir == "Scripts" else "python"))
            subprocess.run([py, "-m", "pip", "install", "-q", "-r", str(work / "requirements.txt")], check=True)
        env = {**__import__("os").environ, "FLASK_SECRET_KEY": secrets.token_hex(32)}
        code = f"import app; app.app.run(host='127.0.0.1', port={PORT}, debug=False, use_reloader=False)"
        proc = subprocess.Popen([py, "-c", code], cwd=work, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        up = False
        for _ in range(40):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                up = True
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        check("app starts from legacy/expense-tracker/ and serves GET /", up)
        if not up:
            return

        a, b = client(), client()
        email = f"a{secrets.token_hex(4)}@example.com"
        st, _, _ = call(a, "POST", "/signup", form={"name": "A", "email": email, "password": "secret1"})
        check("signup redirects (302)", st == 302, st)
        st, _, body = call(a, "POST", "/api/expenses",
                           js={"description": "smoke", "amount": 12.5, "category": "Other", "date": "2026-11-01"})
        exp = json.loads(body)
        check("add expense returns 201", st == 201, st)
        st, _, body = call(a, "GET", "/api/expenses/summary")
        s = json.loads(body)
        check("summary total equals amount added", s.get("total_spending") == 12.5 and s.get("transaction_count") == 1,
              f"total={s.get('total_spending')} count={s.get('transaction_count')}")
        st, hdr, body = call(a, "GET", "/api/expenses/export/excel")
        check("Excel export returns a real .xlsx (200, zip header)", st == 200 and body[:2] == b"PK", st)
        call(b, "POST", "/signup", form={"name": "B", "email": f"b{secrets.token_hex(4)}@example.com", "password": "secret1"})
        st, _, body = call(b, "DELETE", f"/api/expenses/{exp['expense']['id']}")
        check("another user cannot delete this expense", json.loads(body).get("deleted") is False)
        st, _, _ = call(a, "GET", "/logout")
        check("logout redirects (302)", st == 302, st)
        st, _, _ = call(a, "GET", "/api/expenses")
        check("API requires login after logout (302)", st == 302, st)
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nRESULT:", "ALL CHECKS PASSED" if all(results) else "FAILED")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
