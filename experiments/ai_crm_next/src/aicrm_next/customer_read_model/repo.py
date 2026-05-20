from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import create_engine, delete, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from aicrm_next.shared.config import Settings, get_settings
from aicrm_next.shared.typing import JsonDict

from .models import (
    customer_detail_snapshot_next,
    customer_list_index_next,
    customer_recent_message_next,
    customer_timeline_event_next,
)


class CustomerReadRepository(Protocol):
    def list_customers(
        self,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]: ...

    def get_customer_detail(self, external_userid: str) -> JsonDict | None: ...

    def get_customer(self, external_userid: str) -> JsonDict | None: ...

    def get_customer_timeline(
        self,
        external_userid: str,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]: ...

    def list_timeline(
        self,
        external_userid: str,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]: ...

    def get_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]: ...

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]: ...

    def customer_exists(self, external_userid: str) -> bool: ...


class FixtureCustomerReadRepository:
    """Fixture read repository shaped for the future PostgreSQL projection repo."""

    def __init__(self) -> None:
        self._customers: list[JsonDict] = [
            {
                "person_id": "person_001",
                "external_userid": "wx_ext_001",
                "customer_name": "张小蓝",
                "remark": "小蓝",
                "description": "9.9 试用后关注正式课安排",
                "owner_userid": "ZhaoYanFang",
                "owner_display_name": "赵艳芳",
                "mobile": "13800138000",
                "tags": ["付费意向", "黄小璨", "重点跟进"],
                "class_user_status": {
                    "current_status": "lead_trial",
                    "signup_status": "trial_9_9",
                    "signup_label_name": "9.9 试用",
                    "activation_bucket": "activated",
                    "updated_at": "2026-05-18T10:20:00+08:00",
                },
                "last_message_at": "2026-05-18T10:15:00+08:00",
                "last_touch_at": "2026-05-18T10:20:00+08:00",
                "updated_at": "2026-05-18T10:20:00+08:00",
                "binding": {"is_bound": True, "mobile": "13800138000", "binding_status": "bound"},
                "identity": {"person_id": "person_001", "external_userid": "wx_ext_001", "mobile": "13800138000"},
                "follow_users": [{"userid": "ZhaoYanFang", "display_name": "赵艳芳", "is_primary": True}],
                "marketing_summary": {
                    "main_stage": "trial",
                    "sub_stage": "activated_focus",
                    "value_segment": "high_intent",
                    "last_dispatch_at": "2026-05-18T09:00:00+08:00",
                },
                "marketing_profile": {
                    "stage_key": "trial/activated_focus",
                    "recommended_action": "跟进正式课报名",
                    "signals": ["recent_reply", "high_intent_tag"],
                },
                "contact": {
                    "external_userid": "wx_ext_001",
                    "name": "张小蓝",
                    "remark": "小蓝",
                    "description": "9.9 试用后关注正式课安排",
                },
                "sidebar_context": {
                    "can_open_sidebar": True,
                    "marketing_stage": "activated_focus",
                    "customer_profile_url": "/admin/customers/wx_ext_001",
                },
            },
            {
                "person_id": "person_002",
                "external_userid": "wx_ext_002",
                "customer_name": "李未绑",
                "remark": "未绑手机号客户",
                "description": "已加微但尚未绑定手机号",
                "owner_userid": "LiuXiao",
                "owner_display_name": "刘晓",
                "mobile": None,
                "tags": ["新用户"],
                "class_user_status": {
                    "current_status": "new_user",
                    "signup_status": "",
                    "signup_label_name": "",
                    "activation_bucket": "pending_input",
                    "updated_at": "2026-05-17T18:05:00+08:00",
                },
                "last_message_at": "2026-05-17T18:00:00+08:00",
                "last_touch_at": "2026-05-17T18:05:00+08:00",
                "updated_at": "2026-05-17T18:05:00+08:00",
                "binding": {"is_bound": False, "mobile": None, "binding_status": "unbound"},
                "identity": {"person_id": "person_002", "external_userid": "wx_ext_002", "mobile": None},
                "follow_users": [{"userid": "LiuXiao", "display_name": "刘晓", "is_primary": True}],
                "marketing_summary": {"main_stage": "new_user", "sub_stage": "pending_input", "value_segment": "unknown"},
                "marketing_profile": {
                    "stage_key": "new_user/pending_input",
                    "recommended_action": "补录手机号和激活状态",
                    "signals": ["missing_mobile"],
                },
                "contact": {
                    "external_userid": "wx_ext_002",
                    "name": "李未绑",
                    "remark": "未绑手机号客户",
                    "description": "已加微但尚未绑定手机号",
                },
                "sidebar_context": {
                    "can_open_sidebar": True,
                    "marketing_stage": "new_user",
                    "customer_profile_url": "/admin/customers/wx_ext_002",
                },
            },
            {
                "person_id": "person_003",
                "external_userid": "",
                "customer_name": "王缺失",
                "remark": "缺外部联系人",
                "description": "导入线索，尚未形成 external_userid",
                "owner_userid": "",
                "owner_display_name": "",
                "mobile": "13900139000",
                "tags": ["导入线索"],
                "class_user_status": {
                    "current_status": "lead_imported",
                    "signup_status": "",
                    "signup_label_name": "导入线索",
                    "activation_bucket": "not_activated",
                    "updated_at": "2026-05-16T12:00:00+08:00",
                },
                "last_message_at": None,
                "last_touch_at": None,
                "updated_at": "2026-05-16T12:00:00+08:00",
                "binding": {"is_bound": True, "mobile": "13900139000", "binding_status": "bound_no_external_userid"},
                "identity": {"person_id": "person_003", "external_userid": "", "mobile": "13900139000"},
                "follow_users": [],
                "marketing_summary": {"main_stage": "lead", "sub_stage": "imported", "value_segment": "unknown"},
                "marketing_profile": {"stage_key": "lead/imported", "recommended_action": "等待加微", "signals": []},
                "contact": {"external_userid": "", "name": "王缺失", "remark": "缺外部联系人", "description": "导入线索"},
                "sidebar_context": {"can_open_sidebar": False, "marketing_stage": "lead_imported"},
            },
            {
                "person_id": "person_004",
                "external_userid": "wx_ext_004",
                "customer_name": "陈复访",
                "remark": "复访客户",
                "description": "黄小璨未激活，需要再次触达",
                "owner_userid": "ZhaoYanFang",
                "owner_display_name": "赵艳芳",
                "mobile": "13700137000",
                "tags": ["黄小璨", "复访"],
                "class_user_status": {
                    "current_status": "followup",
                    "signup_status": "",
                    "signup_label_name": "复访",
                    "activation_bucket": "not_activated",
                    "updated_at": "2026-05-15T11:30:00+08:00",
                },
                "last_message_at": "2026-05-15T11:10:00+08:00",
                "last_touch_at": "2026-05-15T11:30:00+08:00",
                "updated_at": "2026-05-15T11:30:00+08:00",
                "binding": {"is_bound": True, "mobile": "13700137000", "binding_status": "bound"},
                "identity": {"person_id": "person_004", "external_userid": "wx_ext_004", "mobile": "13700137000"},
                "follow_users": [{"userid": "ZhaoYanFang", "display_name": "赵艳芳", "is_primary": True}],
                "marketing_summary": {"main_stage": "followup", "sub_stage": "not_activated", "value_segment": "medium"},
                "marketing_profile": {
                    "stage_key": "followup/not_activated",
                    "recommended_action": "发送激活提醒",
                    "signals": ["not_activated"],
                },
                "contact": {
                    "external_userid": "wx_ext_004",
                    "name": "陈复访",
                    "remark": "复访客户",
                    "description": "黄小璨未激活，需要再次触达",
                },
                "sidebar_context": {
                    "can_open_sidebar": True,
                    "marketing_stage": "followup",
                    "customer_profile_url": "/admin/customers/wx_ext_004",
                },
            },
            {
                "person_id": "person_masked_001",
                "external_userid": "external_user_masked_001",
                "customer_name": "customer_masked_001",
                "remark": "remark_masked_001",
                "description": "description_masked_001",
                "owner_userid": "owner_masked_001",
                "owner_display_name": "owner_masked_display_001",
                "mobile": "mobile_masked_001",
                "tags": [],
                "class_user_status": {
                    "current_status": "activated",
                    "signup_status": "activated",
                    "signup_label_name": "tag_masked_001",
                    "activation_bucket": "activated",
                    "updated_at": "2026-05-20T08:43:12+00:00",
                    "wecom_tag_sync_status": "skipped_fake_seed",
                    "wecom_tag_sync_error": "",
                },
                "last_message_at": "2026-05-20T08:43:12+00:00",
                "last_touch_at": "2026-05-20T08:43:12+00:00",
                "updated_at": "2026-05-20T08:43:12+00:00",
                "binding": {
                    "is_bound": True,
                    "person_id": 1,
                    "mobile": "mobile_masked_001",
                    "binding_status": "bound",
                    "third_party_user_id": "third_party_user_masked_001",
                },
                "identity": {
                    "person_id": 1,
                    "external_userid": "external_user_masked_001",
                    "mobile": "mobile_masked_001",
                    "unionid": "unionid_masked_001",
                    "openid": "openid_masked_001",
                    "status": "active",
                },
                "follow_users": [{"userid": "owner_masked_001", "display_name": "owner_masked_display_001", "is_primary": True}],
                "marketing_summary": {"main_stage": "activated", "sub_stage": "masked_sample", "value_segment": "fixture"},
                "marketing_profile": {
                    "stage_key": "activated/masked_sample",
                    "recommended_action": "masked sample only",
                    "signals": ["masked_sample"],
                },
                "contact": {
                    "external_userid": "external_user_masked_001",
                    "name": "customer_masked_001",
                    "remark": "remark_masked_001",
                    "description": "description_masked_001",
                },
                "sidebar_context": {
                    "can_open_sidebar": True,
                    "marketing_stage": "activated",
                    "customer_profile_url": "/admin/customers/external_user_masked_001",
                },
            },
        ]
        self._timeline: dict[str, list[JsonDict]] = {
            "wx_ext_001": [
                {
                    "event_id": "evt_001",
                    "event_type": "message",
                    "event_time": "2026-05-18T10:15:00+08:00",
                    "title": "客户发送新消息",
                    "summary": "想了解 9.9 试用后的正式课安排。",
                    "source_table": "archive_messages",
                    "source_id": "msg_001",
                    "metadata": {"msgtype": "text", "owner_userid": "ZhaoYanFang"},
                },
                {
                    "event_id": "evt_002",
                    "event_type": "tag",
                    "event_time": "2026-05-18T10:20:00+08:00",
                    "title": "标签更新",
                    "summary": "新增重点跟进标签。",
                    "source_table": "contact_tags",
                    "source_id": "tag_evt_001",
                    "metadata": {"tags": ["重点跟进"]},
                },
            ],
            "wx_ext_002": [
                {
                    "event_id": "evt_003",
                    "event_type": "contact_added",
                    "event_time": "2026-05-17T18:00:00+08:00",
                    "title": "客户已加微",
                    "summary": "客户进入新用户池，尚未绑定手机号。",
                    "source_table": "contacts",
                    "source_id": "wx_ext_002",
                    "metadata": {"binding_status": "unbound"},
                }
            ],
            "wx_ext_004": [
                {
                    "event_id": "evt_004",
                    "event_type": "message",
                    "event_time": "2026-05-15T11:10:00+08:00",
                    "title": "客户回复复访消息",
                    "summary": "客户询问激活入口是否还有效。",
                    "source_table": "archive_messages",
                    "source_id": "msg_004",
                    "metadata": {"msgtype": "text", "owner_userid": "ZhaoYanFang"},
                }
            ],
            "external_user_masked_001": [
                {
                    "event_id": "message:masked_001",
                    "event_type": "message",
                    "event_time": "2026-05-20T08:43:12+00:00",
                    "title": "消息 · text",
                    "summary": "masked message content 001",
                    "source_table": "archived_messages",
                    "source_id": "msg_masked_001",
                    "metadata": {"msgtype": "text", "owner_userid": "owner_masked_001"},
                },
                {
                    "event_id": "status_change:masked_001",
                    "event_type": "status_change",
                    "event_time": "2026-05-20T08:43:12+00:00",
                    "title": "状态变更",
                    "summary": "- -> activated",
                    "source_table": "class_user_status_history",
                    "source_id": "status_masked_001",
                    "metadata": {"signup_label_name": "tag_masked_001"},
                },
            ],
        }
        self._messages: dict[str, list[JsonDict]] = {
            "wx_ext_001": [
                {
                    "msgid": "msg_001",
                    "msgtype": "text",
                    "content": "我想了解正式课怎么报名",
                    "send_time": "2026-05-18T10:15:00+08:00",
                    "external_userid": "wx_ext_001",
                    "chat_type": "single",
                    "owner_userid": "ZhaoYanFang",
                    "sender": "customer",
                },
                {
                    "msgid": "msg_002",
                    "msgtype": "text",
                    "content": "老师什么时候方便介绍一下",
                    "send_time": "2026-05-18T10:10:00+08:00",
                    "external_userid": "wx_ext_001",
                    "chat_type": "single",
                    "owner_userid": "ZhaoYanFang",
                    "sender": "customer",
                }
            ],
            "wx_ext_002": [],
            "wx_ext_004": [
                {
                    "msgid": "msg_004",
                    "msgtype": "text",
                    "content": "激活入口还有效吗",
                    "send_time": "2026-05-15T11:10:00+08:00",
                    "external_userid": "wx_ext_004",
                    "chat_type": "single",
                    "owner_userid": "ZhaoYanFang",
                    "sender": "customer",
                }
            ],
            "external_user_masked_001": [
                {
                    "msgid": "msg_masked_001",
                    "msgtype": "text",
                    "content": "masked message content 001",
                    "send_time": "2026-05-20T08:43:12+00:00",
                    "external_userid": "external_user_masked_001",
                    "chat_type": "single",
                    "owner_userid": "owner_masked_001",
                    "sender": "customer",
                }
            ],
        }

    def list_customers(
        self,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        rows = _apply_customer_filters([deepcopy(item) for item in self._customers], filters or {})
        return _apply_page(rows, limit=limit, offset=offset)

    def get_customer(self, external_userid: str) -> JsonDict | None:
        item = next((item for item in self._customers if item.get("external_userid") == external_userid), None)
        return deepcopy(item) if item else None

    get_customer_detail = get_customer

    def list_timeline(
        self,
        external_userid: str,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        rows = [deepcopy(item) for item in self._timeline.get(external_userid, [])]
        event_type = str((filters or {}).get("event_type") or "").strip()
        if event_type:
            rows = [item for item in rows if item.get("event_type") == event_type]
        return _apply_page(rows, limit=limit, offset=offset)

    get_customer_timeline = list_timeline

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]:
        return _apply_page([deepcopy(item) for item in self._messages.get(external_userid, [])], limit=limit, offset=0)

    get_recent_messages = list_recent_messages

    def customer_exists(self, external_userid: str) -> bool:
        return self.get_customer(external_userid) is not None


class SqlAlchemyCustomerReadModelRepository:
    """PostgreSQL-ready Customer Read Model repository backed by SQLAlchemy Core tables."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def reset(self) -> None:
        self._session.execute(delete(customer_recent_message_next))
        self._session.execute(delete(customer_timeline_event_next))
        self._session.execute(delete(customer_detail_snapshot_next))
        self._session.execute(delete(customer_list_index_next))
        self.seed_from_fixture()
        self._session.commit()

    def seed_from_fixture(self, fixture: FixtureCustomerReadRepository | None = None) -> None:
        fixture = fixture or FixtureCustomerReadRepository()
        self.seed(
            customers=fixture.list_customers(),
            timeline_by_external_userid={row["external_userid"]: fixture.list_timeline(row["external_userid"]) for row in fixture.list_customers() if row.get("external_userid")},
            messages_by_external_userid={row["external_userid"]: fixture.list_recent_messages(row["external_userid"]) for row in fixture.list_customers() if row.get("external_userid")},
        )

    def seed(
        self,
        *,
        customers: list[JsonDict],
        timeline_by_external_userid: dict[str, list[JsonDict]] | None = None,
        messages_by_external_userid: dict[str, list[JsonDict]] | None = None,
    ) -> None:
        timeline_by_external_userid = timeline_by_external_userid or {}
        messages_by_external_userid = messages_by_external_userid or {}
        for index, customer in enumerate(customers, start=1):
            external_userid = str(customer.get("external_userid") or "")
            created_at = _coerce_datetime(customer.get("created_at") or customer.get("updated_at"))
            updated_at = _coerce_datetime(customer.get("updated_at"))
            binding = dict(customer.get("binding") or {})
            self._session.execute(
                insert(customer_list_index_next).values(
                    id=index,
                    person_id=customer.get("person_id") or "",
                    external_userid=external_userid,
                    customer_name=customer.get("customer_name") or "",
                    owner_userid=customer.get("owner_userid") or "",
                    owner_display_name=customer.get("owner_display_name") or "",
                    remark=customer.get("remark") or "",
                    description=customer.get("description") or "",
                    mobile=customer.get("mobile") or "",
                    is_bound=bool(binding.get("is_bound")),
                    binding_status=binding.get("binding_status") or customer.get("binding_status") or "unbound",
                    tags_json=list(customer.get("tags") or []),
                    class_user_status_json=dict(customer.get("class_user_status") or {}),
                    last_message_at=_coerce_optional_datetime(customer.get("last_message_at")),
                    last_touch_at=_coerce_optional_datetime(customer.get("last_touch_at")),
                    updated_at=updated_at,
                    created_at=created_at,
                )
            )
            self._session.execute(
                insert(customer_detail_snapshot_next).values(
                    id=index,
                    person_id=customer.get("person_id") or "",
                    external_userid=external_userid,
                    customer_json=dict(customer),
                    binding_json=dict(customer.get("binding") or {}),
                    identity_json=dict(customer.get("identity") or {}),
                    follow_users_json=list(customer.get("follow_users") or []),
                    marketing_summary_json=dict(customer.get("marketing_summary") or {}),
                    marketing_profile_json=dict(customer.get("marketing_profile") or {}),
                    contact_json=dict(customer.get("contact") or {}),
                    sidebar_context_json=dict(customer.get("sidebar_context") or {}),
                    updated_at=updated_at,
                    created_at=created_at,
                )
            )
            for event_index, item in enumerate(timeline_by_external_userid.get(external_userid, []), start=1):
                self._session.execute(
                    insert(customer_timeline_event_next).values(
                        id=index * 1000 + event_index,
                        event_id=item.get("event_id") or f"evt_{index}_{event_index}",
                        person_id=customer.get("person_id") or "",
                        external_userid=external_userid,
                        event_type=item.get("event_type") or "",
                        event_time=_coerce_datetime(item.get("event_time")),
                        title=item.get("title") or "",
                        summary=item.get("summary") or "",
                        source_table=item.get("source_table") or "",
                        source_id=item.get("source_id") or "",
                        metadata_json=dict(item.get("metadata") or {}),
                        created_at=created_at,
                    )
                )
            for message_index, item in enumerate(messages_by_external_userid.get(external_userid, []), start=1):
                metadata = {key: value for key, value in item.items() if key not in {"msgid", "external_userid", "msgtype", "content", "send_time", "owner_userid", "chat_type"}}
                self._session.execute(
                    insert(customer_recent_message_next).values(
                        id=index * 1000 + message_index,
                        msgid=item.get("msgid") or f"msg_{index}_{message_index}",
                        external_userid=external_userid,
                        msgtype=item.get("msgtype") or "text",
                        content=item.get("content") or "",
                        send_time=_coerce_datetime(item.get("send_time")),
                        owner_userid=item.get("owner_userid") or "",
                        chat_type=item.get("chat_type") or "single",
                        metadata_json=metadata,
                        created_at=created_at,
                    )
                )

    def list_customers(
        self,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        rows = self._session.execute(
            select(customer_list_index_next).order_by(customer_list_index_next.c.id.asc())
        ).mappings()
        customers = [self._list_row_to_customer(row) for row in rows]
        return _apply_page(_apply_customer_filters(customers, filters or {}), limit=limit, offset=offset)

    def get_customer(self, external_userid: str) -> JsonDict | None:
        row = self._session.execute(
            select(customer_detail_snapshot_next)
            .where(customer_detail_snapshot_next.c.external_userid == external_userid)
            .limit(1)
        ).mappings().first()
        if not row:
            return None
        customer = dict(row["customer_json"] or {})
        customer.update(
            {
                "binding": dict(row["binding_json"] or {}),
                "identity": dict(row["identity_json"] or {}),
                "follow_users": list(row["follow_users_json"] or []),
                "marketing_summary": dict(row["marketing_summary_json"] or {}),
                "marketing_profile": dict(row["marketing_profile_json"] or {}),
                "contact": dict(row["contact_json"] or {}),
                "sidebar_context": dict(row["sidebar_context_json"] or {}),
                "updated_at": _iso(customer.get("updated_at") or row["updated_at"]),
            }
        )
        return customer

    get_customer_detail = get_customer

    def list_timeline(
        self,
        external_userid: str,
        filters: JsonDict | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JsonDict]:
        stmt = select(customer_timeline_event_next).where(customer_timeline_event_next.c.external_userid == external_userid)
        event_type = str((filters or {}).get("event_type") or "").strip()
        if event_type:
            stmt = stmt.where(customer_timeline_event_next.c.event_type == event_type)
        stmt = stmt.order_by(customer_timeline_event_next.c.id.asc())
        rows = [self._timeline_row_to_dict(row) for row in self._session.execute(stmt).mappings()]
        return _apply_page(rows, limit=limit, offset=offset)

    get_customer_timeline = list_timeline

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]:
        stmt = (
            select(customer_recent_message_next)
            .where(customer_recent_message_next.c.external_userid == external_userid)
            .order_by(customer_recent_message_next.c.send_time.desc(), customer_recent_message_next.c.id.asc())
        )
        rows = [self._message_row_to_dict(row) for row in self._session.execute(stmt).mappings()]
        return _apply_page(rows, limit=limit, offset=0)

    get_recent_messages = list_recent_messages

    def customer_exists(self, external_userid: str) -> bool:
        return self.get_customer(external_userid) is not None

    def _list_row_to_customer(self, row) -> JsonDict:
        data = dict(row)
        return {
            "person_id": data.get("person_id") or "",
            "external_userid": data.get("external_userid") or "",
            "customer_name": data.get("customer_name") or "",
            "remark": data.get("remark") or "",
            "description": data.get("description") or "",
            "owner_userid": data.get("owner_userid") or "",
            "owner_display_name": data.get("owner_display_name") or "",
            "mobile": data.get("mobile") or None,
            "tags": list(data.get("tags_json") or []),
            "class_user_status": dict(data.get("class_user_status_json") or {}),
            "last_message_at": _iso(data.get("last_message_at")),
            "last_touch_at": _iso(data.get("last_touch_at")),
            "updated_at": _iso(data.get("updated_at")),
            "created_at": _iso(data.get("created_at")),
            "binding": {
                "is_bound": bool(data.get("is_bound")),
                "mobile": data.get("mobile") or None,
                "binding_status": data.get("binding_status") or "unbound",
            },
        }

    def _timeline_row_to_dict(self, row) -> JsonDict:
        data = dict(row)
        return {
            "event_id": data.get("event_id") or "",
            "event_type": data.get("event_type") or "",
            "event_time": _iso(data.get("event_time")),
            "title": data.get("title") or "",
            "summary": data.get("summary") or "",
            "source_table": data.get("source_table") or "",
            "source_id": data.get("source_id") or "",
            "metadata": dict(data.get("metadata_json") or {}),
        }

    def _message_row_to_dict(self, row) -> JsonDict:
        data = dict(row)
        payload = {
            "msgid": data.get("msgid") or "",
            "msgtype": data.get("msgtype") or "text",
            "content": data.get("content") or "",
            "send_time": _iso(data.get("send_time")),
            "external_userid": data.get("external_userid") or "",
            "owner_userid": data.get("owner_userid") or "",
            "chat_type": data.get("chat_type") or "single",
        }
        payload.update(dict(data.get("metadata_json") or {}))
        return payload


def _apply_customer_filters(rows: list[JsonDict], filters: JsonDict) -> list[JsonDict]:
    owner_userid = str(filters.get("owner_userid") or "").strip()
    tag = str(filters.get("tag") or "").strip()
    status = str(filters.get("status") or "").strip()
    mobile = str(filters.get("mobile") or "").strip()
    keyword = str(filters.get("keyword") or "").strip()
    is_bound = _normalize_bool_filter(filters.get("is_bound"))
    if owner_userid:
        rows = [item for item in rows if item.get("owner_userid") == owner_userid]
    if tag:
        rows = [item for item in rows if tag in item.get("tags", [])]
    if status:
        rows = [
            item
            for item in rows
            if status
            in {
                str(item.get("class_user_status", {}).get("current_status") or ""),
                str(item.get("class_user_status", {}).get("signup_status") or ""),
                str(item.get("class_user_status", {}).get("activation_bucket") or ""),
                str(item.get("binding", {}).get("binding_status") or ""),
                str(item.get("binding_status") or ""),
            }
        ]
    if is_bound is not None:
        rows = [item for item in rows if bool(item.get("binding", {}).get("is_bound", item.get("is_bound"))) is is_bound]
    if mobile:
        rows = [item for item in rows if mobile in str(item.get("mobile") or "")]
    if keyword:
        rows = [
            item
            for item in rows
            if keyword in str(item.get("customer_name") or "")
            or keyword in str(item.get("external_userid") or "")
            or keyword in str(item.get("mobile") or "")
            or keyword in str(item.get("owner_userid") or "")
            or keyword in str(item.get("owner_display_name") or "")
        ]
    return rows


def _apply_page(rows: list[JsonDict], *, limit: int | None, offset: int = 0) -> list[JsonDict]:
    if limit is None:
        return rows[offset:] if offset else rows
    return rows[offset : offset + limit]


def _normalize_bool_filter(value: object) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "all"}:
        return None
    if normalized in {"1", "true", "yes", "y", "on", "bound"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", "unbound"}:
        return False
    return None


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        return datetime.fromisoformat(str(value))
    return datetime.now(timezone.utc)


def _coerce_optional_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    return _coerce_datetime(value)


def _iso(value: object) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def build_customer_read_model_repository(
    settings: Settings | None = None,
    *,
    session: Session | None = None,
    engine: Engine | None = None,
) -> CustomerReadRepository:
    settings = settings or get_settings()
    backend = os.getenv("CUSTOMER_READ_MODEL_REPO_BACKEND", settings.customer_read_model_repo_backend).strip().lower()
    if backend in {"sql", "sqlalchemy", "postgres", "postgresql"}:
        if session is not None:
            return SqlAlchemyCustomerReadModelRepository(session)
        engine = engine or create_engine(settings.database_url, future=True)
        session_factory = sessionmaker(bind=engine, future=True)
        return SqlAlchemyCustomerReadModelRepository(session_factory())
    return InMemoryCustomerReadModelRepository()


InMemoryCustomerReadModelRepository = FixtureCustomerReadRepository
