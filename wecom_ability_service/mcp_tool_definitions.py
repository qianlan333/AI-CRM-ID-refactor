from __future__ import annotations

TOOL_DEFS = [
    {
        "name": "resolve_customer",
        "description": "Resolve customer_ref (mobile or external_userid) to a CRM customer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "include_context": {"type": "boolean"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "timeline_limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "get_contact",
        "description": "Read a single contact by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "refresh_tags": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_customer_context",
        "description": "Read a customer's aggregated CRM context by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "refresh_tags": {"type": "boolean"},
                "recent_message_limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "timeline_limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "get_messages",
        "description": "Read full message history for a contact by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "chat_type": {"type": "string", "enum": ["private", "group"]},
            },
        },
    },
    {
        "name": "get_recent_messages",
        "description": "Read recent messages for a contact by customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "chat_type": {"type": "string", "enum": ["private", "group"]},
            },
        },
    },
    {
        "name": "search_messages",
        "description": "Search messages for a contact by keyword, using customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "keyword": {"type": "string"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_group_chat",
        "description": "Read a group chat by chat_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
            },
            "required": ["chat_id"],
        },
    },
    {
        "name": "mark_tags",
        "description": "Add one or more tags to a contact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "userid": {"type": "string"},
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "add_tag": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["userid", "add_tag"],
        },
    },
    {
        "name": "unmark_tags",
        "description": "Remove one or more tags from a contact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "userid": {"type": "string"},
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "remove_tag": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["userid", "remove_tag"],
        },
    },
    {
        "name": "update_customer_tags",
        "description": "Update a customer's tags with customer_ref or external_userid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "userid": {"type": "string"},
                "add_tags": {"type": "array", "items": {"type": "string"}},
                "remove_tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "create_private_message_task",
        "description": "Create a private message task using a simple business input or raw WeCom payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "content": {"type": "string"},
                "userid": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "confirm": {"type": "boolean"},
            },
        },
    },
    {
        "name": "create_moment_task",
        "description": "Create a moment task using customer_ref/customer_refs or raw WeCom payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "customer_refs": {"type": "array", "items": {"type": "string"}},
                "external_userid": {"type": "string"},
                "external_userids": {"type": "array", "items": {"type": "string"}},
                "content": {"type": "string"},
                "userid": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "confirm": {"type": "boolean"},
            },
        },
    },
    {
        "name": "create_group_message_task",
        "description": "Create a group message task using customer_ref/customer_refs or raw WeCom payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "customer_refs": {"type": "array", "items": {"type": "string"}},
                "external_userid": {"type": "string"},
                "external_userids": {"type": "array", "items": {"type": "string"}},
                "content": {"type": "string"},
                "userid": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "confirm": {"type": "boolean"},
            },
        },
    },
    {
        "name": "record_conversion_feedback",
        "description": "Persist conversion feedback from OpenClaw without applying sales logic.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feedback_type": {"type": "string"},
                "customer_ref": {"type": "string"},
                "external_userid": {"type": "string"},
                "chat_id": {"type": "string"},
                "actor": {"type": "string"},
                "feedback_payload": {"type": "object"},
            },
            "required": ["feedback_type"],
        },
    },
    {
        "name": "get_owner_role_map",
        "description": "Read the owner role mapping used for routing validation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "active_only": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_signup_tag_rules",
        "description": "Read signup tag rules used for pre/post-signup routing validation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "active_only": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_routing_config",
        "description": "Read both owner role map and signup tag rules in one call.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_pending_message_batches",
        "description": "List pending 3-minute message batches for OpenClaw to judge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "cursor": {"type": "string"},
            },
        },
    },
    {
        "name": "get_message_batch",
        "description": "Fetch a batch with full message payloads.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                "cursor": {"type": "string"},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "ack_message_batch",
        "description": "Acknowledge a batch after OpenClaw has consumed it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "ack_note": {"type": "string"},
                "acked_by": {"type": "string"},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "get_owner_recent_chat_dump",
        "description": "Read recent private/group archived chat dumps for one owner without ranking or recommendations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner_userid": {"type": "string"},
                "lookback_minutes": {"type": "integer", "minimum": 1, "maximum": 1440},
                "include_private": {"type": "boolean"},
                "include_group": {"type": "boolean"},
            },
            "required": ["owner_userid"],
        },
    },
    {
        "name": "get_hourly_followup_candidates",
        "description": "List the best customers to follow up with right now using simple CRM rules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "lookback_hours": {"type": "integer", "minimum": 1, "maximum": 168},
            },
        },
    },
]
