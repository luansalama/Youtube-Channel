from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .analytics import import_youtube_csv, report_for_slug
from .dashboard import generate_dashboard
from .core import (
    StudioError,
    add_calendar_item,
    add_deal,
    add_idea,
    add_library_asset,
    add_social_item,
    add_time_entry,
    active_project,
    advance_stage,
    approve_gate,
    business_entry,
    business_summary,
    continue_workflow,
    create_video,
    evaluate_stage,
    find_root,
    initialise_repository,
    list_projects,
    maintain_repository,
    load_project,
    package_publish,
    pause_video,
    read_csv_rows,
    reopen_stage,
    resume_video,
    table,
    time_summary,
    validate_repository,
)
from .server import run_studio
from .svg import generate_thumbnail_wireframes
from .story import audit_story
from .youtube import upload


def _root(args: argparse.Namespace) -> Path:
    return Path(args.root).resolve() if getattr(args, "root", None) else find_root()


def print_checks(results) -> bool:
    for result in results:
        severity = getattr(result, "severity", "error")
        if not result.ok:
            marker = "FAIL"
        elif severity == "warning":
            marker = "WARN"
        elif severity == "info":
            marker = "INFO"
        else:
            marker = "PASS"
        print(f"[{marker}] {result.label}: {result.detail}")
    return all(result.ok for result in results)


def cmd_init(args: argparse.Namespace) -> int:
    root = _root(args)
    initialise_repository(root)
    print(f"Initialised studio data files in {root}")
    return 0


def cmd_new_video(args: argparse.Namespace) -> int:
    path = create_video(_root(args), args.title, args.slug)
    print(f"Started: {path}")
    print("Open the dashboard with: mcstudio studio")
    return 0


