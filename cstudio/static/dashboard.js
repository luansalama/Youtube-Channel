(() => {
  "use strict";

  const body = document.body;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function toggleClass(name, enabled) {
    body.classList.toggle(name, enabled);
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
        const oldRun = $('[data-twitch-live]', twitchContainer);
        const oldLog = $('.log-output', twitchContainer);
        const wasNearBottom = oldLog ? (oldLog.scrollHeight - oldLog.scrollTop - oldLog.clientHeight < 44) : true;
        const oldId = oldRun?.dataset.runId || '';
        twitchContainer.innerHTML = html;
        const newRun = $('[data-twitch-live]', twitchContainer);
        const newLog = $('.log-output', twitchContainer);
        if (newLog && (wasNearBottom || oldId !== (newRun?.dataset.runId || ''))) newLog.scrollTop = newLog.scrollHeight;
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
})();
