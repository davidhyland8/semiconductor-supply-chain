import argparse
import sys
from pathlib import Path

from scg import entities, paths, review
from scg.build import write_build
from scg.collect import collect_sec, collect_url
from scg.inferred import add_inferred
from scg.promote import load_decisions, promote
from scg.seed import validate_seed
from scg.validate import validate_extraction


def _validate_extraction(args: argparse.Namespace) -> int:
    failed = False
    for path in args.files:
        report = validate_extraction(Path(path))
        for w in report.warnings:
            print(f"warning: {w}")
        for e in report.errors:
            print(f"error: {e}")
        status = "ok" if report.ok else "FAILED"
        print(f"{path}: {report.records} records, {len(report.errors)} errors -> {status}")
        failed |= not report.ok
    return 1 if failed else 0


def _validate_seed(args: argparse.Namespace) -> int:
    report = validate_seed()
    for w in report.warnings:
        print(f"warning: {w}")
    for e in report.errors:
        print(f"error: {e}")
    print(f"seed: {report.records} records, {len(report.errors)} errors -> {'ok' if report.ok else 'FAILED'}")
    return 0 if report.ok else 1


def _promote(args: argparse.Namespace) -> int:
    files = [Path(f) for f in args.files] or sorted(paths.EXTRACTED_DIR.glob("*.jsonl"))
    result = promote(files)
    for r in result.rejected:
        print(f"rejected: {r}")
    for s in result.skipped:
        print(f"skipped: {s}")
    for c in result.entity_changes:
        print(f"entities: {c}")
    print(
        f"promoted {len(files)} files: +{result.edges_added} edges, +{result.evidence_added} evidence; "
        f"{len(result.pending)} waiting for review (scg review), {sum(not s.endswith('(ignored)') for s in result.skipped)} waiting on entities (scg entities)"
    )
    return 0


def _extraction_files(args: argparse.Namespace) -> list[Path]:
    return sorted(paths.EXTRACTED_DIR.glob("*.jsonl"))


def _queue(files: list[Path]) -> list[review.Candidate]:
    ignored = {r["key"] for r in entities._rows(paths.EXTRACTED_DIR / "entities.csv") if r.get("decision") == "ignore"}
    return review.candidates(files, decisions=load_decisions(paths.EXTRACTED_DIR / "decisions.csv"), ignored=ignored)


def _status(args: argparse.Namespace) -> int:
    statuses = review.status(cands=_queue(_extraction_files(args)))
    todo = review.to_extract(statuses)
    if args.todo:
        print(" ".join(todo))
        return 0
    states = ["promoted", "auto", "accepted", "needs_review", "blocked", "rejected", "ignored"]
    print(f"{'source':44} {'type':22} " + " ".join(f"{s[:8]:>8}" for s in states))
    totals = dict.fromkeys(states, 0)
    for st in statuses:
        if not st.extracted:
            continue
        for k, v in st.counts.items():
            totals[k] += v
        print(f"{st.source_id:44} {st.doc_type:22} " + " ".join(f"{st.counts.get(s, 0):>8}" for s in states))
    print(f"{'total':67} " + " ".join(f"{totals[s]:>8}" for s in states))
    print(f"\n{sum(s.extracted for s in statuses)} of {len(statuses)} sources extracted; {len(todo)} cached and waiting: {' '.join(todo)}")
    return 0


def _entities(args: argparse.Namespace) -> int:
    rejected = {k for k, d in load_decisions(paths.EXTRACTED_DIR / "decisions.csv").items() if d["decision"] == "reject"}
    rows = entities.refresh(_extraction_files(args), skip=rejected)
    errors = entities.check()
    for e in errors:
        print(f"error: {e}")
    open_rows = [r for r in rows if not r["decision"]]
    for r in open_rows:
        match = f" [ETO: {r['eto_match']}]" if r["eto_match"] else ""
        print(f"undecided: {r['proposed_name']} ({r['candidates']} candidates in {r['sources']}){match}")
    print(f"data/extracted/entities.csv: {len(rows)} entities, {len(open_rows)} undecided")
    return 1 if errors else 0


def _review(args: argparse.Namespace) -> int:
    cands = _queue(_extraction_files(args))
    names = {r["id"]: r["name"] for r in entities._rows(paths.SEED_DIR / "nodes.csv")}
    out = paths.EXTRACTED_DIR / "review.md"
    out.write_text(review.review_markdown(cands, names))
    n = sum(c.state in ("needs_review", "blocked") for c in cands)
    print(f"{out}: {n} candidates need a decision")
    return 0


def _build(args: argparse.Namespace) -> int:
    path, written = write_build()
    print(f"{'wrote' if written else 'unchanged'}: {path}")
    return 0


def _add_inferred(args: argparse.Namespace) -> int:
    added, skipped = add_inferred()
    print(f"inferred edges: {added} regenerated, {skipped} skipped (already covered by a stated source)")
    return 0


def _collect_url(args: argparse.Namespace) -> int:
    cached = collect_url(
        args.source_id, args.url, args.doc_type, args.title,
        company=args.company, publisher=args.publisher, published=args.published,
    )
    print(f"{args.source_id}: cached at {cached}")
    return 0


def _collect_sec(args: argparse.Namespace) -> int:
    collect_sec(only=set(args.companies) or None)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scg")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate data files")
    vsub = validate.add_subparsers(dest="target", required=True)
    ext = vsub.add_parser("extraction", help="validate data/extracted/*.jsonl files")
    ext.add_argument("files", nargs="+")
    ext.set_defaults(func=_validate_extraction)
    seed = vsub.add_parser("seed", help="validate data/seed/*.csv")
    seed.set_defaults(func=_validate_seed)

    collect = sub.add_parser("collect", help="collect source documents")
    csub = collect.add_subparsers(dest="target", required=True)
    sec = csub.add_parser("sec", help="latest 10-K/20-F for data/sources/sec_targets.csv")
    sec.add_argument("companies", nargs="*", help="limit to these node ids")
    sec.set_defaults(func=_collect_sec)

    prom = sub.add_parser("promote", help="merge reviewed extraction candidates into data/seed")
    prom.add_argument("files", nargs="*", help="extraction files (default: all of data/extracted/*.jsonl)")
    prom.set_defaults(func=_promote)

    url = csub.add_parser("url", help="fetch one web page or PDF into the source cache")
    url.add_argument("source_id")
    url.add_argument("url")
    url.add_argument("--doc-type", required=True)
    url.add_argument("--title", required=True)
    url.add_argument("--company", default="")
    url.add_argument("--publisher", default="")
    url.add_argument("--published", default="", help="YYYY[-MM[-DD]]")
    url.set_defaults(func=_collect_url)

    st = sub.add_parser("status", help="per-source extraction and review status")
    st.add_argument("--todo", action="store_true", help="print only the source ids waiting for extraction")
    st.set_defaults(func=_status)

    ent = sub.add_parser("entities", help="group unmatched companies across extractions into data/extracted/entities.csv")
    ent.set_defaults(func=_entities)

    rev = sub.add_parser("review", help="write data/extracted/review.md: candidates waiting for a decision")
    rev.set_defaults(func=_review)

    inf = sub.add_parser("add-inferred", help="write the curated inferred edges in scg/inferred.py to data/seed")
    inf.set_defaults(func=_add_inferred)

    bld = sub.add_parser("build", help="build data/build/graph.v<N>.json")
    bld.set_defaults(func=_build)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
