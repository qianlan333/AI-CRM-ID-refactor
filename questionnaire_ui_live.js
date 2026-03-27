
    const listEl = document.getElementById('questionnaire-list');
    const formEl = document.getElementById('editor-form');
    const questionsEl = document.getElementById('questions');
    const scoreRulesEl = document.getElementById('score-rules');
    const formMessageEl = document.getElementById('form-message');
    const tagCatalogMessageEl = document.getElementById('tag-catalog-message');
    const listMessageEl = document.getElementById('list-message');
    const preflightResultEl = document.getElementById('preflight-result');
    const latestSubmitResultEl = document.getElementById('latest-submit-result');
    const editorTitleEl = document.getElementById('editor-title');
    let availableTags = [];
    let availableTagMap = new Map();
    let currentId = null;

    function field(name) {
      return formEl.querySelector(`[name="${name}"]`);
    }

    function showMessage(el, message, isError = false) {
      el.textContent = message || '';
      el.className = message ? `message${isError ? ' error' : ''}` : 'message hidden';
      if (!message) el.classList.add('hidden');
    }

    function showDebugBox(el, message) {
      el.textContent = message || '';
      el.className = message ? 'debug-box' : 'debug-box hidden';
      if (!message) el.classList.add('hidden');
    }

    function escapeHtml(value) {
      return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function blankQuestion(type = 'single_choice') {
      return { type, title: '', required: false, sort_order: questionsEl.children.length + 1, options: type === 'textarea' ? [] : [{ option_text: '', score: 0, tag_codes: [], sort_order: 1 }] };
    }

    function blankRule() {
      return { min_score: '', max_score: '', tag_codes: [], sort_order: scoreRulesEl.children.length + 1 };
    }

    function normalizeTagIds(value) {
      if (Array.isArray(value)) return [...new Set(value.map((item) => String(item || '').trim()).filter(Boolean))];
      if (typeof value === 'string' && value.trim()) {
        try {
          const parsed = JSON.parse(value);
          if (Array.isArray(parsed)) return normalizeTagIds(parsed);
        } catch (error) {
          return [...new Set(value.split(',').map((item) => item.trim()).filter(Boolean))];
        }
      }
      return [];
    }

    function formatTagLabel(tag) {
      const groupName = tag.group_name || '未分组';
      return `${groupName} / ${tag.tag_name}`;
    }

    function buildUnknownTag(tagId) {
      return { tag_id: tagId, tag_name: `未知标签（${tagId}）`, group_name: '未知标签' };
    }

    function ensureTagKnown(tagId) {
      if (!availableTagMap.has(tagId)) return buildUnknownTag(tagId);
      return availableTagMap.get(tagId);
    }

    function parseManualTagInput(value) {
      if (!value.trim()) return [];
      try {
        const parsed = JSON.parse(value);
        if (!Array.isArray(parsed)) return [];
        return normalizeTagIds(parsed);
      } catch (error) {
        return normalizeTagIds(value);
      }
    }

    function createTagPicker(selectedTagIds = []) {
      const normalizedSelected = normalizeTagIds(selectedTagIds);
      const wrapper = document.createElement('div');
      wrapper.className = 'tag-picker';
      const select = document.createElement('select');
      select.multiple = true;
      select.dataset.field = 'tag_select';

      const knownSelected = new Set(normalizedSelected);
      const tagsForSelect = [...availableTags];
      normalizedSelected.forEach((tagId) => {
        if (!availableTagMap.has(tagId)) tagsForSelect.push(buildUnknownTag(tagId));
      });

      tagsForSelect.forEach((tag) => {
        const option = document.createElement('option');
        option.value = tag.tag_id;
        option.textContent = `${formatTagLabel(tag)} [${tag.tag_id}]`;
        option.selected = knownSelected.has(tag.tag_id);
        select.appendChild(option);
      });

      const summary = document.createElement('div');
      summary.className = 'tag-summary';
      const fallback = document.createElement('details');
      fallback.className = 'tag-fallback';
      fallback.innerHTML = `
        <summary>手工填写 tag_id 兜底</summary>
        <input data-field="tag_codes_manual" type="text" placeholder='例如 ["etxxx1","etxxx2"]'>
      `;
      const manualInput = fallback.querySelector('[data-field="tag_codes_manual"]');

      function updateSummary() {
        const selectIds = Array.from(select.selectedOptions).map((option) => option.value);
        const manualIds = parseManualTagInput(manualInput.value || '');
        const merged = normalizeTagIds([...selectIds, ...manualIds]);
        if (!merged.length) {
          summary.textContent = '未选择标签';
          return;
        }
        summary.textContent = merged.map((tagId) => {
          const tag = ensureTagKnown(tagId);
          return `${formatTagLabel(tag)} [${tagId}]`;
        }).join('\n');
      }

      select.addEventListener('change', updateSummary);
      manualInput.addEventListener('input', updateSummary);
      wrapper.appendChild(select);
      wrapper.appendChild(summary);
      wrapper.appendChild(fallback);
      updateSummary();
      return wrapper;
    }

    function collectTagIds(container) {
      const selectIds = Array.from(container.querySelectorAll('[data-field="tag_select"] option:checked')).map((option) => option.value);
      const manualValue = container.querySelector('[data-field="tag_codes_manual"]')?.value || '';
      return normalizeTagIds([...selectIds, ...parseManualTagInput(manualValue)]);
    }

    function resetForm(data = null) {
      currentId = data ? data.id : null;
      editorTitleEl.textContent = currentId ? `编辑问卷 #${currentId}` : '新建问卷';
      field('name').value = data?.name || '';
      field('title').value = data?.title || '';
      field('description').value = data?.description || '';
      field('redirect_url').value = data?.redirect_url || '';
      field('slug').value = data?.slug || '';
      field('is_disabled').checked = Boolean(data?.is_disabled);
      questionsEl.innerHTML = '';
      scoreRulesEl.innerHTML = '';
      (data?.questions || []).forEach(addQuestionCard);
      (data?.score_rules || []).forEach(addRuleCard);
      if (!questionsEl.children.length) addQuestionCard(blankQuestion('single_choice'));
      showMessage(formMessageEl, '');
    }

    function optionCard(option = {}) {
      const wrapper = document.createElement('div');
      wrapper.className = 'option-card';
      wrapper.innerHTML = `
        <div class="inline-row">
          <label style="flex:2;">option_text<input data-field="option_text" type="text" value="${escapeHtml(option.option_text || '')}"></label>
          <label style="flex:1;">score<input data-field="score" type="text" value="${escapeHtml(option.score ?? 0)}"></label>
          <label style="flex:1;">sort_order<input data-field="sort_order" type="text" value="${escapeHtml(option.sort_order ?? 1)}"></label>
        </div>
        <button type="button" class="danger remove-option">删除选项</button>
      `;
      wrapper.insertBefore(createTagPicker(option.tag_codes || []), wrapper.querySelector('.remove-option'));
      wrapper.querySelector('.remove-option').addEventListener('click', () => wrapper.remove());
      return wrapper;
    }

    function addQuestionCard(question = blankQuestion()) {
      const wrapper = document.createElement('div');
      wrapper.className = 'question-card';
      wrapper.innerHTML = `
        <div class="inline-row">
          <label style="flex:1;">type
            <select data-field="type">
              <option value="single_choice">single_choice</option>
              <option value="multi_choice">multi_choice</option>
              <option value="textarea">textarea</option>
            </select>
          </label>
          <label style="flex:3;">title<input data-field="title" type="text" value="${escapeHtml(question.title || '')}"></label>
          <label style="flex:1;">sort_order<input data-field="sort_order" type="text" value="${escapeHtml(question.sort_order ?? 1)}"></label>
          <label style="flex:1;"><input data-field="required" type="checkbox" ${question.required ? 'checked' : ''}> required</label>
        </div>
        <div class="options-wrap"></div>
        <div class="builder-actions">
          <button type="button" class="ghost add-option">添加选项</button>
          <button type="button" class="danger remove-question">删除题目</button>
        </div>
      `;
      wrapper.querySelector('[data-field="type"]').value = question.type || 'single_choice';
      const optionsWrap = wrapper.querySelector('.options-wrap');
      const renderOptions = () => {
        const type = wrapper.querySelector('[data-field="type"]').value;
        optionsWrap.innerHTML = '';
        const addBtn = wrapper.querySelector('.add-option');
        if (type === 'textarea') {
          addBtn.classList.add('hidden');
          return;
        }
        addBtn.classList.remove('hidden');
        (question.options || []).forEach((option) => optionsWrap.appendChild(optionCard(option)));
        if (!optionsWrap.children.length) optionsWrap.appendChild(optionCard());
      };
      renderOptions();
      wrapper.querySelector('[data-field="type"]').addEventListener('change', () => {
        question.type = wrapper.querySelector('[data-field="type"]').value;
        if (question.type === 'textarea') question.options = [];
        renderOptions();
      });
      wrapper.querySelector('.add-option').addEventListener('click', () => optionsWrap.appendChild(optionCard()));
      wrapper.querySelector('.remove-question').addEventListener('click', () => wrapper.remove());
      questionsEl.appendChild(wrapper);
    }

    function addRuleCard(rule = blankRule()) {
      const wrapper = document.createElement('div');
      wrapper.className = 'rule-card';
      wrapper.innerHTML = `
        <div class="inline-row">
          <label style="flex:1;">min_score<input data-field="min_score" type="text" value="${escapeHtml(rule.min_score ?? '')}"></label>
          <label style="flex:1;">max_score<input data-field="max_score" type="text" value="${escapeHtml(rule.max_score ?? '')}"></label>
          <label style="flex:1;">sort_order<input data-field="sort_order" type="text" value="${escapeHtml(rule.sort_order ?? 1)}"></label>
        </div>
        <button type="button" class="danger remove-rule">删除规则</button>
      `;
      wrapper.insertBefore(createTagPicker(rule.tag_codes || []), wrapper.querySelector('.remove-rule'));
      wrapper.querySelector('.remove-rule').addEventListener('click', () => wrapper.remove());
      scoreRulesEl.appendChild(wrapper);
    }

    function collectPayload() {
      const questions = Array.from(questionsEl.children).map((el) => {
        const type = el.querySelector('[data-field="type"]').value;
        const payload = {
          type,
          title: el.querySelector('[data-field="title"]').value,
          required: el.querySelector('[data-field="required"]').checked,
          sort_order: Number(el.querySelector('[data-field="sort_order"]').value || 0),
        };
        if (type !== 'textarea') {
          payload.options = Array.from(el.querySelectorAll('.option-card')).map((optionEl) => ({
            option_text: optionEl.querySelector('[data-field="option_text"]').value,
            score: Number(optionEl.querySelector('[data-field="score"]').value || 0),
            tag_codes: collectTagIds(optionEl),
            sort_order: Number(optionEl.querySelector('[data-field="sort_order"]').value || 0),
          }));
        }
        return payload;
      });

      const score_rules = Array.from(scoreRulesEl.children).map((el) => ({
        min_score: el.querySelector('[data-field="min_score"]').value,
        max_score: el.querySelector('[data-field="max_score"]').value,
        tag_codes: collectTagIds(el),
        sort_order: Number(el.querySelector('[data-field="sort_order"]').value || 0),
      }));

      return {
        name: field('name').value,
        title: field('title').value,
        description: field('description').value,
        redirect_url: field('redirect_url').value,
        slug: field('slug').value,
        is_disabled: field('is_disabled').checked,
        questions,
        score_rules,
      };
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, options);
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) throw new Error(data.error || '请求失败');
      return data;
    }

    async function loadAvailableTags() {
      try {
        const data = await fetchJson('/api/admin/wecom/tags');
        availableTags = data.items || [];
        availableTagMap = new Map(availableTags.map((item) => [item.tag_id, item]));
        if (!availableTags.length) {
          showMessage(tagCatalogMessageEl, '当前未获取到企微标签，可手工填写 tag_id');
        } else {
          showMessage(tagCatalogMessageEl, '');
        }
      } catch (error) {
        availableTags = [];
        availableTagMap = new Map();
        showMessage(tagCatalogMessageEl, '企微标签加载失败，可稍后重试或手工填写 tag_id', true);
      }
    }

    async function loadList() {
      const data = await fetchJson('/api/admin/questionnaires');
      listEl.innerHTML = '';
      data.questionnaires.forEach((item) => {
        const el = document.createElement('div');
        el.className = 'item';
        el.innerHTML = `
          <h3>${escapeHtml(item.name)}<span class="status ${item.is_disabled ? 'disabled' : ''}">${item.is_disabled ? '已停用' : '启用中'}</span></h3>
          <div class="muted">${escapeHtml(item.title)}</div>
          <div class="muted">提交 ${item.submission_count || 0} 次</div>
          <div class="item-actions" style="margin-top:10px;">
            <button type="button" class="ghost edit">编辑</button>
            <button type="button" class="secondary toggle">${item.is_disabled ? '启用' : '停用'}</button>
            <button type="button" class="danger remove">删除</button>
            <button type="button" class="ghost export">导出数据</button>
            <button type="button" class="ghost copy">复制链接</button>
            <button type="button" class="ghost latest-debug">最近提交调试</button>
          </div>
        `;
        el.querySelector('.edit').addEventListener('click', async () => {
          const detail = await fetchJson(`/api/admin/questionnaires/${item.id}`);
          resetForm(detail.questionnaire);
        });
        el.querySelector('.toggle').addEventListener('click', async () => {
          await fetchJson(`/api/admin/questionnaires/${item.id}/disable`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ is_disabled: !item.is_disabled }) });
          showMessage(listMessageEl, item.is_disabled ? '问卷已启用' : '问卷已停用');
          await loadList();
        });
        el.querySelector('.remove').addEventListener('click', async () => {
          if (!confirm(`确认删除问卷「${item.name}」吗？`)) return;
          await fetchJson(`/api/admin/questionnaires/${item.id}`, { method: 'DELETE' });
          showMessage(listMessageEl, '问卷已删除');
          await loadList();
          if (currentId === item.id) resetForm();
        });
        el.querySelector('.export').addEventListener('click', () => {
          window.open(`/api/admin/questionnaires/${item.id}/export`, '_blank');
        });
        el.querySelector('.copy').addEventListener('click', async () => {
          await navigator.clipboard.writeText(item.public_url);
          showMessage(listMessageEl, '链接已复制');
        });
        el.querySelector('.latest-debug').addEventListener('click', async () => {
          try {
            const result = await fetchJson(`/api/admin/questionnaires/${item.id}/latest-submit-debug`);
            showDebugBox(
              latestSubmitResultEl,
              [
                `问卷ID: ${result.questionnaire_id}`,
                `提交ID: ${result.submission_id}`,
                `matched_by: ${result.matched_by || '-'}`,
                `external_userid: ${result.external_userid || '-'}`,
                `follow_user_userid: ${result.follow_user_userid || '-'}`,
                `total_score: ${result.total_score}`,
                `final_tags: ${(result.final_tags || []).join(', ') || '-'}`,
                `scrm_apply_status: ${result.scrm_apply_status || '-'}`,
              ].join('\n')
            );
          } catch (error) {
            showDebugBox(latestSubmitResultEl, `最近提交调试失败: ${error.message || '请求失败'}`);
          }
        });
        listEl.appendChild(el);
      });
    }

    document.getElementById('preflight-btn').addEventListener('click', async () => {
      try {
        const result = await fetchJson('/api/admin/questionnaires/preflight');
        showDebugBox(
          preflightResultEl,
          Object.entries(result).map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`).join('\n')
        );
      } catch (error) {
        showDebugBox(preflightResultEl, `环境检查失败: ${error.message || '请求失败'}`);
      }
    });
    document.getElementById('new-btn').addEventListener('click', () => resetForm());
    document.getElementById('reset-btn').addEventListener('click', () => resetForm());
    document.getElementById('add-single').addEventListener('click', () => addQuestionCard(blankQuestion('single_choice')));
    document.getElementById('add-multi').addEventListener('click', () => addQuestionCard(blankQuestion('multi_choice')));
    document.getElementById('add-textarea').addEventListener('click', () => addQuestionCard(blankQuestion('textarea')));
    document.getElementById('add-rule').addEventListener('click', () => addRuleCard());
    document.getElementById('save-btn').addEventListener('click', async () => {
      try {
        const payload = collectPayload();
        const url = currentId ? `/api/admin/questionnaires/${currentId}` : '/api/admin/questionnaires';
        const method = currentId ? 'PUT' : 'POST';
        const data = await fetchJson(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        showMessage(formMessageEl, currentId ? '问卷已更新' : '问卷已创建');
        resetForm(data.questionnaire);
        await loadList();
      } catch (error) {
        showMessage(formMessageEl, error.message || '保存失败', true);
      }
    });

    Promise.all([
      loadAvailableTags(),
      loadList().catch((error) => showMessage(listMessageEl, error.message || '加载失败', true)),
    ]).finally(() => {
      resetForm();
    });
  