# github-buying-signals

Finding go-to-market signal in public GitHub data.

Most outbound for developer tools starts from a firmographic list: company size,
funding stage, job titles. None of that tells you whether a team has the problem
your product solves. GitHub does, because engineering teams commit the evidence.

This repo mines that evidence, scores it, and separates the orgs that can actually
buy from the ones that can't.

---

## The thesis

Pick a product. Work out what a team with that problem leaves behind in a public
repo. Then search for it, and subtract the teams already using the product.

For a continuous-benchmarking tool, the chain is:

1. **A repo that runs benchmarks cares about performance.** Benchmarks are optional.
   Writing them is a deliberate cost a team only pays when speed matters.
2. **A repo that runs benchmarks in CI but doesn't gate on regressions has the pain.**
   They've automated measurement and still can't block a slow merge. That is the
   product's exact pitch, and they've already proven they'll spend effort here.
3. **A repo already running the product is a customer, not a prospect.** Subtract them.

Step 2 is the valuable one because it is *revealed behaviour*, not a stated attribute.
Stars tell you reach. A benchmark job in CI tells you intent.

---

## Worked example: CodSpeed

[CodSpeed](https://codspeed.io) runs benchmarks in CI and comments performance
changes on pull requests. Free for open source, $15/user/month beyond that.

**Result: 891 scored prospects, 373 org-owned, zero overlap with existing users.**

| Segment | What it means | Count |
|---|---|---|
| **Priority** | Commercial org, benchmarks already in CI | **69** |
| High confidence | Named company or explicit commercial language | 43 orgs |
| Medium confidence | Identified via contributor employers or commercial TLD | 237 orgs |
| Tier 1 (all owners) | Benchmarks in CI, no regression gating | 101 |
| Tier 2 (all owners) | Tooling declared, never wired into CI | 272 |
| Excluded | Already using CodSpeed | 259 repos |

Language mix: Rust 350, Python 228, TypeScript 196, JavaScript 84.

Tier 1 includes Deno, Feast, Instagram's LibCST, borgbackup, OSGeo/GDAL, Zama, and
wasmi. Tier 2 includes Bun, Burn, Databend, napi-rs, and pgdog — a softer pitch,
since the ask is finishing something they already started.

---

## How it works

**Signal queries** (GitHub code search). Note that the REST code search API accepts
`filename:` and silently returns zero for `path:` — a wrong query and an empty
result look identical, so every query is sanity-checked against a known-good count
before its output is trusted.

```
CodSpeedHQ/action  in .github/workflows   -> existing customers (exclusion set)
cargo bench        in .github/workflows   -> Rust, benchmarks already in CI
pytest-benchmark   in .github/workflows   -> Python, benchmarks already in CI
criterion / divan  in Cargo.toml          -> Rust tooling present
pytest-benchmark   in pyproject.toml      -> Python tooling present
tinybench / mitata / benchmark.js in package.json -> Node tooling present
```

**Filters.** Drops forks, archived repos, anything not pushed in 180 days, and any
language the product doesn't support.

**Scoring.** Org-owned +30. Stars `log10 × 11`, capped at 40. Benchmarks already in
CI +20. Each additional tooling signal +8. Rust or Python +10, other supported
languages +5.

**Classification.** A GitHub org is not a company. `classify_orgs.py` pulls org
metadata and top-contributor employer affiliations. `refine_classification.py` then
grades commercial confidence as high, medium, low, or none.

The first pass was binary and leaned on "org has a website", which labelled
borgbackup.org and cocotb.org as companies and — because its community regex ran
before any allowlist — labelled Facebook a community project. The refinement checks
known companies first, treats academic employers as a community signal rather than a
commercial one, and discounts `.org` domains. Grading beats a binary verdict here
because the underlying evidence genuinely varies in strength.

---

## What this does not do

Worth stating plainly, because a list that oversells itself is worse than no list.

- **Stars are a proxy for reach, not budget.** A 20k-star project may be three people.
- **Org classification is heuristic.** It reads descriptions, websites, and contributor
  employers. Only "high" confidence is backed by a named company or explicit commercial
  language; "medium" is inference. Treat the grade as a sort order, not a verdict.
- **No contacts.** This produces accounts and repos. Mapping to people is a separate pass.
- **Code search is capped.** Results are a large sample, not an exhaustive census.
- **Only bench-in-CI is revealed behaviour.** Every other dimension is an attribute,
  and attributes are weaker signal.

---

## Running it

Requires the [GitHub CLI](https://cli.github.com) authenticated with `repo` scope.
Standard library only, no dependencies.

```bash
gh auth login
python3 build_signal_list.py     # customers + benchmarks-in-CI
python3 expand_signal_list.py    # manifest tooling, merged and rescored
python3 classify_orgs.py         # pull org metadata + contributor employers
python3 refine_classification.py # grade commercial confidence
```

Outputs land in `data/`.

---

## Adapting it to another tool

Change the queries. The structure holds for anything that leaves a trace in a repo.

| Product | Pain signal | Exclusion signal |
|---|---|---|
| Error monitoring | `logging` config, no Sentry DSN | `sentry` in deps |
| CI optimisation | long-running workflow matrices | that vendor's action |
| Dependency security | lockfiles, no scanner action | `dependabot.yml`, `snyk` |
| Type checking | large untyped Python codebase | `mypy.ini`, `pyrightconfig` |

---

Built by [Reynaldo Espanola](https://github.com/reynaldo-oss).
