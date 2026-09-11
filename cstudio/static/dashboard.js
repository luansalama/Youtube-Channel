(() => {
  "use strict";

  const body = document.body;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function toggleClass(name, enabled) {
    body.classList.toggle(name, enabled);
  }

  async function copyText(text) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-copy-log]');
    if (!button) return;
    const log = button.closest('.log-panel')?.querySelector('.log-output');
    if (!log) return;
    const original = button.textContent;
    try {
      await copyText(log.textContent || '');
      button.textContent = 'Copiado';
      button.dataset.copied = 'true';
    } catch (error) {
      button.textContent = 'Falha ao copiar';
    }
    window.setTimeout(() => {
      button.textContent = original;
      delete button.dataset.copied;
    }, 1600);
  });

  function replaceLiveFragment(container, html, runSelector) {
    const oldRun = $(runSelector, container);
    const oldLog = $('.log-output', container);
    const oldId = oldRun?.dataset.runId || '';
    const oldScrollTop = oldLog?.scrollTop || 0;
    const wasNearBottom = oldLog ? (oldLog.scrollHeight - oldLog.scrollTop - oldLog.clientHeight < 44) : true;

    const template = document.createElement('template');
    template.innerHTML = html.trim();
    const incomingRun = $(runSelector, template.content);
    const incomingLog = $('.log-output', template.content);
    const newId = incomingRun?.dataset.runId || '';

    // Keep the existing <pre> node for the same run. Appending only the new
    // suffix preserves scroll position and text selection while polling.
    if (oldLog && incomingLog && oldId && oldId === newId) {
      const oldText = oldLog.textContent || '';
      const newText = incomingLog.textContent || '';
      if (newText.startsWith(oldText)) {
        const suffix = newText.slice(oldText.length);
        if (suffix) oldLog.append(document.createTextNode(suffix));
      } else if (newText !== oldText) {
        oldLog.textContent = newText;
      }
      incomingLog.replaceWith(oldLog);
    }

    container.replaceChildren(template.content);
    const newRun = $(runSelector, container);
    const newLog = $('.log-output', container);
    if (newLog) {
      if (wasNearBottom || oldId !== (newRun?.dataset.runId || '')) newLog.scrollTop = newLog.scrollHeight;
      else newLog.scrollTop = oldScrollTop;
    }
    return newRun;
  }

  $$('[data-open-sidebar]').forEach((button) => button.addEventListener('click', () => toggleClass('sidebar-open', true)));
  $$('[data-close-sidebar]').forEach((button) => button.addEventListener('click', () => toggleClass('sidebar-open', false)));
  $$('[data-open-context]').forEach((button) => button.addEventListener('click', () => toggleClass('context-open', true)));
  $$('[data-close-context]').forEach((button) => button.addEventListener('click', () => toggleClass('context-open', false)));

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      toggleClass('sidebar-open', false);
      toggleClass('context-open', false);
    }
  });

  if (!reducedMotion && 'animate' in Element.prototype) {
    const nodes = $$('.page-header, .next-action, .metric, .panel, .artifact-hero, .cli-strip');
    nodes.slice(0, 14).forEach((node, index) => {
      node.animate(
        [
          { opacity: 0, transform: 'translateY(8px)' },
          { opacity: 1, transform: 'translateY(0)' },
        ],
        { duration: 220, delay: Math.min(index * 24, 150), easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'both' },
      );
    });
  }

  const runnerForms = $$('[data-agent-job-form], [data-runner-form]');
  runnerForms.forEach((agentForm) => {
    const submitButton = $('button[type="submit"]', agentForm);
    const feedback = $('[data-agent-feedback]', agentForm);
    const originalButtonHtml = submitButton?.innerHTML || '';
    const formLocked = Boolean(submitButton?.disabled);
    const runnerSelect = $('[data-runner-select]', agentForm);
    const modelSelect = $('[data-model-select]', agentForm);
    const effortSelect = $('[data-effort-select]', agentForm);
    const modelHint = $('[data-model-hint]', agentForm);
    const effortHint = $('[data-effort-hint]', agentForm);
    const selectionSummary = $('[data-agent-selection-summary]', agentForm);
    let runnerConfig = {
      models: {}, model_labels: {}, efforts: {}, model_efforts: {},
      model_default_efforts: {}, defaults: {}, effort_labels: {},
    };
    try { runnerConfig = { ...runnerConfig, ...JSON.parse(agentForm.dataset.runnerConfig || '{}') }; } catch (_) {}
    let previousRunner = runnerSelect?.value || '';
    let previousModel = modelSelect?.value || '';

    function runnerDefault(runner) {
      return runnerConfig.defaults?.[runner] || {};
    }

    function effortsFor(runner, model) {
      return runnerConfig.model_efforts?.[runner]?.[model] || runnerConfig.efforts?.[runner] || [];
    }

    function populateModels(runner, wanted = '') {
      if (!modelSelect) return '';
      const models = runnerConfig.models?.[runner] || [];
      const labels = runnerConfig.model_labels?.[runner] || {};
      const target = models.includes(wanted) ? wanted : (runnerDefault(runner).model || models[0] || '');
      modelSelect.innerHTML = '';
      models.forEach((model) => {
        const option = document.createElement('option');
        option.value = model;
        option.textContent = labels[model] || model;
        option.selected = model === target;
        modelSelect.appendChild(option);
      });
      return target;
    }

    function populateEfforts(runner, model, wanted = '') {
      if (!effortSelect) return '';
      const efforts = effortsFor(runner, model);
      const labels = runnerConfig.effort_labels || {};
      const modelDefault = runnerConfig.model_default_efforts?.[runner]?.[model] || runnerDefault(runner).reasoning_effort || efforts[0] || '';
      const target = efforts.includes(wanted) ? wanted : (efforts.includes(modelDefault) ? modelDefault : (efforts[0] || ''));
      effortSelect.innerHTML = '';
      efforts.forEach((effort) => {
        const option = document.createElement('option');
        option.value = effort;
        option.textContent = labels[effort] || effort;
        option.selected = effort === target;
        effortSelect.appendChild(option);
      });
      return target;
    }

    function syncAgentControls({ runnerChanged = false, modelChanged = false } = {}) {
      if (!runnerSelect || !modelSelect || !effortSelect) return;
      const runner = runnerSelect.value;
      if (runnerChanged || runner !== previousRunner) {
        previousModel = populateModels(runner, runnerDefault(runner).model);
        populateEfforts(runner, previousModel, runnerDefault(runner).reasoning_effort);
      } else if (modelChanged || modelSelect.value !== previousModel) {
        previousModel = modelSelect.value;
        populateEfforts(runner, previousModel, runnerConfig.model_default_efforts?.[runner]?.[previousModel] || '');
      } else if (!effortSelect.options.length) {
        populateEfforts(runner, modelSelect.value, '');
      }
      previousRunner = runner;
      previousModel = modelSelect.value;
      modelSelect.disabled = formLocked;
      effortSelect.disabled = formLocked;

      if (modelHint) {
        modelHint.textContent = runner === 'opencode'
          ? 'Somente o lineup OpenCode Zen Free desta configuração.'
          : runner === 'agy'
            ? 'Modelos do Antigravity Free; uso continua sujeito às quotas da conta/modelo.'
            : 'Catálogo atual do Codex CLI; modelos aposentados ficam fora do seletor.';
      }
      if (effortHint) {
        const count = effortsFor(runner, modelSelect.value).length;
        effortHint.textContent = runner === 'opencode' && effortSelect.value === 'default'
          ? 'Este modelo não expõe variant; o reasoning fica model-managed.'
          : count <= 1
            ? 'Reasoning fixo para este modelo.'
            : 'Somente níveis compatíveis com o modelo selecionado.';
      }
      const modelLabel = modelSelect.selectedOptions[0]?.textContent || modelSelect.value || 'modelo padrão';
      const effortLabel = effortSelect.selectedOptions[0]?.textContent || effortSelect.value || 'default';
      if (selectionSummary) selectionSummary.textContent = `${runner} · ${modelLabel} · reasoning ${effortLabel}`;
    }

    runnerSelect?.addEventListener('change', () => syncAgentControls({ runnerChanged: true }));
    modelSelect?.addEventListener('change', () => syncAgentControls({ modelChanged: true }));
    effortSelect?.addEventListener('change', () => syncAgentControls());
    syncAgentControls();

    function setAgentFeedback(message, isError = false) {
      if (!feedback) return;
      if (!message) {
        feedback.hidden = true;
        feedback.className = 'agent-submit-feedback';
        feedback.textContent = '';
        return;
      }
      feedback.hidden = false;
      feedback.className = `agent-submit-feedback notice ${isError ? 'notice-danger' : 'notice-info'}`;
      feedback.textContent = message;
    }

    agentForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (submitButton?.disabled) return;
      const formData = new FormData(agentForm);
      const sourceIds = formData.getAll('source_asset_ids').map(String).filter(Boolean);
      const continueAttempt = ['1', 'true', 'on', 'yes'].includes(String(formData.get('continue_attempt') || '').toLowerCase());
      if (agentForm.action.endsWith('/action/video-proposal-run') && sourceIds.length === 0 && !continueAttempt) {
        setAgentFeedback('Selecione pelo menos um VOD para esta proposta.', true);
        return;
      }
      const payload = Object.fromEntries(formData.entries());
      if (sourceIds.length) payload.source_asset_ids = sourceIds;
      if (agentForm.action.endsWith('/action/video-proposal-refine')) {
        const card = agentForm.closest('.video-proposal-card');
        const answerFields = card ? $$('[name^="answer_"]', card) : [];
        payload.answers = Object.fromEntries(answerFields.map((field) => [field.name.slice(7), field.value]));
      }
      setAgentFeedback('');
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = 'Iniciando…';
      }
      try {
        const response = await fetch(agentForm.action, {
          method: 'POST',
          headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          cache: 'no-store',
        });
        let data = {};
        try { data = await response.json(); } catch (_) { data = {}; }
        if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
        setAgentFeedback(continueAttempt
          ? 'Continuação iniciada na mesma sessão. O agente recebeu apenas “Continue.”'
          : (agentForm.action.includes('refine') ? 'Refinamento iniciado. Acompanhe o job acima.' : 'Proposta iniciada. Acompanhe o job abaixo.'));
        if (submitButton) submitButton.textContent = 'Executando…';
        const pageJob = $('.studio-job-fragment[data-studio-job-endpoint]');
        pageJob?.dispatchEvent(new CustomEvent('cstudio:refresh-job'));
      } catch (error) {
        const offline = error instanceof TypeError;
        setAgentFeedback(
          offline ? 'Não foi possível falar com o dashboard. O servidor local pode ter parado.' : `Não foi possível iniciar: ${error.message || error}`,
          true,
        );
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.innerHTML = originalButtonHtml;
        }
      }
    });
  });

  const vodChoices = $$('input[name="source_asset_ids"]');
  if (vodChoices.length) {
    const count = $('[data-vod-selection-count]');
    const syncVodCount = () => {
      const selected = vodChoices.filter((item) => item.checked).length;
      if (count) count.textContent = `${selected} VOD${selected === 1 ? '' : 's'} selecionado${selected === 1 ? '' : 's'}`;
    };
    $$('[data-vod-select]').forEach((button) => button.addEventListener('click', () => {
      const checked = button.dataset.vodSelect === 'all';
      vodChoices.forEach((item) => { item.checked = checked; });
      syncVodCount();
    }));
    vodChoices.forEach((item) => item.addEventListener('change', syncVodCount));
    syncVodCount();
  }

  const dialog = $('#confirm-dialog');
  const dialogMessage = $('#confirm-message');
  let pendingForm = null;

  if (dialog && typeof dialog.showModal === 'function') {
    $$('form[data-confirm]').forEach((form) => {
      form.addEventListener('submit', (event) => {
        if (form.dataset.confirmed === 'true') {
          delete form.dataset.confirmed;
          return;
        }
        event.preventDefault();
        pendingForm = form;
        dialogMessage.textContent = form.dataset.confirm || 'Confirmar esta ação?';
        dialog.showModal();
      });
    });
    dialog.addEventListener('close', () => {
      if (dialog.returnValue === 'confirm' && pendingForm) {
        const form = pendingForm;
        pendingForm = null;
        form.dataset.confirmed = 'true';
        form.requestSubmit();
      } else {
        pendingForm = null;
      }
    });
  }

  const filterInput = $('[data-table-filter]');
  if (filterInput) {
    const table = document.getElementById(filterInput.dataset.tableFilter);
    const counter = $('[data-table-count]');
    const rows = table ? Array.from(table.tBodies[0]?.rows || []) : [];
    filterInput.addEventListener('input', () => {
      const query = filterInput.value.trim().toLocaleLowerCase('pt-BR');
      let visible = 0;
      rows.forEach((row) => {
        const match = !query || row.textContent.toLocaleLowerCase('pt-BR').includes(query);
        row.hidden = !match;
        if (match) visible += 1;
      });
      if (counter) counter.textContent = `${visible} linha${visible === 1 ? '' : 's'}`;
    });
  }

  const youtubeAssignmentSearch = $('[data-youtube-assignment-search]');
  const youtubeAssignmentList = $('[data-youtube-assignment-list]');
  if (youtubeAssignmentList) {
    const assignmentCards = $$('[data-youtube-assignment]', youtubeAssignmentList);
    const assignmentFilters = $$('[data-youtube-state-filter]');
    const visibleCount = $('[data-youtube-visible-count]');
    const emptyState = $('[data-youtube-filter-empty]');
    let assignmentState = 'all';

    function applyAssignmentFilter() {
      const query = (youtubeAssignmentSearch?.value || '').trim().toLocaleLowerCase('pt-BR');
      let visible = 0;
      assignmentCards.forEach((card) => {
        const stateMatch = assignmentState === 'all' || card.dataset.state === assignmentState;
        const haystack = (card.dataset.search || card.textContent || '').toLocaleLowerCase('pt-BR');
        const queryMatch = !query || haystack.includes(query);
        const show = stateMatch && queryMatch;
        card.hidden = !show;
        if (show) visible += 1;
      });
      if (visibleCount) visibleCount.textContent = `${visible} visíve${visible === 1 ? 'l' : 'is'}`;
      if (emptyState) emptyState.hidden = visible !== 0;
    }

    youtubeAssignmentSearch?.addEventListener('input', applyAssignmentFilter);
    assignmentFilters.forEach((button) => button.addEventListener('click', () => {
      assignmentState = button.dataset.youtubeStateFilter || 'all';
      assignmentFilters.forEach((item) => item.classList.toggle('is-active', item === button));
      applyAssignmentFilter();
    }));
  }

  const twitchContainer = $('#twitch-run-fragment');
  if (twitchContainer) {
    const endpoint = twitchContainer.dataset.twitchEndpoint;
    const connection = $('[data-live-connection]');
    let timer = null;
    let stopped = false;

    function shouldPoll() {
      const run = $('[data-twitch-live]', twitchContainer);
      return run?.dataset.running === 'true';
    }

    function setConnection(text) {
      if (connection) connection.textContent = text;
    }

    async function refreshRun() {
      if (stopped || !endpoint) return;
      try {
        setConnection('Atualizando…');
        const response = await fetch(endpoint, { headers: { 'Accept': 'text/html', 'X-CStudio-Fragment': '1' }, cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const html = await response.text();
        const newRun = replaceLiveFragment(twitchContainer, html, '[data-twitch-live]');
        setConnection(newRun?.dataset.running === 'true' ? 'Monitor local · 2 s' : 'Execução finalizada');
        if (newRun?.dataset.running !== 'true') stopped = true;
      } catch (error) {
        setConnection('Falha ao atualizar · tentando novamente');
      }
      if (!stopped) timer = window.setTimeout(refreshRun, 2000);
    }

    if (shouldPoll()) {
      timer = window.setTimeout(refreshRun, 900);
    } else {
      setConnection('Monitor local');
    }

    window.addEventListener('beforeunload', () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    });
  }

  $$('.studio-job-fragment[data-studio-job-endpoint]').forEach((studioContainer) => {
    const endpoint = studioContainer.dataset.studioJobEndpoint;
    const connection = $('[data-studio-job-connection]');
    let timer = null;
    let stopped = false;

    function currentRun() { return $('[data-studio-job-live]', studioContainer); }
    function setConnection(text) { if (connection) connection.textContent = text; }

    async function refreshStudioJob() {
      if (stopped || !endpoint) return;
      try {
        setConnection('Atualizando…');
        const response = await fetch(endpoint, { headers: { 'Accept': 'text/html', 'X-CStudio-Fragment': '1' }, cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const html = await response.text();
        const newRun = replaceLiveFragment(studioContainer, html, '[data-studio-job-live]');
        setConnection(newRun?.dataset.running === 'true' ? 'Monitor local · 2 s' : 'Execução finalizada');
        if (newRun?.dataset.running !== 'true') stopped = true;
      } catch (error) {
        setConnection('Falha ao atualizar · tentando novamente');
      }
      if (!stopped) timer = window.setTimeout(refreshStudioJob, 2000);
    }

    if (currentRun()?.dataset.running === 'true') timer = window.setTimeout(refreshStudioJob, 800);
    else setConnection('Monitor local');

    studioContainer.addEventListener('cstudio:refresh-job', () => {
      stopped = false;
      if (timer) clearTimeout(timer);
      timer = window.setTimeout(refreshStudioJob, 80);
    });

    window.addEventListener('beforeunload', () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    });
  });

  const youtubeContainer = $('#youtube-run-fragment');
  if (youtubeContainer) {
    const endpoint = youtubeContainer.dataset.youtubeEndpoint;
    const connection = $('[data-youtube-connection]');
    let timer = null;
    let stopped = false;

    function currentRun() { return $('[data-youtube-live]', youtubeContainer); }
    function setConnection(text) { if (connection) connection.textContent = text; }

    async function refreshRun() {
      if (stopped || !endpoint) return;
      try {
        setConnection('Atualizando…');
        const response = await fetch(endpoint, { headers: { 'Accept': 'text/html', 'X-CStudio-Fragment': '1' }, cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const html = await response.text();
        const newRun = replaceLiveFragment(youtubeContainer, html, '[data-youtube-live]');
        setConnection(newRun?.dataset.running === 'true' ? 'Monitor local · 2 s' : 'Execução finalizada');
        if (newRun?.dataset.running !== 'true') stopped = true;
      } catch (error) {
        setConnection('Falha ao atualizar · tentando novamente');
      }
      if (!stopped) timer = window.setTimeout(refreshRun, 2000);
    }

    if (currentRun()?.dataset.running === 'true') timer = window.setTimeout(refreshRun, 900);
    else setConnection('Monitor local');

    window.addEventListener('beforeunload', () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    });
  }
})();
