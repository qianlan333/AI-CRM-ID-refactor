"""image_library 模板 contract 测试。

不起 Flask app，直接 grep 模板源码，确保前端筛选栏 / 编辑模态框 / 上传
表单的新字段不被无意撤回。同 ``test_admin_static_contract.py`` 风格。
"""
from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "wecom_ability_service" / "templates" / "admin_console" / "image_library.html"


@pytest.fixture(scope="module")
def source() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


# ---------- 上传表单包含新字段 ---------- #

def test_upload_form_has_description_field(source: str):
    assert 'id="il-form-description"' in source
    assert "description" in source.lower()


def test_upload_form_has_tags_field(source: str):
    assert 'id="il-form-tags"' in source
    # form data 必须把 tags 提交到后端
    assert "fd.append('tags'" in source


def test_upload_form_has_category_field(source: str):
    assert 'id="il-form-category"' in source
    # 用 datalist 自动补全已有分类
    assert 'id="il-form-category-options"' in source
    assert "<datalist" in source


def test_upload_form_keeps_existing_upload_and_url_tabs(source: str):
    """老的上传文件 + 外链 URL 两个 tab 必须保留。"""
    assert 'data-tab="upload"' in source
    assert 'data-tab="url"' in source
    assert 'id="il-upload-file"' in source
    assert 'id="il-url-input"' in source


def test_upload_submit_passes_metadata_in_multipart(source: str):
    """multipart 上传必须把 description / tags / category 一起 append。"""
    assert "fd.append('description'" in source
    assert "fd.append('category'" in source


def test_url_create_passes_metadata_in_json_body(source: str):
    """from-url 走 JSON body，body 必须含新字段。"""
    assert "/api/admin/image-library/from-url" in source
    assert "description: fields.description" in source
    assert "category: fields.category" in source


# ---------- 筛选栏 ---------- #

def test_filter_bar_has_keyword_search(source: str):
    assert 'id="il-q"' in source
    assert 'type="search"' in source


def test_filter_bar_has_category_dropdown(source: str):
    assert 'id="il-category-filter"' in source


def test_filter_bar_has_only_unlabeled_checkbox(source: str):
    assert 'id="il-only-unlabeled"' in source


def test_filter_bar_has_tag_pool(source: str):
    assert 'id="il-tag-pool"' in source


def test_filter_bar_has_reset_button(source: str):
    assert 'id="il-reset"' in source


# ---------- 网格卡片 ---------- #

def test_card_renders_tags_and_category_chips(source: str):
    assert '<span class="tag">' in source or "class=\"tag\"" in source
    assert '<span class="cat">' in source or "class=\"cat\"" in source


def test_card_marks_unlabeled_records(source: str):
    assert "未打标" in source


def test_card_has_edit_button(source: str):
    assert 'data-action="edit"' in source


def test_card_keeps_legacy_actions_toggle_and_delete(source: str):
    """启用 / 停用 / 删除按钮的能力不能丢，旧调用方依赖。"""
    assert 'data-action="toggle"' in source
    assert 'data-action="delete"' in source


# ---------- 编辑模态框 ---------- #

def test_edit_modal_present(source: str):
    assert 'id="il-edit-modal"' in source
    assert 'id="il-edit-name"' in source
    assert 'id="il-edit-description"' in source
    assert 'id="il-edit-tags"' in source
    assert 'id="il-edit-category"' in source


def test_edit_modal_save_calls_put_endpoint_with_metadata(source: str):
    assert "/api/admin/image-library/" in source
    assert "method: 'PUT'" in source
    # 保存时必须把 4 个字段都打包
    assert "description: document.getElementById('il-edit-description').value" in source
    assert "tags: tagsArr" in source
    assert "category: document.getElementById('il-edit-category').value" in source


def test_edit_modal_clickaway_closes(source: str):
    """点击模态框 backdrop 自身关闭。"""
    assert "il-edit-modal" in source
    assert "closeEditModal" in source


# ---------- API 调用 ---------- #

def test_list_request_supports_filter_query_params(source: str):
    """列表请求必须能传 q / tags / category / only_unlabeled，否则筛选失效。"""
    assert "params.set('q'" in source
    assert "params.set('tags'" in source
    assert "params.set('category'" in source
    assert "params.set('only_unlabeled'" in source


def test_facets_endpoint_called_on_load(source: str):
    assert "/api/admin/image-library/facets" in source


def test_include_disabled_passes_enabled_only_false(source: str):
    """筛选「含已停用」时必须把 enabled_only=false 传给后端。"""
    assert "enabled_only" in source
    assert "'false'" in source or '"false"' in source


# ---------- 不能误删的老路径 ---------- #

def test_thumbnail_loader_handles_url_and_base64_sources(source: str):
    """缩略图加载逻辑保留：source=url 直链，否则拉 base64 详情。"""
    assert "data_base64" in source
    assert "source === 'url'" in source
    assert "data:" in source  # data url


def test_extends_admin_console_base(source: str):
    """模板必须继承 admin_console/base.html，跟整个后台 shell 一致。"""
    assert '{% extends "admin_console/base.html" %}' in source
