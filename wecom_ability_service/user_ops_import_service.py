
from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .db import get_db
from .identity_binding_service import _normalize_mobile
from .user_ops_pool_service import reload_user_ops_pool
from .user_ops_shared import _current_user_ops_operator, _db_bool

def _is_experience_lead_header(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"手机号", "手机", "mobile", "phone", "手机号列表"}

def _is_activation_status_header(value: str) -> bool:
    normalized = str(value or "").strip().lower().replace(" ", "")
    return normalized in {
        "手机号,状态",
        "手机号,状态,备注",
        "mobile,status",
        "mobile,status,remark",
    }

def _collect_experience_lead_mobiles(raw_values: list[str]) -> dict[str, Any]:
    valid_rows: list[str] = []
    invalid_rows: list[str] = []
    seen: set[str] = set()
    unique_mobiles: list[str] = []
    total_rows = 0
    for raw_value in raw_values:
        candidate = str(raw_value or "").strip()
        if not candidate or _is_experience_lead_header(candidate):
            continue
        total_rows += 1
        try:
            mobile = _normalize_mobile(candidate)
        except ValueError:
            invalid_rows.append(candidate)
            continue
        valid_rows.append(mobile)
        if mobile not in seen:
            seen.add(mobile)
            unique_mobiles.append(mobile)
    return {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "unique_mobiles": unique_mobiles,
        "invalid_rows": invalid_rows,
        "duplicate_count": max(0, len(valid_rows) - len(unique_mobiles)),
    }

def _parse_experience_leads_from_text(pasted_text: str) -> dict[str, Any]:
    raw_values = [item for item in re.split(r"[\s,，;；]+", str(pasted_text or "").strip()) if item.strip()]
    result = _collect_experience_lead_mobiles(raw_values)
    result["input_mode"] = "pasted_text"
    return result

def _extract_xlsx_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for item in root.findall("a:si", namespace):
        values.append("".join(item.itertext()).strip())
    return values

def _parse_xlsx_rows(file_bytes: bytes) -> list[list[str]]:
    with ZipFile(BytesIO(file_bytes)) as archive:
        shared_strings = _extract_xlsx_shared_strings(archive)
        worksheet_name = "xl/worksheets/sheet1.xml"
        if worksheet_name not in archive.namelist():
            worksheet_candidates = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml"))
            if not worksheet_candidates:
                return []
            worksheet_name = worksheet_candidates[0]
        root = ET.fromstring(archive.read(worksheet_name))
        namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows: list[str] = []
        for row in root.findall(".//a:sheetData/a:row", namespace):
            cell_values: list[str] = []
            for cell in row.findall("a:c", namespace):
                cell_type = str(cell.attrib.get("t") or "").strip()
                if cell_type == "inlineStr":
                    text_value = "".join(cell.itertext()).strip()
                else:
                    value_node = cell.find("a:v", namespace)
                    text_value = str(value_node.text or "").strip() if value_node is not None else ""
                    if cell_type == "s" and text_value.isdigit():
                        index = int(text_value)
                        text_value = shared_strings[index] if 0 <= index < len(shared_strings) else ""
                cell_values.append(text_value)
            if any(value.strip() for value in cell_values):
                rows.append(cell_values)
        return rows

def _parse_experience_leads_from_file(*, file_name: str, file_bytes: bytes) -> dict[str, Any]:
    normalized_name = str(file_name or "").strip().lower()
    if normalized_name.endswith(".xlsx"):
        raw_values = [row[0] for row in _parse_xlsx_rows(file_bytes) if row]
    else:
        try:
            decoded = file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("only .xlsx or utf-8 text files are supported") from exc
        raw_values = [item for item in re.split(r"[\r\n,，;；\t ]+", decoded) if item.strip()]
    result = _collect_experience_lead_mobiles(raw_values)
    result["input_mode"] = "file"
    result["file_name"] = str(file_name or "").strip()
    return result

