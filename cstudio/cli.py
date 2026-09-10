"""CLI for Cuts Studio."""
from __future__ import annotations
import argparse
import json
import os
import sys


def _root(args) -> str:
    from .core import find_root
    return os.path.abspath(args.root or find_root("."))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cstudio")
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init"); s.add_argument("--title", default="Nova produção")
    s = sub.add_parser("new"); s.add_argument("--title", required=True); s.add_argument("--slug", default=""); s.add_argument("--source-url", default="")
    s = sub.add_parser("status"); s.add_argument("slug", nargs="?")
    s = sub.add_parser("maintain")
    s = sub.add_parser("validate"); s.add_argument("slug", nargs="?")
    s = sub.add_parser("gate"); s.add_argument("slug")
    s = sub.add_parser("approve"); s.add_argument("slug"); s.add_argument("--gate", required=True); s.add_argument("--by", default="showrunner"); s.add_argument("--note", default="")
    s = sub.add_parser("advance"); s.add_argument("slug")
    s = sub.add_parser("reopen"); s.add_argument("slug"); s.add_argument("--to-stage", required=True); s.add_argument("--by", default="showrunner"); s.add_argument("--reason", required=True)
    s = sub.add_parser("pause"); s.add_argument("slug"); s.add_argument("--reason", default="")
    s = sub.add_parser("resume"); s.add_argument("slug")
    s = sub.add_parser("continue"); s.add_argument("slug", nargs="?")

    s = sub.add_parser("propose"); s.add_argument("slug"); s.add_argument("--request", required=True); s.add_argument("--runner", default=""); s.add_argument("--model", default="")
    s = sub.add_parser("proposal-list"); s.add_argument("slug")
    s = sub.add_parser("proposal-import"); s.add_argument("slug"); s.add_argument("--file", required=True); s.add_argument("--request", default="")
    s = sub.add_parser("proposal-apply"); s.add_argument("slug"); s.add_argument("--id", required=True); s.add_argument("--by", default="showrunner")
    s = sub.add_parser("proposal-discard"); s.add_argument("slug"); s.add_argument("--id", required=True)

    s = sub.add_parser("ingest"); s.add_argument("slug"); s.add_argument("--asset-id", required=True); s.add_argument("--kind", required=True); s.add_argument("--path", required=True); s.add_argument("--rights", default="sem_autorizacao_confirmada")
    s = sub.add_parser("twitch-scrape"); s.add_argument("slug"); s.add_argument("--streamer", required=True); s.add_argument("--target", default="3"); s.add_argument("--threads", type=int, choices=(1, 2, 4, 8), default=4); s.add_argument("--force", action="store_true"); s.add_argument("--no-resume", action="store_true"); s.add_argument("--sequential", action="store_true")
    s = sub.add_parser("rights"); s.add_argument("slug"); s.add_argument("--asset", required=True); s.add_argument("--status", required=True); s.add_argument("--by", default=""); s.add_argument("--scope", default=""); s.add_argument("--evidence", default="")
    s = sub.add_parser("cutlist-validate"); s.add_argument("slug")
    s = sub.add_parser("nle-export"); s.add_argument("slug"); s.add_argument("--driver", default="davinci-resolve"); s.add_argument("--outdir", default="")
    s = sub.add_parser("master"); s.add_argument("slug"); s.add_argument("--file", required=True); s.add_argument("--duration", type=float, required=True); s.add_argument("--fps", type=float, default=30.0)
    s = sub.add_parser("metadata"); s.add_argument("slug"); s.add_argument("--title", required=True); s.add_argument("--description", required=True); s.add_argument("--tags", required=True)
    s = sub.add_parser("package"); s.add_argument("slug")
    s = sub.add_parser("publish"); s.add_argument("slug"); s.add_argument("--execute", action="store_true")
    s = sub.add_parser("learn"); s.add_argument("slug"); s.add_argument("--lesson", required=True)
    s = sub.add_parser("studio"); s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8765); s.add_argument("--no-browser", action="store_true")
    s = sub.add_parser("dashboard"); s.add_argument("--output", default="")
    s = sub.add_parser("zai-import"); s.add_argument("--json", required=True); s.add_argument("--session-id", default=""); s.add_argument("--out", default="")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = _root(args)
    try:
        from . import core as C
        if args.cmd == "init":
            C.maintain_repository(root)
            print(f"root ready: {root}")
        elif args.cmd == "new":
            p = C.create_production(root, args.title, args.slug or None, args.source_url)
            print(json.dumps({"slug": p["slug"], "stage": p["stage"]}, ensure_ascii=False))
        elif args.cmd == "status":
            slug = args.slug or ((C.active_production(root) or {}).get("slug"))
            if not slug:
                print(json.dumps({"productions": C.list_productions(root)}, ensure_ascii=False, indent=2)); return 0
            print(json.dumps(C.workflow_status(root, slug), ensure_ascii=False, indent=2))
        elif args.cmd == "maintain":
            print(json.dumps(C.maintain_repository(root), ensure_ascii=False, indent=2))
        elif args.cmd == "validate":
            slug = args.slug or ((C.active_production(root) or {}).get("slug"))
            checks = C.evaluate_stage(root, slug, include_approval=True)
            print(json.dumps([c.__dict__ for c in checks], ensure_ascii=False, indent=2))
            return 1 if any(not c.ok for c in checks) else 0
        elif args.cmd == "gate":
            print(json.dumps(C.gate_status(root, args.slug), ensure_ascii=False, indent=2))
        elif args.cmd == "approve":
            print(json.dumps(C.approve_gate(root, args.slug, args.gate, args.by, args.note), ensure_ascii=False, indent=2))
        elif args.cmd == "advance":
            print(C.advance_stage(root, args.slug))
        elif args.cmd == "reopen":
            C.reopen_stage(root, args.slug, args.to_stage, args.by, args.reason); print("reopened")
        elif args.cmd == "pause":
            C.pause_production(root, args.slug, reason=args.reason); print("paused")
        elif args.cmd == "resume":
            C.resume_production(root, args.slug); print("resumed")
        elif args.cmd == "continue":
            print(json.dumps(C.continue_workflow(root, args.slug), ensure_ascii=False, indent=2))
        elif args.cmd == "propose":
            from . import runners as R
            print(json.dumps(R.execute_runner(root, args.slug, args.request, args.runner, args.model), ensure_ascii=False, indent=2)[:4000])
        elif args.cmd == "proposal-list":
            from . import proposals as P
            print(json.dumps(P.list_proposals(root, args.slug), ensure_ascii=False, indent=2)[:6000])
        elif args.cmd == "proposal-import":
            from . import runners as R
            payload = open(args.file, encoding="utf-8").read()
            print(json.dumps(R.import_proposal(root, args.slug, payload, args.request), ensure_ascii=False, indent=2)[:4000])
        elif args.cmd == "proposal-apply":
            from . import proposals as P
            print(json.dumps(P.apply_proposal(root, args.slug, args.id), ensure_ascii=False)[:2000])
        elif args.cmd == "proposal-discard":
            from . import proposals as P
            P.discard_proposal(root, args.slug, args.id); print("discarded")
        elif args.cmd == "ingest":
            from . import pipeline as PL
            print(json.dumps(PL.register_asset(root, args.slug, args.asset_id, args.kind, args.path, args.rights), ensure_ascii=False))
        elif args.cmd == "twitch-scrape":
            from . import twitch as TW
            rec = TW.run_scrape(root, args.slug, args.streamer, args.target, threads=args.threads, force=args.force, resume=not args.no_resume, sequential=args.sequential)
            print(json.dumps(rec, ensure_ascii=False, indent=2))
            return 0 if rec.get("status") == "completed" else 1
        elif args.cmd == "rights":
            from . import rights as RT
            print(json.dumps(RT.set_asset_rights(root, args.slug, args.asset, args.status, args.by, args.scope, args.evidence), ensure_ascii=False))
        elif args.cmd == "cutlist-validate":
            from . import cutlist as CL
            from .core import prod_path
            p = os.path.join(prod_path(root, args.slug), ".studio/internal/cutlist/cutlist.csv")
            print(json.dumps(CL.validate_cutlist_file(p), ensure_ascii=False, indent=2))
        elif args.cmd == "nle-export":
            from . import nle as NLE
            from .core import prod_path
            vdir = prod_path(root, args.slug)
            tl = json.load(open(os.path.join(vdir, ".studio/internal/assembly/timeline.json"), encoding="utf-8"))
            _, proj = C.load_project(root, args.slug)
            out = args.outdir or os.path.join(vdir, ".studio/internal/assembly/resolve")
            print(json.dumps(NLE.get_driver(args.driver).export(tl, out, proj.get("title", "")), ensure_ascii=False, indent=2))
        elif args.cmd == "master":
            from . import pipeline as PL
            print(json.dumps(PL.register_master(root, args.slug, args.file, args.duration, args.fps), ensure_ascii=False, indent=2))
        elif args.cmd == "metadata":
            from . import pipeline as PL
            print(json.dumps(PL.write_metadata(root, args.slug, args.title, args.description, args.tags.split(","), ), ensure_ascii=False, indent=2))
        elif args.cmd == "package":
            print(json.dumps(C.package_publish(root, args.slug), ensure_ascii=False, indent=2))
        elif args.cmd == "publish":
            from . import pipeline as PL
            if args.execute:
                print(json.dumps(PL.publish_execute(root, args.slug), ensure_ascii=False, indent=2))
            else:
                print(json.dumps(PL.publish_dry_run(root, args.slug), ensure_ascii=False, indent=2))
        elif args.cmd == "learn":
            from . import pipeline as PL
            PL.append_lesson(root, args.slug, args.lesson); print("lesson added")
        elif args.cmd == "studio":
            from .server import run
            run(root, args.host, args.port, open_browser=not args.no_browser)
        elif args.cmd == "dashboard":
            from .dashboard import render
            slug = (C.active_production(root) or {}).get("slug", "")
            out = render(root, "gates", slug)
            if args.output:
                open(args.output, "w", encoding="utf-8").write(out); print(args.output)
            else:
                print(out[:3000])
        elif args.cmd == "zai-import":
            from .session import load_session_file, to_markdown
            data = load_session_file(args.json)
            md = to_markdown(data, args.session_id)
            out = args.out or os.path.join(root, "CONTEXT", "zai-session.md")
            open(out, "w", encoding="utf-8").write(md)
            print(f"wrote {out} ({len(md)} chars)")
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
