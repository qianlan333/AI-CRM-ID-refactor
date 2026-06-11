from __future__ import annotations

from aicrm_next.integration_gateway.wecom_private_adapter import WeComPrivateMessageAdapter


def test_private_adapter_normalizes_miniprogram_attachment_aliases() -> None:
    adapter = WeComPrivateMessageAdapter(mode="fake")

    payload = adapter._build_wecom_payload(
        {
            "sender": "HuangYouCan",
            "external_userids": ["wm_test"],
            "attachments": [
                {
                    "msgtype": "miniprogram",
                    "miniprogram": {
                        "appid": "wx_app_001",
                        "pagepath": "pages/article/article?lesson_id=abc",
                        "title": "Mini Card",
                        "thumb_media_id": "media_thumb_001",
                    },
                }
            ],
        }
    )

    assert payload["attachments"] == [
        {
            "msgtype": "miniprogram",
            "miniprogram": {
                "appid": "wx_app_001",
                "page": "pages/article/article?lesson_id=abc",
                "title": "Mini Card",
                "pic_media_id": "media_thumb_001",
            },
        }
    ]