def _normalize_activation_status_value(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace(" ", "").replace("_", "").replace("-", "")
    mapping = {
        "notactivated": "not_activated",
        "未激活": "not_activated",
        "activated": "activated",
        "激活": "activated",
        "highintent": "high_intent",
        "高意向": "high_intent",
    }
    result = mapping.get(normalized)
    if not result:
        raise ValueError("activation_status is invalid")
    return result

def _parse_activation_status_line(line: str) -> tuple[str, str, str]:
    parts = [item.strip() for item in re.split(r"[,\t，]+", str(line or "").strip())]
    parts = [item for item in parts if item]
    if not parts:
        raise ValueError("activation row is empty")
    mobile = _normalize_mobile(parts[0])
    if len(parts) < 2:
        raise ValueError("activation_status is required")
    activation_status = _normalize_activation_status_value(parts[1])
    activation_remark = ",".join(parts[2:]).strip() if len(parts) > 2 else ""
    if activation_status != "high_intent":
        activation_remark = ""
    return mobile, activation_status, activation_remark

def _parse_activation_status_from_text(pasted_text: str) -> dict[str, Any]:
    lines = [line.strip() for line in str(pasted_text or "").splitlines() if line.strip()]
    rows: list[dict[str, str]] = []
    invalid_rows: list[str] = []
    total_rows = 0
    for line in lines:
        if _is_activation_status_header(line):
            continue
        total_rows += 1
        try:
            mobile, activation_status, activation_remark = _parse_activation_status_line(line)
        except ValueError:
            invalid_rows.append(line)
            continue
        rows.append(
            {
                "mobile": mobile,
                "activation_status": activation_status,
                "activation_remark": activation_remark,
            }
        )
    return {
        "input_mode": "pasted_text",
        "total_rows": total_rows,
        "rows": rows,
        "invalid_rows": invalid_rows,
    }

def _parse_activation_status_from_file(*, file_name: str, file_bytes: bytes) -> dict[str, Any]:
    normalized_name = str(file_name or "").strip().lower()
    if normalized_name.endswith(".xlsx"):
        raw_rows = _parse_xlsx_rows(file_bytes)
        lines = []
        for row in raw_rows:
            normalized_row = [str(item or "").strip() for item in row[:3]]
            if not any(normalized_row):
                continue
            lines.append(",".join(normalized_row))
    else:
        try:
            decoded = file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("only .xlsx or utf-8 text files are supported") from exc
        lines = [line.strip() for line in decoded.splitlines() if line.strip()]
    result = _parse_activation_status_from_text("\n".join(lines))
    result["input_mode"] = "file"
    result["file_name"] = str(file_name or "").strip()
    return result

def _create_user_ops_import_batch(
    *,
    import_type: str,
    file_name: str,
    total_rows: int,
    success_rows: int,
    failed_rows: int,
    error_summary: str,
    created_by: str,
) -> int:
    row = get_db().execute(
        """
        INSERT INTO user_ops_import_batches (
            import_type, file_name, total_rows, success_rows, failed_rows, error_summary, created_by, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (
            import_type,
            file_name,
            int(total_rows),
            int(success_rows),
            int(failed_rows),
            error_summary,
            created_by,
        ),
    ).fetchone()
    return int(row["id"])

def import_experience_leads(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    operator = str(created_by or _current_user_ops_operator()).strip() or "admin_user_ops"
    if file_bytes is not None:
        parsed = _parse_experience_leads_from_file(file_name=file_name, file_bytes=file_bytes)
    else:
        parsed = _parse_experience_leads_from_text(pasted_text)

    unique_mobiles = list(parsed["unique_mobiles"])
    invalid_rows = list(parsed["invalid_rows"])
    total_rows = int(parsed["total_rows"])
    success_rows = len(parsed["valid_rows"])
    failed_rows = len(invalid_rows)
    duplicate_count = int(parsed["duplicate_count"])

    if not unique_mobiles:
        raise ValueError("no valid mobile numbers found")

    error_summary_parts: list[str] = []
    if invalid_rows:
        preview = " / ".join(invalid_rows[:5])
        suffix = " ..." if len(invalid_rows) > 5 else ""
        error_summary_parts.append(f"invalid: {preview}{suffix}")
    if duplicate_count:
        error_summary_parts.append(f"duplicates: {duplicate_count}")
    error_summary = "; ".join(error_summary_parts)

    db = get_db()
    batch_id = _create_user_ops_import_batch(
        import_type="experience_leads",
        file_name=str(parsed.get("file_name") or file_name or parsed.get("input_mode") or "").strip(),
        total_rows=total_rows,
        success_rows=success_rows,
        failed_rows=failed_rows,
        error_summary=error_summary,
        created_by=operator,
    )

    for mobile in unique_mobiles:
        existing = db.execute(
            """
            SELECT id, mobile, source_type, import_batch_id, created_by, is_active
            FROM user_ops_experience_leads
            WHERE mobile = ?
            LIMIT 1
            """,
            (mobile,),
        ).fetchone()
        db.execute(
            """
            INSERT INTO user_ops_experience_leads (
                mobile, source_type, import_batch_id, created_by, is_active, created_at, updated_at
            )
            VALUES (?, 'experience_import', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(mobile) DO UPDATE SET
                source_type = excluded.source_type,
                import_batch_id = excluded.import_batch_id,
                created_by = excluded.created_by,
                is_active = excluded.is_active,
                updated_at = CURRENT_TIMESTAMP
            """,
            (mobile, batch_id, operator, _db_bool(True)),
        )
        db.execute(
            """
            INSERT INTO user_ops_pool_history (
                pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
            )
            VALUES (?, ?, '', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                None,
                mobile,
                "experience_import_source_upsert",
                json.dumps(dict(existing or {}), ensure_ascii=False),
                json.dumps(
                    {
                        "mobile": mobile,
                        "source_type": "experience_import",
                        "import_batch_id": batch_id,
                        "created_by": operator,
                        "is_active": True,
                    },
                    ensure_ascii=False,
                ),
                operator,
                "experience_import",
            ),
        )
    db.commit()

    reload_payload = reload_user_ops_pool()
    return {
        "ok": True,
        "import_type": "experience_leads",
        "input_mode": str(parsed.get("input_mode") or "").strip(),
        "batch_id": batch_id,
        "total_rows": total_rows,
        "success_rows": success_rows,
        "failed_rows": failed_rows,
        "duplicate_count": duplicate_count,
        "unique_mobile_count": len(unique_mobiles),
        "invalid_rows": invalid_rows,
        "reload": reload_payload,
    }

def import_activation_status_source(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    operator = str(created_by or _current_user_ops_operator()).strip() or "admin_user_ops"
    if file_bytes is not None:
        parsed = _parse_activation_status_from_file(file_name=file_name, file_bytes=file_bytes)
    else:
        parsed = _parse_activation_status_from_text(pasted_text)

    rows = list(parsed["rows"])
    invalid_rows = list(parsed["invalid_rows"])
    total_rows = int(parsed["total_rows"])
    failed_rows = len(invalid_rows)

    if not rows:
        raise ValueError("no valid activation rows found")

    deduped_by_mobile: dict[str, dict[str, str]] = {}
    for row in rows:
        deduped_by_mobile[str(row["mobile"])] = row
    unique_rows = list(deduped_by_mobile.values())
    duplicate_count = max(0, len(rows) - len(unique_rows))
    error_summary_parts: list[str] = []
    if invalid_rows:
        preview = " / ".join(invalid_rows[:5])
        suffix = " ..." if len(invalid_rows) > 5 else ""
        error_summary_parts.append(f"invalid: {preview}{suffix}")
    if duplicate_count:
        error_summary_parts.append(f"duplicates: {duplicate_count}")
    error_summary = "; ".join(error_summary_parts)

    db = get_db()
    batch_id = _create_user_ops_import_batch(
        import_type="activation_status",
        file_name=str(parsed.get("file_name") or file_name or parsed.get("input_mode") or "").strip(),
        total_rows=total_rows,
        success_rows=len(rows),
        failed_rows=failed_rows,
        error_summary=error_summary,
        created_by=operator,
    )

    for row in unique_rows:
        mobile = str(row["mobile"])
        existing = db.execute(
            """
            SELECT id, mobile, activation_status, activation_remark, import_batch_id, created_by, is_active
            FROM user_ops_activation_status_source
            WHERE mobile = ?
            LIMIT 1
            """,
            (mobile,),
        ).fetchone()
        db.execute(
            """
            INSERT INTO user_ops_activation_status_source (
                mobile, activation_status, activation_remark, import_batch_id, created_by, is_active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(mobile) DO UPDATE SET
                activation_status = excluded.activation_status,
                activation_remark = excluded.activation_remark,
                import_batch_id = excluded.import_batch_id,
                created_by = excluded.created_by,
                is_active = excluded.is_active,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                mobile,
                row["activation_status"],
                row["activation_remark"],
                batch_id,
                operator,
                _db_bool(True),
            ),
        )
        db.execute(
            """
            INSERT INTO user_ops_pool_history (
                pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
            )
            VALUES (?, ?, '', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                None,
                mobile,
                "activation_import_upsert",
                json.dumps(dict(existing or {}), ensure_ascii=False),
                json.dumps(
                    {
                        "mobile": mobile,
                        "activation_status": row["activation_status"],
                        "activation_remark": row["activation_remark"],
                        "import_batch_id": batch_id,
                        "created_by": operator,
                        "is_active": True,
                    },
                    ensure_ascii=False,
                ),
                operator,
                "activation_import",
            ),
        )
    db.commit()

    reload_payload = reload_user_ops_pool()
    return {
        "ok": True,
        "import_type": "activation_status",
        "input_mode": str(parsed.get("input_mode") or "").strip(),
        "batch_id": batch_id,
        "total_rows": total_rows,
        "success_rows": len(rows),
        "failed_rows": failed_rows,
        "duplicate_count": duplicate_count,
        "unique_mobile_count": len(unique_rows),
        "invalid_rows": invalid_rows,
        "reload": reload_payload,
    }
