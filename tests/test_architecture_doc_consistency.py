from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "tools/check_architecture_doc_consistency.py"
SKILL_DOC = REPO_ROOT / "docs/development/ai_crm_next_architecture_skill.md"
TEMPLATE_DOC = REPO_ROOT / "docs/development/codex_task_template.md"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_architecture_doc_consistency", CHECKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_architecture_skill_contains_required_rules() -> None:
    text = SKILL_DOC.read_text(encoding="utf-8")
    for phrase in [
        "默认 runtime 是 AI-CRM Next FastAPI modular monolith",
        "`app.py run` 默认启动 `aicrm_next.main:app`",
        "legacy Flask 只作为显式 fallback 和生产兼容 facade",
        "`wecom_ability_service/` 保留为 legacy fallback",
        "`openclaw_service/` 和 `legacy_flask/openclaw_legacy/` 已物理删除，不得重新引入",
        "MCP/OpenClaw 后续只允许通过 `aicrm_next.integration_gateway` adapter boundary 承接",
        "real external adapter 仍 blocked / fake / staging-disabled",
        "禁止在 frontend_compat 继续新增直接 SQL",
        "禁止 API 层直接 import 其他 context 的 `repo.py` 或 `service.py`",
        "禁止把 checker 本地结果写成 production canary evidence",
        "本任务属于哪个 capability owner？",
        "Risk / rollback",
    ]:
        assert phrase in text


def test_codex_task_template_points_to_architecture_skill() -> None:
    text = TEMPLATE_DOC.read_text(encoding="utf-8")
    assert "docs/development/ai_crm_next_architecture_skill.md" in text
    assert "Capability owner:" in text
    assert "Current route owner: Next / legacy facade / blocked" in text
    assert "Risk / rollback" in text


def test_architecture_doc_checker_passes_current_docs() -> None:
    checker = _load_checker()
    report = checker.build_report()
    assert report["ok"], report["blockers"]
    assert report["checks"]["openclaw_live_source_violations"] == {}
    assert report["checks"]["llm_handoff_openclaw_read_suggestion"] == []


def test_architecture_doc_checker_detects_live_openclaw_source_drift(tmp_path: Path) -> None:
    for relpath in _load_checker().SCANNED_DOCS:
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        (REPO_ROOT / relpath).read_text(encoding="utf-8")
        target.write_text((REPO_ROOT / relpath).read_text(encoding="utf-8"), encoding="utf-8")
    dev_dir = tmp_path / "docs/development"
    dev_dir.mkdir(parents=True, exist_ok=True)
    (dev_dir / "ai_crm_next_architecture_skill.md").write_text("stub\n", encoding="utf-8")
    (dev_dir / "codex_task_template.md").write_text("stub\n", encoding="utf-8")

    readme = tmp_path / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\n## Bad drift\n- `openclaw_service/`\n  - legacy OpenClaw 适配、工具和服务\n",
        encoding="utf-8",
    )

    checker = _load_checker()
    report = checker.build_report(tmp_path)
    assert report["ok"] is False
    assert "README.md" in report["checks"]["openclaw_live_source_violations"]


def test_architecture_doc_checker_cli_outputs_pass() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "tools/check_architecture_doc_consistency.py",
            "--output-md",
            "/tmp/architecture_doc_consistency.md",
            "--output-json",
            "/tmp/architecture_doc_consistency.json",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "overall: PASS" in completed.stdout
