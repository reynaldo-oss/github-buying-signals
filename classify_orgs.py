#!/usr/bin/env python3
"""
Phase 3: repo list -> buying list.

A GitHub org is not a company. Foundations, research labs, and community projects
all own repos and none of them have a software budget. This pass pulls org metadata
plus top-contributor employer affiliations and splits the list into COMMERCIAL,
COMMUNITY, and UNKNOWN so outreach targets orgs that can actually buy.
"""
import json, subprocess, time, csv, os, re, collections

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)

def gh(path):
    for a in range(3):
        p = subprocess.run(["gh","api","-H","Accept: application/vnd.github+json",path],
                           capture_output=True, text=True)
        if p.returncode == 0:
            try: return json.loads(p.stdout)
            except json.JSONDecodeError: return None
        e = p.stderr.lower()
        if "rate limit" in e or "secondary" in e:
            time.sleep(20*(a+1)); continue
        return None
    return None

COMMUNITY_PAT = re.compile(
    r"\b(foundation|non-?profit|nonprofit|community|open[- ]?source collective|"
    r"working group|consortium|university|universit|institute|research group|"
    r"laborator|\bcnrs\b|\bgsoc\b|students?|academy|school)\b", re.I)
COMMERCIAL_PAT = re.compile(
    r"\b(inc\.?|llc|ltd\.?|gmbh|s\.?a\.?s\.?|b\.?v\.?|corp\.?|company|"
    r"startup|platform|we build|our product|saas|enterprise)\b", re.I)
KNOWN_FOUNDATIONS = {
    "apache","cncf","python","pytorch","numfocus","rust-lang","openjs","nodejs",
    "linuxfoundation","eclipse","mozilla","gnome","kde","openssl","django",
    "jupyter","scipy","pandas-dev","osgeo","openstack","w3c","oasis-open",
    "django-commons","pallets","scikit-learn","matplotlib",
}

rows = list(csv.DictReader(open(os.path.join(OUT,"codspeed_targets.csv"))))
orgs = sorted({r["owner"] for r in rows if r["owner_type"]=="org"})
print(f"classifying {len(orgs)} orgs", flush=True)

info = {}
for i, o in enumerate(orgs, 1):
    if i % 50 == 0: print(f"  {i}/{len(orgs)}", flush=True)
    d = gh(f"/orgs/{o}")
    if not d:
        info[o] = {"org_name":"","website":"","location":"","desc":"",
                   "members":"", "classification":"unknown","why":"lookup failed"}
        continue
    name = d.get("name") or ""
    blog = (d.get("blog") or "").strip()
    desc = d.get("description") or ""
    loc  = d.get("location") or ""
    blob = " ".join([o, name, desc])

    # employer affiliations from top contributors of that org's listed repo
    employers = []
    repo = next((r["repo"] for r in rows if r["owner"]==o), None)
    if repo:
        cons = gh(f"/repos/{repo}/contributors?per_page=5")
        if isinstance(cons, list):
            for c in cons[:3]:
                u = gh(f"/users/{c.get('login','')}")
                if u and u.get("company"):
                    employers.append(u["company"].strip().lstrip("@"))
    emp_s = "; ".join(dict.fromkeys(employers))[:90]

    cls, why = "unknown", ""
    if o.lower() in KNOWN_FOUNDATIONS:
        cls, why = "community", "known foundation"
    elif COMMUNITY_PAT.search(blob):
        cls, why = "community", "community/academic language"
    elif COMMERCIAL_PAT.search(blob):
        cls, why = "commercial", "commercial language"
    elif blog and not re.search(r"(github\.io|readthedocs|gitlab\.io)", blog):
        cls, why = "commercial", "own domain"
    elif employers:
        cls, why = "commercial", f"contributors employed ({emp_s[:40]})"

    info[o] = {"org_name":name,"website":blog,"location":loc,"desc":desc[:110],
               "members":emp_s,"classification":cls,"why":why}

for r in rows:
    m = info.get(r["owner"], {}) if r["owner_type"]=="org" else {}
    r["org_name"]       = m.get("org_name","")
    r["website"]        = m.get("website","")
    r["org_location"]   = m.get("location","")
    r["org_desc"]       = m.get("desc","")
    r["contributor_employers"] = m.get("members","")
    r["classification"] = m.get("classification","personal" if r["owner_type"]=="user" else "unknown")
    r["classify_reason"]= m.get("why","personal account")

cols = ["repo","owner","org_name","classification","classify_reason","owner_type","language",
        "stars","signals","bench_in_ci","last_push","website","org_location",
        "contributor_employers","org_desc","url","score"]
p = os.path.join(OUT,"codspeed_buying_list.csv")
with open(p,"w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
    for r in sorted(rows,key=lambda r:-float(r["score"])): w.writerow({k:r.get(k,"") for k in cols})

c = collections.Counter(r["classification"] for r in rows)
print("\n" + str(dict(c)))
comm = [r for r in rows if r["classification"]=="commercial"]
ci   = [r for r in comm if r["bench_in_ci"]=="yes"]
print(f"commercial: {len(comm)}  | commercial + bench-in-CI: {len(ci)}")
print(p)
