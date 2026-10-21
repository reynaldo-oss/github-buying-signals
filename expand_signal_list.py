#!/usr/bin/env python3
"""Phase 2: re-run the manifest queries with working `filename:` syntax and merge."""
import json, subprocess, time, csv, math, datetime, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)

def gh(path):
    for attempt in range(4):
        p = subprocess.run(["gh","api","-H","Accept: application/vnd.github+json",path],
                           capture_output=True, text=True)
        if p.returncode == 0:
            try: return json.loads(p.stdout)
            except json.JSONDecodeError: return None
        e = p.stderr.lower()
        if "rate limit" in e or "secondary" in e or "403" in e:
            w = 25*(attempt+1); print(f"    rate limited {w}s", flush=True); time.sleep(w); continue
        return None
    return None

def search(q, pages=2):
    repos=set()
    for page in range(1, pages+1):
        d = gh(f"/search/code?q={q}&per_page=100&page={page}")
        if not d or "items" not in d: break
        for it in d["items"]: repos.add(it["repository"]["full_name"])
        if len(d["items"]) < 100: break
        time.sleep(7)
    time.sleep(7)
    return repos

QUERIES = [
    ("criterion+filename%3ACargo.toml",            3, "criterion"),
    ("divan+filename%3ACargo.toml",                2, "divan"),
    ("pytest-benchmark+filename%3Apyproject.toml", 3, "pytest-benchmark"),
    ("tinybench+filename%3Apackage.json",          2, "tinybench"),
    ("mitata+filename%3Apackage.json",             2, "mitata"),
    ("benchmark.js+filename%3Apackage.json",       2, "benchmark.js"),
]

customers = set()
with open(os.path.join(OUT,"codspeed_existing_users.csv")) as f:
    for r in csv.DictReader(f): customers.add(r["repo"])

existing = {}
with open(os.path.join(OUT,"codspeed_targets.csv")) as f:
    for r in csv.DictReader(f): existing[r["repo"]] = r
print(f"loaded {len(existing)} existing targets, {len(customers)} customers", flush=True)

print("== searching manifests", flush=True)
new_sigs = {}
for q, pages, sig in QUERIES:
    found = search(q, pages)
    print(f"  {sig:18} -> {len(found)}", flush=True)
    for r in found:
        if r not in customers:
            new_sigs.setdefault(r, set()).add(sig)

# carry over signals already known
for repo, row in existing.items():
    new_sigs.setdefault(repo, set()).update(row["signals"].split("|"))

to_enrich = [r for r in new_sigs if r not in existing]
print(f"== enriching {len(to_enrich)} new repos", flush=True)

CUT = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=180)
enriched = {}
for i, full in enumerate(to_enrich, 1):
    if i % 100 == 0: print(f"    {i}/{len(to_enrich)}", flush=True)
    repo = gh(f"/repos/{full}")
    if not repo or repo.get("archived") or repo.get("fork"): continue
    lang=(repo.get("language") or "").lower()
    if lang not in ("rust","python","javascript","typescript","go","c++","c"): continue
    pushed=repo.get("pushed_at")
    if pushed:
        try:
            if datetime.datetime.fromisoformat(pushed.replace("Z","+00:00")) < CUT: continue
        except Exception: pass
    o=repo.get("owner",{}) or {}
    enriched[full]={"owner":o.get("login",""),"owner_type":"org" if o.get("type")=="Organization" else "user",
        "language":repo.get("language") or "","stars":repo.get("stargazers_count",0) or 0,
        "last_push":(pushed or "")[:10],"url":repo.get("html_url","")}

rows=[]
for repo, sigs in new_sigs.items():
    if repo in existing:
        r=existing[repo]
        meta={"owner":r["owner"],"owner_type":r["owner_type"],"language":r["language"],
              "stars":int(r["stars"]),"last_push":r["last_push"],"url":r["url"]}
    elif repo in enriched:
        meta=enriched[repo]
    else:
        continue
    sigs=set(s for s in sigs if s)
    ci = "bench-in-ci" in sigs
    tooling = sigs - {"bench-in-ci"}
    lang=meta["language"].lower()
    score  = 30 if meta["owner_type"]=="org" else 0
    score += min(25, math.log10(max(meta["stars"],1))*9)
    score += 20 if ci else 0
    score += 8*max(0,len(tooling)-1)
    score += 10 if lang in ("rust","python") else 5
    rows.append({**meta,"repo":repo,"signals":"|".join(sorted(sigs)),
                 "bench_in_ci":"yes" if ci else "no","score":round(score,1)})

rows.sort(key=lambda r:-r["score"])
cols=["repo","owner","owner_type","language","stars","signals","bench_in_ci","last_push","url","score"]
p=os.path.join(OUT,"codspeed_targets.csv")
with open(p,"w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
    for r in rows: w.writerow({k:r[k] for k in cols})

print(f"\nDONE total={len(rows)} org={sum(1 for r in rows if r['owner_type']=='org')} "
      f"ci={sum(1 for r in rows if r['bench_in_ci']=='yes')}")
print(p)
