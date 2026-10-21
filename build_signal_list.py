#!/usr/bin/env python3
"""
CodSpeed prospect signal engine.

Thesis: a repo that already runs benchmarks cares about performance. A repo that
runs them WITHOUT regression gating in CI has the pain CodSpeed sells into but no
solution. Those are the qualified targets. Repos already on CodSpeed are excluded
as customers and kept separately as expansion/champion signal.
"""
import json, subprocess, time, csv, sys, math, datetime, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)

def gh(path, paginate=False):
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    if paginate:
        cmd.append("--paginate")
    for attempt in range(4):
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0:
            try:
                return json.loads(p.stdout)
            except json.JSONDecodeError:
                return None
        err = p.stderr.lower()
        if "rate limit" in err or "secondary" in err or "403" in err:
            wait = 25 * (attempt + 1)
            print(f"    rate limited, sleeping {wait}s", flush=True)
            time.sleep(wait)
            continue
        return None
    return None

def code_search(q, pages=1):
    """Returns set of 'owner/repo'. Code search is capped at 10 req/min."""
    repos = set()
    for page in range(1, pages + 1):
        url = f"/search/code?q={q}&per_page=100&page={page}"
        data = gh(url)
        if not data or "items" not in data:
            break
        for it in data["items"]:
            repos.add(it["repository"]["full_name"])
        if len(data["items"]) < 100:
            break
        time.sleep(7)
    time.sleep(7)   # stay under 10/min
    return repos

# ---------------------------------------------------------------- signal queries
CUSTOMER_Q = [
    ("CodSpeedHQ%2Faction+path%3A.github%2Fworkflows", 2),
    ("codspeed+path%3A.github%2Fworkflows", 2),
]

# Benchmark tooling present = cares about performance
TARGET_Q = [
    ("criterion+path%3ACargo.toml",                      2, "rust",   "criterion"),
    ("divan+path%3ACargo.toml",                          1, "rust",   "divan"),
    ("pytest-benchmark+path%3Apyproject.toml",           2, "python", "pytest-benchmark"),
    ("tinybench+path%3Apackage.json",                    1, "node",   "tinybench"),
    ("mitata+path%3Apackage.json",                       1, "node",   "mitata"),
    ("cargo+bench+path%3A.github%2Fworkflows",           2, "rust",   "bench-in-ci"),
    ("pytest-benchmark+path%3A.github%2Fworkflows",      1, "python", "bench-in-ci"),
]

print("== phase 1: existing CodSpeed users (exclusion + champion signal)", flush=True)
customers = set()
for q, pages in CUSTOMER_Q:
    found = code_search(q, pages)
    print(f"  {q[:45]:45} -> {len(found)}", flush=True)
    customers |= found
print(f"  total existing users: {len(customers)}", flush=True)

print("== phase 2: benchmark signal (candidate targets)", flush=True)
signals = {}   # repo -> set of signals
for q, pages, lang, sig in TARGET_Q:
    found = code_search(q, pages)
    print(f"  {sig:16} {lang:7} -> {len(found)}", flush=True)
    for r in found:
        signals.setdefault(r, set()).add(sig)

candidates = {r: s for r, s in signals.items() if r not in customers}
print(f"  candidates after removing existing users: {len(candidates)}", flush=True)

print("== phase 3: enrich + score", flush=True)
CUTOFF = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=180))
rows = []
for i, (full, sigs) in enumerate(sorted(candidates.items()), 1):
    if i % 25 == 0:
        print(f"    enriched {i}/{len(candidates)}", flush=True)
    repo = gh(f"/repos/{full}")
    if not repo or repo.get("archived") or repo.get("fork"):
        continue
    lang = (repo.get("language") or "").lower()
    if lang not in ("rust", "python", "javascript", "typescript", "go", "c++", "c"):
        continue
    pushed = repo.get("pushed_at")
    if pushed:
        try:
            if datetime.datetime.fromisoformat(pushed.replace("Z", "+00:00")) < CUTOFF:
                continue
        except Exception:
            pass
    owner = repo.get("owner", {}) or {}
    is_org = owner.get("type") == "Organization"
    stars = repo.get("stars", repo.get("stargazers_count", 0)) or 0

    score  = 0.0
    score += 30 if is_org else 0                       # company-owned beats personal
    score += min(25, math.log10(max(stars, 1)) * 9)    # reach, log-scaled
    score += 20 if "bench-in-ci" in sigs else 0        # already automating = highest intent
    score += 8 * (len(sigs) - 1)                       # multiple benchmark tools
    score += 10 if lang in ("rust", "python") else 5   # CodSpeed's strongest ecosystems

    rows.append({
        "repo": full,
        "owner": owner.get("login", ""),
        "owner_type": "org" if is_org else "user",
        "language": repo.get("language") or "",
        "stars": stars,
        "signals": "|".join(sorted(sigs)),
        "bench_in_ci": "yes" if "bench-in-ci" in sigs else "no",
        "last_push": (pushed or "")[:10],
        "url": repo.get("html_url", ""),
        "score": round(score, 1),
    })

rows.sort(key=lambda r: -r["score"])
path = os.path.join(OUT, "codspeed_targets.csv")
with open(path, "w", newline="", encoding="utf-8") as f:
    wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["repo"])
    wr.writeheader()
    wr.writerows(rows)

cust_path = os.path.join(OUT, "codspeed_existing_users.csv")
with open(cust_path, "w", newline="", encoding="utf-8") as f:
    wr = csv.writer(f); wr.writerow(["repo"])
    for r in sorted(customers): wr.writerow([r])

orgs = len([r for r in rows if r["owner_type"] == "org"])
ci   = len([r for r in rows if r["bench_in_ci"] == "yes"])
print(f"\nDONE  targets={len(rows)}  org-owned={orgs}  bench-in-CI={ci}  existing-users={len(customers)}")
print(f"  {path}")
print(f"  {cust_path}")
