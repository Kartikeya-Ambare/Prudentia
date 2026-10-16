#!/usr/bin/env python3
"""Prudentia launcher: one command that sets everything up and starts the app.

    python run.py            (Windows: py run.py)

First run: checks your tools, creates a virtual environment per Python service, installs dependencies, installs the
frontend packages, makes sure Ollama has the chat models, then starts the backend, chat service and frontend and opens
the app. Later runs skip whatever is already done. Press Ctrl+C to stop everything.

Options:
  --no-browser    do not open the browser
  --setup-only    install everything, then exit without starting
  --skip-ollama   do not touch Ollama (chat will be unavailable)
  --skip-models   start Ollama if needed but do not download models
  --test          run the backend tests, the chat service tests and the frontend build, then exit
  --smoke         start everything, run quick checks, stop, and exit 0 if all passed (used by CI)

Only the Python standard library is used, so this works on Windows, macOS and Linux.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND, CHAT, FRONT = ROOT / "backend", ROOT / "chat-service", ROOT / "frontend"
LOGS = ROOT / "logs"
OLLAMA_URL = "http://127.0.0.1:11434"
MODELS = ["qwen2.5:1.5b-instruct", "llama3.2:1b"]      # the first one is the one chat cannot work without
DEFAULT_PORTS = {"backend": 8000, "chat": 8001, "frontend": 5173}
IS_WIN = os.name == "nt"
STAMP = ".prudentia-installed"

children: list[tuple[str, subprocess.Popen]] = []
started_ollama: subprocess.Popen | None = None
stop_event = threading.Event()


# ----------------------------------------------------------------------------- output
def say(msg: str = "") -> None:
    print(msg, flush=True)


def step(msg: str) -> None:
    say(f"\n==> {msg}")


def ok(msg: str) -> None:
    say(f"    [ok] {msg}")


def warn(msg: str) -> None:
    say(f"    [!]  {msg}")


_last_tail = ""


def ci_error(text: str) -> None:
    """On GitHub Actions, also publish the failure as an annotation so it is visible without opening the raw logs."""
    if os.environ.get("GITHUB_ACTIONS"):
        text = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::error::{text[:3500]}", flush=True)


def die(problem: str, fix: str = "") -> "None":
    say(f"\n[error] {problem}")
    if fix:
        say(f"        {fix}")
    ci_error(f"{problem} {fix}\n--- end of log ---\n{_last_tail[-2500:]}")
    shutdown()
    sys.exit(1)


def tail(path: Path, n: int = 25) -> str:
    global _last_tail
    try:
        text = "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        text = "(no log)"
    _last_tail = text
    return text


# ----------------------------------------------------------------------------- checks
def version_of(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def check_python() -> None:
    v = sys.version_info
    if v < (3, 11):
        die(f"Python {v.major}.{v.minor} is too old. Prudentia needs Python 3.11 or newer.",
            "Install it from https://www.python.org/downloads/ and run this again.")
    if v >= (3, 15):
        warn(f"Python {v.major}.{v.minor} is newer than the versions this was tested with (3.11 to 3.14).")
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


def node_ok(ver: str) -> bool:
    try:
        major, minor, *_ = (int(p) for p in ver.lstrip("v").split("."))
    except ValueError:
        return False
    return (major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major >= 23


def check_node() -> str:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        die("Node.js was not found.", "Install Node.js 22 LTS from https://nodejs.org/ (it includes npm), then open a NEW terminal and run this again.")
    ver = version_of([node, "--version"]) or ""
    if not node_ok(ver):
        die(f"Node.js {ver or '(unknown version)'} is too old. The frontend needs Node 20.19+ or 22.12+.",
            "Install Node.js 22 LTS from https://nodejs.org/ and run this again.")
    ok(f"Node {ver}")
    return npm


# ----------------------------------------------------------------------------- processes
def python_in(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if IS_WIN else "bin/python")


def spawn(name: str, cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    LOGS.mkdir(exist_ok=True)
    log = open(LOGS / f"{name}.log", "w", encoding="utf-8", errors="replace")
    kwargs: dict = {"cwd": str(cwd), "env": env, "stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    children.append((name, proc))
    return proc


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def shutdown() -> None:
    for _, proc in reversed(children):
        kill_tree(proc)
    children.clear()
    global started_ollama
    if started_ollama is not None:
        kill_tree(started_ollama)
        started_ollama = None


def run_logged(label: str, cmd: list[str], cwd: Path, logname: str, env: dict | None = None) -> None:
    """Runs a long install, keeps the output in logs/, prints a sign of life every 15 s, shows the tail on failure."""
    LOGS.mkdir(exist_ok=True)
    path = LOGS / logname
    with open(path, "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env)
        waited = 0
        while True:
            try:
                code = proc.wait(timeout=15)
                break
            except subprocess.TimeoutExpired:
                waited += 15
                say(f"    ... {label} ({waited // 60}m {waited % 60:02d}s)")
    if code != 0:
        say(tail(path, 30))
        die(f"{label} failed (exit code {code}). The full output is in {path}.",
            "Check your internet connection and free disk space, then run this again; it resumes where it stopped.")


# ----------------------------------------------------------------------------- setup steps
def file_hash(*paths: Path, extra: str = "") -> str:
    h = hashlib.sha256(extra.encode())
    for p in paths:
        h.update(p.read_bytes())
    return h.hexdigest()


def setup_python_service(name: str, folder: Path, torch_cpu: bool = False) -> Path:
    venv = folder / ".venv"
    py = python_in(venv)
    req = folder / "requirements.txt"
    want = file_hash(req, extra=f"{sys.version_info.major}.{sys.version_info.minor}|{platform.system()}")
    stamp = venv / STAMP
    if py.exists() and stamp.exists() and stamp.read_text().strip() == want:
        ok(f"{name}: dependencies already installed")
        return py
    step(f"Setting up {name} (first time takes a few minutes)")
    if venv.exists() and not py.exists():
        shutil.rmtree(venv, ignore_errors=True)            # a half-made environment from an earlier attempt
    if not py.exists():
        res = subprocess.run([sys.executable, "-m", "venv", str(venv)], capture_output=True, text=True)
        if res.returncode != 0:
            hint = "On Debian/Ubuntu run:  sudo apt install python3-venv   then run this again." if platform.system() == "Linux" \
                else "Reinstall Python from https://www.python.org/downloads/ (make sure the standard library and pip are included)."
            die(f"Could not create a virtual environment for {name}.\n        {res.stderr.strip()[-300:]}", hint)
    pip = [str(py), "-m", "pip", "install", "--disable-pip-version-check"]
    if torch_cpu and platform.system() == "Linux":
        # On Linux the default PyTorch wheel bundles CUDA libraries (several GB). The CPU build is all this app needs.
        res = subprocess.run(pip + ["torch", "--index-url", "https://download.pytorch.org/whl/cpu"], capture_output=True, text=True)
        say("    PyTorch (CPU build): " + ("installed" if res.returncode == 0 else "CPU wheel unavailable, using the default one"))
    run_logged(f"installing {name} packages", pip + ["-r", str(req)], folder, f"install-{name}.log")
    stamp.write_text(want)
    ok(f"{name}: dependencies installed")
    return py


def setup_frontend(npm: str) -> None:
    modules = FRONT / "node_modules"
    lock = FRONT / "package-lock.json"
    want = file_hash(lock, FRONT / "package.json")
    stamp = modules / STAMP
    if modules.exists() and stamp.exists() and stamp.read_text().strip() == want:
        ok("frontend: packages already installed")
        return
    step("Setting up the frontend")
    if modules.exists():
        shutil.rmtree(modules, ignore_errors=True)
    run_logged("installing frontend packages", [npm, "ci", "--no-audit", "--no-fund"], FRONT, "install-frontend.log")
    stamp.write_text(want)
    ok("frontend: packages installed")


def run_tests(bpy: Path, cpy: Path, npm: str) -> bool:
    results: list[tuple[str, bool]] = []
    for name, py, cwd in (("backend tests", bpy, BACKEND), ("chat service tests", cpy, CHAT)):
        step(f"Running the {name}")
        results.append((name, subprocess.run([str(py), "-m", "pytest", "-q"], cwd=str(cwd)).returncode == 0))
    step("Building the frontend (type-check + production build)")
    results.append(("frontend build", subprocess.run([npm, "run", "build"], cwd=str(FRONT)).returncode == 0))
    step("Summary")
    for name, good in results:
        say(f"    [{'ok' if good else 'FAIL'}] {name}")
    return all(good for _, good in results)


def http_json(url: str, body: dict | None = None, timeout: float = 5.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "null")


def ollama_up() -> bool:
    try:
        http_json(f"{OLLAMA_URL}/api/tags", timeout=2)
        return True
    except (OSError, ValueError):
        return False


def find_ollama() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    candidates = []
    if IS_WIN:
        candidates.append(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe")
    elif platform.system() == "Darwin":
        candidates.append(Path("/Applications/Ollama.app/Contents/Resources/ollama"))
    return next((str(c) for c in candidates if c.exists()), None)


def setup_ollama(skip_models: bool) -> bool:
    """Returns True when Ollama is reachable. Never fatal: Expert mode works without it, chat just says it is unavailable."""
    global started_ollama
    step("Checking Ollama (the local AI model server)")
    if not ollama_up():
        binary = find_ollama()
        if not binary:
            warn("Ollama is not installed. Chat will be unavailable until you install it from https://ollama.com/download")
            warn("and run this again. Everything else works.")
            return False
        say("    Ollama is installed but not running; starting it...")
        LOGS.mkdir(exist_ok=True)
        kwargs: dict = {"stdout": open(LOGS / "ollama.log", "w"), "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
        if IS_WIN:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        try:
            started_ollama = subprocess.Popen([binary, "serve"], **kwargs)
        except OSError as exc:
            warn(f"Could not start Ollama ({exc}). Start it yourself (open the Ollama app, or run: ollama serve).")
            return False
        for _ in range(40):
            if ollama_up():
                break
            time.sleep(1)
        else:
            warn("Ollama did not respond within 40 seconds. Chat will be unavailable. See logs/ollama.log")
            return False
    ok("Ollama is running")
    if skip_models:
        return True
    have = {m["name"] for m in http_json(f"{OLLAMA_URL}/api/tags", timeout=10).get("models", [])}
    for i, model in enumerate(MODELS):
        if model in have:
            ok(f"model {model} is installed")
            continue
        say(f"    Downloading model {model} (one time, about {'1 GB' if i == 0 else '1.3 GB'})...")
        try:
            last = -10
            req = urllib.request.Request(f"{OLLAMA_URL}/api/pull", data=json.dumps({"model": model, "stream": True}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3600) as resp:
                for line in resp:
                    msg = json.loads(line.decode("utf-8"))
                    if msg.get("error"):
                        raise RuntimeError(msg["error"])
                    if msg.get("total") and msg.get("completed") is not None:
                        pct = int(100 * msg["completed"] / msg["total"])
                        if pct >= last + 10:
                            say(f"        {pct}%")
                            last = pct
            ok(f"model {model} downloaded")
        except (OSError, RuntimeError, ValueError) as exc:
            warn(f"Could not download {model}: {exc}")
            warn(f"Run this yourself, then start again:  ollama pull {model}")
    return True


# ----------------------------------------------------------------------------- start
def port_free(port: int) -> bool:
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                if s.connect_ex((host, port)) == 0:
                    return False
        except OSError:
            pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
    except OSError:
        return False
    return True


def pick_ports() -> dict[str, int]:
    chosen: dict[str, int] = {}
    used: set[int] = set()
    for name, start in DEFAULT_PORTS.items():
        port = start
        while port in used or not port_free(port):
            port += 1
            if port > start + 100:
                die(f"No free port found near {start} for the {name}.", "Close some programs and try again.")
        if port != start:
            warn(f"port {start} is busy, using {port} for the {name}")
        chosen[name] = port
        used.add(port)
    return chosen


def wait_ready(name: str, url: str, proc: subprocess.Popen, seconds: int) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            say(tail(LOGS / f"{name}.log"))
            die(f"The {name} stopped while starting (exit code {proc.returncode}). Its log is {LOGS / (name + '.log')}.",
                "Fix the error above, or send it to the maintainers, and run this again.")
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status < 500:
                    return
        except (OSError, ValueError):
            pass
        if stop_event.wait(1.5):
            die("Stopped.")
    say(tail(LOGS / f"{name}.log"))
    die(f"The {name} did not become ready within {seconds} seconds.", f"Look at {LOGS / (name + '.log')} for the reason.")


def start_services(bpy: Path, cpy: Path, npm: str, ports: dict[str, int]) -> None:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    api = f"http://127.0.0.1:{ports['backend']}"
    chat = f"http://127.0.0.1:{ports['chat']}"
    step("Starting the services")
    bp = spawn("backend", [str(bpy), "-m", "uvicorn", "backend.api.main:app", "--host", "127.0.0.1", "--port", str(ports["backend"])],
               BACKEND, env)
    wait_ready("backend", f"{api}/health", bp, 180)
    ok(f"backend ready on {api}")
    cp = spawn("chat-service", [str(cpy), "-m", "uvicorn", "chat_service.main:app", "--host", "127.0.0.1", "--port", str(ports["chat"])],
               CHAT, dict(env, CHAT_ENGINE_MODE="http", CHAT_ENGINE_URL=api))
    wait_ready("chat-service", f"{chat}/api/chat/health", cp, 120)
    ok(f"chat service ready on {chat}")
    fp = spawn("frontend", [npm, "run", "dev", "--", "--port", str(ports["frontend"]), "--strictPort"], FRONT,
               dict(env, VITE_API_URL=api, VITE_CHAT_URL=chat, BROWSER="none"))
    wait_ready("frontend", f"http://localhost:{ports['frontend']}/", fp, 120)
    ok(f"frontend ready on http://localhost:{ports['frontend']}")


def smoke(ports: dict[str, int], ollama: bool) -> bool:
    step("Smoke checks")
    api = f"http://127.0.0.1:{ports['backend']}"
    results: list[tuple[str, bool, str]] = []

    def check(name: str, fn) -> None:
        try:
            detail = fn()
            results.append((name, True, detail or ""))
        except Exception as exc:  # noqa: BLE001
            results.append((name, False, str(exc)[:200]))

    def health() -> str:
        assert http_json(f"{api}/health")["status"] == "ok", "bad health response"
        return ""
    check("backend health", health)

    def plan() -> str:
        d = http_json(f"{api}/plan", {"capital": 500000, "horizon_years": 5, "risk_thermometer": 50}, timeout=180)
        split = d["split_pct"]
        assert abs(sum(split.values()) - 100) < 0.5, f"split does not add to 100: {split}"
        assert d["bucket_projections"] and d["weights"], "empty plan"
        return f"split {split}"
    check("plan from the engine", plan)

    def sector() -> str:
        d = http_json(f"{api}/mutual-funds/{urllib.parse.quote('HDFC Large Cap Fund')}/sector-allocation")
        assert d["sector_json"], "no sectors"
        return f"{len(d['sector_json'])} sectors"
    check("fund sector table", sector)
    def page() -> str:
        with urllib.request.urlopen(f"http://localhost:{ports['frontend']}/", timeout=10) as r:
            assert r.status == 200, f"HTTP {r.status}"
        return ""
    check("frontend page", page)

    if ollama:
        def chat() -> str:
            d = http_json(f"http://127.0.0.1:{ports['chat']}/api/chat",
                          {"session_id": "smoke", "message": "I want to invest Rs. 5 lakh for 5 years with 50% risk"}, timeout=180)
            assert d.get("result"), f"no plan came back: {d.get('reply')}"
            return d["reply"][:70]
        check("chat builds a plan", chat)
    else:
        results.append(("chat builds a plan", True, "skipped (no Ollama)"))

    allgood = True
    for name, good, detail in results:
        say(f"    [{'ok' if good else 'FAIL'}] {name} {('- ' + detail) if detail else ''}")
        if not good:
            ci_error(f"smoke check failed: {name}: {detail}")
        allgood &= good
    return allgood


# ----------------------------------------------------------------------------- main
def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Set up and start Prudentia.")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--setup-only", action="store_true")
    ap.add_argument("--skip-ollama", action="store_true")
    ap.add_argument("--skip-models", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    def on_signal(*_):
        stop_event.set()
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    if IS_WIN:
        signal.signal(signal.SIGBREAK, on_signal)

    say("Prudentia: setting up and starting. The first run downloads a few GB and can take 5 to 15 minutes.")
    step("Checking your tools")
    check_python()
    npm = check_node()
    for folder in (BACKEND, CHAT, FRONT):
        if not folder.exists():
            die(f"The folder {folder.name}/ is missing.", "Run this from a full clone of the repository (git clone, not a partial download).")
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    if not python_in(BACKEND / ".venv").exists() and free_gb < 6:
        die(f"Only {free_gb:.1f} GB of disk space is free; the first setup needs about 6 GB.", "Free some space and run this again.")

    bpy = setup_python_service("backend", BACKEND, torch_cpu=True)
    cpy = setup_python_service("chat-service", CHAT)
    setup_frontend(npm)
    if args.test:
        sys.exit(0 if run_tests(bpy, cpy, npm) else 1)
    ollama = False if args.skip_ollama else setup_ollama(args.skip_models)
    if args.setup_only:
        say("\nSetup finished. Start the app any time with:  python run.py")
        return

    ports = pick_ports()
    try:
        start_services(bpy, cpy, npm, ports)
        url = f"http://localhost:{ports['frontend']}"
        if args.smoke:
            good = smoke(ports, ollama)
            shutdown()
            sys.exit(0 if good else 1)
        say(f"\n  Prudentia is running.  Open  {url}\n  Press Ctrl+C here to stop everything.\n")
        if not args.no_browser:
            try:
                webbrowser.open(url)
            except Exception:  # noqa: BLE001
                pass
        while not stop_event.wait(1.0):
            for name, proc in children:
                if proc.poll() is not None:
                    say(tail(LOGS / f"{name}.log"))
                    die(f"The {name} stopped unexpectedly (exit code {proc.returncode}).", f"Log: {LOGS / (name + '.log')}")
    finally:
        say("\nStopping...")
        shutdown()
        say("Stopped. See you soon.")


if __name__ == "__main__":
    try:
        main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception:  # noqa: BLE001
        import traceback
        ci_error("unexpected error:\n" + traceback.format_exc())
        raise
