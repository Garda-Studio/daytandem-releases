"""Disposable hosted Windows only. Tests installed packages, never source or personal data."""
import json, os, pathlib, subprocess, sys, time, sqlite3
if os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted" or sys.platform != "win32":
    raise RuntimeError("Disposable hosted Windows runner required")
scope = sys.argv[1]
assert scope in ("currentuser", "allusers")
product = "DayTandem" if os.environ["GITHUB_REPOSITORY"].endswith("/daytandem-releases") else "Commandless"
root = pathlib.Path(os.environ["RUNNER_TEMP"]).resolve() / ("garda-acceptance-" + scope)
root.mkdir(exist_ok=False)
destination = root / product
data = pathlib.Path(os.environ["APPDATA"]) / "app.daytandem.desktop" if product == "DayTandem" else root / "data"
env = dict(os.environ)
env.update(COMMANDLESS_DATA_DIR=str(data), SERVER_AGENT_STUDIO_DATA_DIR=str(data), SERVER_AGENT_STUDIO_SMOKE_TEST="1")
def run(args, **kw):
    result = subprocess.run([str(a) for a in args], env=env, timeout=180, capture_output=True, text=True, **kw)
    print(result.stdout[-6000:])
    if result.returncode:
        print(result.stderr[-6000:])
        raise RuntimeError(f"Process failed: {pathlib.Path(str(args[0])).name}: {result.returncode}")
    return result.stdout
def launch(exe):
    if product == "Commandless":
        run([exe])
        return
    p = subprocess.Popen([str(exe)], env=env)
    try:
        for _ in range(40):
            if p.poll() is not None: raise RuntimeError("DayTandem exited at startup")
            if (data / "planner.sqlite3").exists(): break
            time.sleep(.5)
        assert (data / "planner.sqlite3").exists(), "App did not open its database"
        time.sleep(5)
        run(["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {p.pid}).CloseMainWindow()"])
        try: p.wait(timeout=15)
        except subprocess.TimeoutExpired: p.terminate(); p.wait(timeout=10)
    finally:
        if p.poll() is None: p.terminate(); p.wait(timeout=10)
def seed():
    if product == "DayTandem":
        with sqlite3.connect(data / "planner.sqlite3") as db:
            doc = dict(schemaVersion=1, settings=dict(language="en", theme="dark", style="classic", alwaysOnTop=False, closeToTray=False, autoStart=False, checkUpdates=False, calendarIds=[]), blocks=[dict(id="preserve-installed", title="Keep across installed upgrade", day=1, start="10:00", end="11:00", color="#123456")], lists=[])
            db.execute("INSERT OR REPLACE INTO documents(id,payload) VALUES(1,?)", [json.dumps(doc)])
    else:
        file = data / "config.json"
        doc = json.loads(file.read_text(encoding="utf-8"))
        doc["servers"].append(dict(id="preserve-installed", name="Keep across installed upgrade", host="127.0.0.1", port=22, username="ci", authType="agent", environment="development", tags=[], allowedRoots=["/tmp"], connectTimeoutMs=1000, commandTimeoutMs=1000))
        file.write_text(json.dumps(doc), encoding="utf-8")
def retained():
    if product == "DayTandem":
        with sqlite3.connect(data / "planner.sqlite3") as db:
            doc = json.loads(db.execute("SELECT payload FROM documents WHERE id=1").fetchone()[0])
        assert any(x["id"] == "preserve-installed" for x in doc["blocks"])
        assert doc["settings"]["theme"] == "dark"
    else:
        doc = json.loads((data / "config.json").read_text(encoding="utf-8"))
        assert any(x["id"] == "preserve-installed" for x in doc["servers"])
exe = destination / (product + ".exe")
versions = []
for phase in ("baseline", "candidate"):
    package = pathlib.Path("packages", phase + "-setup.exe").resolve()
    assert package.is_file()
    run([package, "/S", "/" + scope, "/D=" + str(destination)])
    assert exe.is_file(), "Missing installed executable"
    version = run(["powershell", "-NoProfile", "-Command", f"(Get-Item -LiteralPath '{exe}').VersionInfo.ProductVersion"]).strip()
    versions.append(version)
    launch(exe)
    if phase == "baseline": seed()
    retained()
    print(json.dumps(dict(product=product, phase=phase, scope=scope, version=version, retained=True)))
assert versions[0] != versions[1], "Versions did not change"
uninstaller = destination / ("uninstall.exe" if product == "DayTandem" else "Uninstall Commandless.exe")
run([uninstaller, "/S", "/" + scope, "_?=" + str(destination)])
for _ in range(40):
    if not exe.exists(): break
    time.sleep(.5)
assert not exe.exists(), "Uninstall left executable"
retained()
print(json.dumps(dict(passed=True, product=product, scope=scope, versions=versions, dataRetainedAfterUninstall=True)))
