#!/usr/bin/env python3
"""
Phase 4: graded commercial confidence.

The first classifier was binary and leaned on "org has a website", which flags
borgbackup.org and cocotb.org as companies. This replaces the verdict with a
confidence grade, checks known commercial orgs before the community regex (so
Facebook stops being labelled a community project), and treats academic
employers as a community signal rather than a commercial one.

Pure rescoring over the existing CSV. No API calls.
"""
import csv, os, re, collections

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

KNOWN_COMMERCIAL = {
    "facebook","instagram","google","microsoft","amazon","aws","apple","netflix",
    "nvidia","meta","shopify","stripe","cloudflare","vercel","databricks","snowflake",
    "elastic","mongodb","redis","datadog","hashicorp","gitlab","atlassian","twilio",
    "uber","airbnb","lyft","cruise","alibaba","bytedance","tencent","baidu","huawei",
    "denoland","oven-sh","supabase","neondatabase","planetscale","railwayapp",
    "foxglove","zama-ai","pixeltable","nixtla","mirumee","astral-sh","prisma",
    "ringcentral","nearform","spideroak-inc","rocicorp","scopedb","tracel-ai",
    "databendlabs","napi-rs","cisco","cisco-ai-defense","ibm","oracle","sap","intel",
    "amd","qualcomm","arm","samsung","sony","adobe","salesforce","vmware","redhat",
}
ACADEMIC = re.compile(
    r"\b(universit|college|school|institute|academy|research (group|centre|center)|"
    r"laborator|\bcnrs\b|\bmit\b|harvard|stanford|cambridge|oxford|janelia|hhmi|"
    r"max.?planck|fraunhofer|inria|observator)\b", re.I)
FOUNDATION = re.compile(
    r"\b(foundation|non-?profit|nonprofit|\bfsf\b|software conservancy|"
    r"working group|consortium|\bsig\b|open collective)\b", re.I)
COMMERCIAL_LANG = re.compile(
    r"\b(inc\.?|llc|ltd\.?|gmbh|s\.?a\.?s\.?|b\.?v\.?|corp\.?|\bco\.\b|company|"
    r"startup|our platform|our product|saas|enterprise|pricing|customers|"
    r"we're hiring|backed by|yc ?[swf]\d)\b", re.I)
CORP_TLD = re.compile(r"https?://(?:www\.)?[^/]*\.(com|ai|io|dev|co|sh|app|cloud|tech)\b", re.I)

rows = list(csv.DictReader(open(os.path.join(OUT, "codspeed_buying_list.csv"))))

for r in rows:
    owner = (r["owner"] or "").lower()
    blob  = " ".join([r["owner"], r["org_name"], r["org_desc"]])
    site  = r["website"] or ""
    emps  = r["contributor_employers"] or ""

    if r["owner_type"] == "user":
        r["commercial_confidence"], r["confidence_reason"] = "personal", "personal account"
        continue

    # Known companies win before any regex, so Facebook stops reading as community.
    if owner in KNOWN_COMMERCIAL:
        r["commercial_confidence"], r["confidence_reason"] = "high", "known company"
    elif FOUNDATION.search(blob):
        r["commercial_confidence"], r["confidence_reason"] = "none", "foundation"
    elif ACADEMIC.search(blob) or ACADEMIC.search(emps):
        r["commercial_confidence"], r["confidence_reason"] = "none", "academic"
    elif COMMERCIAL_LANG.search(blob):
        r["commercial_confidence"], r["confidence_reason"] = "high", "commercial language"
    elif emps.strip():
        r["commercial_confidence"], r["confidence_reason"] = "medium", f"contributor employers: {emps[:40]}"
    elif site and CORP_TLD.search(site) and not site.lower().endswith(".org"):
        r["commercial_confidence"], r["confidence_reason"] = "medium", "commercial TLD"
    elif site:
        r["commercial_confidence"], r["confidence_reason"] = "low", "has site, non-commercial TLD"
    else:
        r["commercial_confidence"], r["confidence_reason"] = "low", "no org signal"

ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3, "personal": 4}
rows.sort(key=lambda r: (ORDER[r["commercial_confidence"]],
                         0 if r["bench_in_ci"] == "yes" else 1,
                         -float(r["score"])))

cols = ["repo","owner","org_name","commercial_confidence","confidence_reason","bench_in_ci",
        "language","stars","signals","last_push","website","org_location",
        "contributor_employers","org_desc","url","score"]
p = os.path.join(OUT, "codspeed_buying_list.csv")
with open(p, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for r in rows: w.writerow({k: r.get(k, "") for k in cols})

c = collections.Counter(r["commercial_confidence"] for r in rows)
print(dict(c))
hot = [r for r in rows if r["commercial_confidence"] in ("high","medium") and r["bench_in_ci"]=="yes"]
print(f"PRIORITY (high/medium confidence + benchmarks in CI): {len(hot)}")
for r in hot[:20]:
    print(f"  {r['commercial_confidence']:<6} {int(r['stars']):>7,}* {r['language']:<10} "
          f"{r['repo'][:36]:<36} {r['confidence_reason'][:34]}")
print(p)
