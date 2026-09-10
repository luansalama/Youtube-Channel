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
