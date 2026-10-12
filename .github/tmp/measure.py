import os, shutil, subprocess, sys, time

exe = ".exe" if sys.platform.startswith("win") else ""


def mb(path):
    return round(os.path.getsize(path) / 1048576, 1)


def timed(cmd):
    start = time.time()
    r = subprocess.run(cmd, capture_output=True)
    out = f"rc={r.returncode} {time.time() - start:.2f}s"
    if r.returncode:
        out += " :: " + (r.stderr or r.stdout).decode(errors="replace").strip().splitlines()[-1][:300]
    return out


print("### " + sys.platform)
print("base onefile", mb(f"out/base/base{exe}"), "MB")
print("slim onefile", mb(f"out/slim/slim{exe}"), "MB")
d = "out/dir/dir"
total = sum(os.path.getsize(os.path.join(a, f)) for a, _, fs in os.walk(d) for f in fs)
print("onedir total", round(total / 1048576, 1), "MB")
shutil.make_archive("out/dir", "zip", d)
print("onedir zip", mb("out/dir.zip"), "MB")
for label, cmd in (("base", f"out/base/base{exe}"), ("slim", f"out/slim/slim{exe}"), ("onedir", f"out/dir/dir/dir{exe}")):
    for i in (1, 2, 3):
        print(f"{label} selftest run {i}:", timed([cmd, "--selftest"]))
