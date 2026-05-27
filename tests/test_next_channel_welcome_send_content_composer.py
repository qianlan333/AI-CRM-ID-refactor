from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "aicrm_next" / "frontend_compat" / "templates" / "admin_console" / "channel_code_form.html"
CHANNEL_JS = ROOT / "aicrm_next" / "frontend_compat" / "static" / "admin_console" / "channel_admission_pages.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_channel_form_uses_standard_send_content_composer_assets() -> None:
    html = _read(TEMPLATE)
    js = _read(CHANNEL_JS)

    assert "send_content_composer.js" in html
    assert "send_content_composer.css" in html
    assert "material_picker.js" in html
    assert "material_picker.css" in html
    assert "配置欢迎语和素材" in html
    assert "data-open-welcome-composer" in html
    assert "AICRMSendContentComposer.open" in js
    assert 'title: "配置欢迎语和素材"' in js
    assert "标准发送内容组件加载失败" in js


def test_channel_form_no_longer_uses_private_welcome_material_picker() -> None:
    combined = _read(TEMPLATE) + "\n" + _read(CHANNEL_JS)

    forbidden = [
        "/api/admin/channel-" + "welcome-materials",
        "/api/admin/image-" + "library",
        "/api/admin/miniprogram-" + "library",
        "/api/admin/attachment-" + "library",
        "data-open-" + "miniprogram-picker",
        "data-open-" + "attachment-picker",
        "data-miniprogram-" + "selected",
        "data-attachment-" + "selected",
        "预览并选择" + "小程序",
        "预览并选择" + "图片/PDF",
    ]
    for marker in forbidden:
        assert marker not in combined


def test_channel_welcome_adapter_round_trips_standard_content_package() -> None:
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({json.dumps(str(CHANNEL_JS))}, "utf8");
const sandbox = {{
  window: {{}},
  document: {{ querySelector() {{ return null; }} }}
}};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const adapter = sandbox.window.AICRMChannelWelcomeAdapter;
const contentPackage = adapter.welcomeFieldsToContentPackage({{
  welcome_message: "  欢迎加入  ",
  welcome_image_library_ids: [12, "12", 34],
  welcome_miniprogram_library_ids: ["56"],
  welcome_attachment_library_ids: "78, 78, 90"
}});
const fields = adapter.contentPackageToWelcomeFields({{
  content_text: "  新欢迎语  ",
  image_library_ids: ["101", 102],
  miniprogram_library_ids: [201],
  attachment_library_ids: ["301", "301", 302]
}});
const empty = adapter.welcomeFieldsToContentPackage({{}});
console.log(JSON.stringify({{ contentPackage, fields, empty }}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)

    assert payload["contentPackage"] == {
        "content_text": "欢迎加入",
        "image_library_ids": [12, 34],
        "miniprogram_library_ids": [56],
        "attachment_library_ids": [78, 90],
    }
    assert payload["fields"] == {
        "welcome_message": "新欢迎语",
        "welcome_image_library_ids": [101, 102],
        "welcome_miniprogram_library_ids": [201],
        "welcome_attachment_library_ids": [301, 302],
    }
    assert payload["empty"] == {
        "content_text": "",
        "image_library_ids": [],
        "miniprogram_library_ids": [],
        "attachment_library_ids": [],
    }
