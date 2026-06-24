from __future__ import annotations

import json

import pytest

from scripts import precheck_retired_automation_tables as precheck


def test_retired_automation_precheck_scope_keeps_agent_and_channel_tables_out_of_drop_candidates():
    drop_tables = set(precheck.DROP_CANDIDATES)
    preserve_tables = set(precheck.PRESERVE_SAMPLES)

    assert "automation_event_v2" in drop_tables
    assert "automation_membership_v2" in drop_tables
    assert "automation_task_plan_v2" in drop_tables
    assert "automation_program_channel_binding" in drop_tables
    assert "automation_program" in drop_tables

    assert "automation_channel_contact" in preserve_tables
    assert "automation_channel_qrcode_asset" in preserve_tables
    assert "automation_agent_config" in preserve_tables
    assert "automation_agent_run" in preserve_tables
    assert "automation_agent_llm_call_log" in preserve_tables
    assert "automation_agent_output" in preserve_tables

    assert not (drop_tables & preserve_tables)


def test_temporal_detection_keeps_text_time_like_columns_out_of_recent_predicate():
    columns = [
        {"name": "created_at", "data_type": "timestamp with time zone"},
        {"name": "entered_at", "data_type": "text"},
        {"name": "finished_at", "data_type": "text"},
        {"name": "payload_json", "data_type": "jsonb"},
    ]

    assert precheck.temporal_columns(columns) == ["created_at"]
    assert precheck.non_temporal_time_like_columns(columns) == [
        {"name": "entered_at", "data_type": "text"},
        {"name": "finished_at", "data_type": "text"},
    ]


def test_run_precheck_blocks_physical_drop_when_recent_drop_candidate_exists(monkeypatch):
    monkeypatch.setattr(precheck, "DROP_CANDIDATES", ["automation_event_v2", "automation_program"])
    monkeypatch.setattr(precheck, "PRESERVE_SAMPLES", ["automation_channel_contact", "automation_agent_output"])

    def fake_inspect_table(_client, table_name, *, window_days):
        if table_name == "automation_event_v2":
            return {"table": table_name, "exists": True, "recent_window_count": 1}
        return {"table": table_name, "exists": True, "recent_window_count": 0}

    monkeypatch.setattr(precheck, "inspect_table", fake_inspect_table)

    result = precheck.run_precheck(object(), window_days=7)

    assert result["safe_to_drop"] is False
    assert [item["table"] for item in result["recent_blockers"]] == ["automation_event_v2"]
    assert {item["table"] for item in result["preserve_samples"]} == {
        "automation_channel_contact",
        "automation_agent_output",
    }


def test_main_requires_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(precheck.sys, "argv", ["precheck_retired_automation_tables.py"])

    exit_code = precheck.main()

    captured = capsys.readouterr()
    assert exit_code == 2
    assert json.loads(captured.err)["error"] == "database_url_missing"


def test_psql_client_uses_psql_read_only_query_shape(monkeypatch):
    captured = {}

    def fake_check_output(command, *, text):
        captured["command"] = command
        captured["text"] = text
        return "t\n"

    monkeypatch.setattr(precheck.subprocess, "check_output", fake_check_output)

    client = precheck.PsqlReadOnlyClient("postgresql://example")
    assert client.scalar("SELECT 1") == "t"

    command = captured["command"]
    assert command[:2] == ["psql", "postgresql://example"]
    assert "-X" in command
    assert "ON_ERROR_STOP=1" in command
    assert "-At" in command
    assert command[-1] == "SELECT 1"
