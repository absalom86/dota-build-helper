"""Standalone Windows entry point; intentionally excludes local settings and caches."""
import sys

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        import json
        from pathlib import Path
        import traceback
        report = Path(sys.argv[2]).resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"stage": "entry", "ok": False}), encoding="utf-8")
        try:
            from dota_helper.packaging_check import run
            code = run(str(report))
        except Exception:
            report.write_text(json.dumps({"ok": False, "error": traceback.format_exc()}, indent=2), encoding="utf-8")
            code = 1
        raise SystemExit(code)
    from dota_helper.app import main
    raise SystemExit(main())