def cmd_studio(args: argparse.Namespace) -> int:
    run_studio(_root(args), host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_continue(args: argparse.Namespace) -> int:
    result = continue_workflow(_root(args), args.slug)
    for phase in result.get("advanced", []):
        print(f"Advanced: {phase}")
    print(result.get("headline", "Workflow checked."))
    print(result.get("next_action", ""))
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    root = _root(args)
    slug = args.slug or ((active_project(root) or {}).get("slug"))
    if not slug:
        raise StudioError("There is no active video to pause.")
    pause_video(root, slug, args.by, args.reason)
    print(f"Paused {slug}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    resume_video(_root(args), args.slug, args.by)
    print(f"Resumed {args.slug}")
    return 0


def cmd_maintain(args: argparse.Namespace) -> int:
    ok = print_checks(maintain_repository(_root(args)))
    return 0 if ok else 2


def cmd_status(args: argparse.Namespace) -> int:
    root = _root(args)
    if args.slug:
        project = next((item for item in list_projects(root) if item.get("slug") == args.slug), None)
        if not project:
            raise StudioError(f"Unknown video project: {args.slug}")
        print(json.dumps(project, indent=2, ensure_ascii=False))
        print()
        print_checks(evaluate_stage(root, args.slug))
        return 0
    project = active_project(root)
    if not project:
        print("No active video. Start one from mcstudio studio.")
        return 0
    blockers = len([check for check in evaluate_stage(root, project["slug"]) if not check.ok])
    print(table([[project["slug"], project["stage"], project.get("state", "active"), blockers, project["title"]]], ["SLUG", "PHASE", "STATE", "BLOCKERS", "TITLE"]))
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    ok = print_checks(evaluate_stage(_root(args), args.slug, args.stage))
    return 0 if ok else 2


def cmd_approve(args: argparse.Namespace) -> int:
    root = _root(args)
    project = None
    if args.slug:
        _, project = load_project(root, args.slug)
    else:
        project = active_project(root)
    if not project:
        raise StudioError("There is no active video to approve.")
    gate = args.gate or get_current_gate(root, project["stage"])
    if not gate:
        raise StudioError("The current phase does not require human approval.")
    approve_gate(root, project["slug"], gate, args.by, args.note)
    print(f"Approved {gate} for {project['slug']}")
    result = continue_workflow(root, project["slug"])
    if result.get("advanced"):
        print(f"Advanced to {result.get('project', {}).get('stage', result.get('progress', {}).get('phase', 'next phase'))}")
    return 0


def get_current_gate(root: Path, stage_name: str) -> str | None:
    from .core import get_stage
    return get_stage(root, stage_name).get("approval_gate")


def cmd_advance(args: argparse.Namespace) -> int:
    stage = advance_stage(_root(args), args.slug)
    print(f"{args.slug} advanced to {stage}")
    return 0


def cmd_reopen(args: argparse.Namespace) -> int:
    reopen_stage(_root(args), args.slug, args.to_stage, args.by, args.reason)
    print(f"{args.slug} reopened at {args.to_stage}; affected approvals invalidated")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    ok = print_checks(validate_repository(_root(args)))
    return 0 if ok else 2


def cmd_story_audit(args: argparse.Namespace) -> int:
    root = _root(args)
    video_dir, project = load_project(root, args.slug)
    findings = audit_story(root, video_dir, args.scope, project.get("stage"))
    ok = print_checks(findings)
    return 0 if ok else 2


def cmd_idea_add(args: argparse.Namespace) -> int:
    result = add_idea(_root(args), vars(args))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_idea_list(args: argparse.Namespace) -> int:
    rows = read_csv_rows(_root(args) / "data" / "ideas.csv")
    if args.status:
        rows = [row for row in rows if row.get("status") == args.status]
    rows.sort(key=lambda row: float(row.get("score") or 0), reverse=True)
    print(table([[r.get("score"), r.get("status"), r.get("scope"), r.get("title")] for r in rows], ["SCORE", "STATUS", "SCOPE", "TITLE"]) if rows else "No ideas found.")
    return 0


def cmd_business_entry(args: argparse.Namespace) -> int:
    business_entry(_root(args), {
        "date": args.date,
        "type": args.type,
        "amount": args.amount,
        "currency": args.currency.upper(),
        "category": args.category,
        "video": args.video,
        "counterparty": args.counterparty,
        "note": args.note,
    })
    print("Business ledger updated.")
    return 0


def cmd_business_summary(args: argparse.Namespace) -> int:
    summary = business_summary(_root(args))
    rows = [[currency, f"{values['revenue']:.2f}", f"{values['expense']:.2f}", f"{values['profit']:.2f}"] for currency, values in sorted(summary.items())]
    print(table(rows, ["CURRENCY", "REVENUE", "EXPENSE", "PROFIT"]) if rows else "No ledger entries.")
    return 0


def cmd_deal_add(args: argparse.Namespace) -> int:
    add_deal(_root(args), {
        "brand": args.brand,
        "contact": args.contact,
        "status": args.status,
        "value": args.value,
        "currency": args.currency.upper(),
        "deliverables": args.deliverables,
        "next_action": args.next_action,
        "next_action_date": args.next_action_date,
        "notes": args.notes,
    })
    print("Deal added.")
    return 0


def cmd_deal_list(args: argparse.Namespace) -> int:
    rows = read_csv_rows(_root(args) / "data" / "business" / "deals.csv")
    if args.status:
        rows = [row for row in rows if row.get("status") == args.status]
    print(table([[r.get("status"), r.get("brand"), r.get("value"), r.get("currency"), r.get("next_action"), r.get("next_action_date")] for r in rows], ["STATUS", "BRAND", "VALUE", "CUR", "NEXT ACTION", "DATE"]) if rows else "No deals found.")
    return 0


def cmd_time_add(args: argparse.Namespace) -> int:
    add_time_entry(_root(args), {
        "date": args.date, "hours": args.hours, "area": args.area, "video": args.video,
        "task": args.task, "tool": args.tool, "notes": args.notes,
    })
    print("Time entry added.")
    return 0


def cmd_time_summary(args: argparse.Namespace) -> int:
    print(json.dumps(time_summary(_root(args)), indent=2, ensure_ascii=False))
    return 0


def cmd_calendar_add(args: argparse.Namespace) -> int:
    add_calendar_item(_root(args), {
        "video_slug": args.video_slug, "working_title": args.working_title, "format": args.format,
        "pillar": args.pillar, "status": args.status, "target_publish": args.target_publish,
        "priority": args.priority, "dependency": args.dependency, "notes": args.notes,
    })
    print("Calendar item added.")
    return 0


def cmd_calendar_list(args: argparse.Namespace) -> int:
    rows = read_csv_rows(_root(args) / "data" / "channel" / "content_calendar.csv")
    if args.status:
        rows = [row for row in rows if row.get("status") == args.status]
    rows.sort(key=lambda row: (row.get("target_publish") or "9999", row.get("priority") or ""))
    data = [[r.get("target_publish"), r.get("priority"), r.get("status"), r.get("video_slug"), r.get("working_title")] for r in rows]
    print(table(data, ["TARGET", "PRIORITY", "STATUS", "SLUG", "TITLE"]) if data else "No calendar items.")
    return 0


def cmd_social_add(args: argparse.Namespace) -> int:
    add_social_item(_root(args), {
        "platform": args.platform, "video_slug": args.video_slug, "target_publish": args.target_publish,
        "status": args.status, "copy_file": args.copy_file, "asset": args.asset,
        "approved_by": args.approved_by, "notes": args.notes,
    })
    print("Social queue item added.")
    return 0


def cmd_social_list(args: argparse.Namespace) -> int:
    rows = read_csv_rows(_root(args) / "data" / "channel" / "social_queue.csv")
    if args.status:
        rows = [row for row in rows if row.get("status") == args.status]
    data = [[r.get("target_publish"), r.get("platform"), r.get("status"), r.get("video_slug"), r.get("copy_file"), r.get("approved_by")] for r in rows]
    print(table(data, ["TARGET", "PLATFORM", "STATUS", "SLUG", "COPY", "APPROVED BY"]) if data else "No social queue items.")
    return 0


def cmd_asset_add(args: argparse.Namespace) -> int:
    add_library_asset(_root(args), {
        "asset_id": args.asset_id, "name": args.name, "type": args.type, "path_or_url": args.path_or_url,
        "owner": args.owner, "licence": args.licence, "version": args.version,
        "reuse_status": args.reuse_status, "used_in": args.used_in, "notes": args.notes,
    })
    print("Reusable asset added.")
    return 0


def cmd_asset_list(args: argparse.Namespace) -> int:
    rows = read_csv_rows(_root(args) / "data" / "library" / "assets.csv")
    if args.type:
        rows = [row for row in rows if row.get("type") == args.type]
    data = [[r.get("asset_id"), r.get("type"), r.get("reuse_status"), r.get("name"), r.get("version"), r.get("used_in")] for r in rows]
    print(table(data, ["ID", "TYPE", "STATUS", "NAME", "VERSION", "USED IN"]) if data else "No reusable assets.")
    return 0


def cmd_analytics_import(args: argparse.Namespace) -> int:
    result = import_youtube_csv(_root(args), args.csv, args.slug, args.video_id)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_analytics_report(args: argparse.Namespace) -> int:
    print(json.dumps(report_for_slug(_root(args), args.slug), indent=2, ensure_ascii=False))
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    print(generate_dashboard(_root(args), args.output))
    return 0


def cmd_wireframe(args: argparse.Namespace) -> int:
    paths = generate_thumbnail_wireframes(_root(args), args.slug)
    for path in paths:
        print(path)
    return 0


def cmd_package(args: argparse.Namespace) -> int:
    print(package_publish(_root(args), args.slug))
    return 0


def cmd_youtube_upload(args: argparse.Namespace) -> int:
    root = _root(args)
    if args.execute:
        _, project = load_project(root, args.slug)
        approvals = project.get("approvals", {})
        if not approvals.get("publish_lock"):
            raise StudioError("Executed upload requires the human publish_lock approval.")
        
    result = upload(
        args.video,
        args.metadata or (root / "videos" / args.slug / ".studio" / "internal" / "release" / "metadata.json"),
        args.client_secrets,
        args.token,
        args.privacy,
        args.publish_at,
        args.execute,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcstudio", description="Minecraft Narrative Studio operating harness")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--root", help="Repository root; normally auto-detected")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Initialise deterministic data ledgers")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("studio", help="Open the dashboard-first local interface")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_studio)

    p = sub.add_parser("new-video", help="Start the only active video")
    p.add_argument("title")
    p.add_argument("--slug")
    p.set_defaults(func=cmd_new_video)

    p = sub.add_parser("continue", help="Advance safe completed phases and stop at the next real decision")
    p.add_argument("slug", nargs="?")
    p.set_defaults(func=cmd_continue)

    p = sub.add_parser("pause", help="Pause the active video")
    p.add_argument("slug", nargs="?")
    p.add_argument("--by", default="Luan")
    p.add_argument("--reason", default="Paused to focus elsewhere")
    p.set_defaults(func=cmd_pause)

    p = sub.add_parser("resume", help="Resume one paused video as the only active video")
    p.add_argument("slug")
    p.add_argument("--by", default="Luan")
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("maintain", help="Run automatic maintenance and diagnostics")
    p.set_defaults(func=cmd_maintain)

    p = sub.add_parser("status", help="Show the active video or inspect one project")
    p.add_argument("slug", nargs="?")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("gate", help="Evaluate the current or specified stage gate")
    p.add_argument("slug")
    p.add_argument("--stage")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("approve", help="Approve the current human decision and continue")
    p.add_argument("slug", nargs="?")
    p.add_argument("--gate")
    p.add_argument("--by", default="Luan")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("advance", help="Advance exactly one stage after a passing gate")
    p.add_argument("slug")
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("reopen", help="Move to an earlier stage and invalidate affected approvals")
    p.add_argument("slug")
    p.add_argument("--to-stage", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_reopen)

    p = sub.add_parser("validate", help="Validate harness structure and active project gates")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("story-audit", help="Run deterministic narrative-structure diagnostics without enforcing formulaic conventions")
    p.add_argument("slug")
    p.add_argument("--scope", choices=["auto", "outline", "script", "all"], default="auto")
    p.set_defaults(func=cmd_story_audit)

    idea = sub.add_parser("idea", help="Manage the deterministic idea backlog").add_subparsers(dest="idea_command", required=True)
    p = idea.add_parser("add")
    p.add_argument("--title", required=True)
    p.add_argument("--premise", required=True)
    p.add_argument("--hook", required=True)
    p.add_argument("--format", default="investigation")
    p.add_argument("--scope", choices=["micro", "small", "medium", "large"], default="small")
    for field in ["clarity", "hook-strength", "visual-potential", "feasibility", "originality", "series-potential"]:
        p.add_argument("--" + field, type=int, choices=range(1, 6), required=True)
    p.add_argument("--status", default="backlog")
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_idea_add)
    p = idea.add_parser("list")
    p.add_argument("--status")
    p.set_defaults(func=cmd_idea_list)

    business = sub.add_parser("business", help="Track money and commercial pipeline").add_subparsers(dest="business_command", required=True)
    p = business.add_parser("entry")
    p.add_argument("--type", choices=["expense", "revenue"], required=True)
    p.add_argument("--amount", required=True)
    p.add_argument("--currency", default="BRL")
    p.add_argument("--category", required=True)
    p.add_argument("--video", default="")
    p.add_argument("--counterparty", default="")
    p.add_argument("--note", default="")
    p.add_argument("--date", default=date.today().isoformat())
    p.set_defaults(func=cmd_business_entry)
    p = business.add_parser("summary")
    p.set_defaults(func=cmd_business_summary)
    p = business.add_parser("deal-add")
    p.add_argument("--brand", required=True)
    p.add_argument("--contact", default="")
    p.add_argument("--status", default="lead")
    p.add_argument("--value", default="")
    p.add_argument("--currency", default="BRL")
    p.add_argument("--deliverables", default="")
    p.add_argument("--next-action", default="")
    p.add_argument("--next-action-date", default="")
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_deal_add)
    p = business.add_parser("deal-list")
    p.add_argument("--status")
    p.set_defaults(func=cmd_deal_list)

    p = business.add_parser("time-add")
    p.add_argument("--hours", required=True)
    p.add_argument("--area", required=True, choices=["development", "research", "writing", "build", "capture", "edit", "sound", "packaging", "business", "admin", "learning"])
    p.add_argument("--video", default="")
    p.add_argument("--task", required=True)
    p.add_argument("--tool", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--date", default=date.today().isoformat())
    p.set_defaults(func=cmd_time_add)
    p = business.add_parser("time-summary")
    p.set_defaults(func=cmd_time_summary)

    channel = sub.add_parser("channel", help="Manage channel calendar and reviewable social queue").add_subparsers(dest="channel_command", required=True)
    p = channel.add_parser("calendar-add")
    p.add_argument("--video-slug", required=True)
    p.add_argument("--working-title", required=True)
    p.add_argument("--format", default="story")
    p.add_argument("--pillar", default="narrative")
    p.add_argument("--status", default="planned")
    p.add_argument("--target-publish", default="")
    p.add_argument("--priority", choices=["low", "medium", "high"], default="medium")
    p.add_argument("--dependency", default="")
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_calendar_add)
    p = channel.add_parser("calendar-list")
    p.add_argument("--status")
    p.set_defaults(func=cmd_calendar_list)
    p = channel.add_parser("social-add")
    p.add_argument("--platform", required=True)
    p.add_argument("--video-slug", required=True)
    p.add_argument("--target-publish", default="")
    p.add_argument("--status", default="draft")
    p.add_argument("--copy-file", required=True)
    p.add_argument("--asset", default="")
    p.add_argument("--approved-by", default="")
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_social_add)
    p = channel.add_parser("social-list")
    p.add_argument("--status")
    p.set_defaults(func=cmd_social_list)

    library = sub.add_parser("library", help="Track reusable authored and licensed production assets").add_subparsers(dest="library_command", required=True)
    p = library.add_parser("asset-add")
    p.add_argument("--asset-id", default="")
    p.add_argument("--name", required=True)
    p.add_argument("--type", required=True)
    p.add_argument("--path-or-url", required=True)
    p.add_argument("--owner", default="Luan")
    p.add_argument("--licence", default="owned")
    p.add_argument("--version", default="1")
    p.add_argument("--reuse-status", default="available")
    p.add_argument("--used-in", default="")
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_asset_add)
    p = library.add_parser("asset-list")
    p.add_argument("--type")
    p.set_defaults(func=cmd_asset_list)

    analytics = sub.add_parser("analytics", help="Import and inspect YouTube Studio exports").add_subparsers(dest="analytics_command", required=True)
    p = analytics.add_parser("import")
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--video-id")
    p.set_defaults(func=cmd_analytics_import)
    p = analytics.add_parser("report")
    p.add_argument("--slug", required=True)
    p.set_defaults(func=cmd_analytics_report)

    p = sub.add_parser("dashboard", help="Generate a static copy of the dashboard")
    p.add_argument("--output", type=Path)
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("thumbnail-wireframes", help="Generate deterministic SVG thumbnail layout sketches")
    p.add_argument("slug")
    p.set_defaults(func=cmd_wireframe)

    p = sub.add_parser("package", help="Create a checksummed publish package")
    p.add_argument("slug")
    p.set_defaults(func=cmd_package)

    p = sub.add_parser("youtube-upload", help="Dry-run or explicitly upload through YouTube Data API")
    p.add_argument("slug")
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--metadata", type=Path)
    p.add_argument("--client-secrets", type=Path, default=Path("secrets/client_secrets.json"))
    p.add_argument("--token", type=Path, default=Path("secrets/youtube-token.json"))
    p.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    p.add_argument("--publish-at")
    p.add_argument("--execute", action="store_true", help="Actually upload; omission guarantees dry-run")
    p.set_defaults(func=cmd_youtube_upload)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except StudioError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
