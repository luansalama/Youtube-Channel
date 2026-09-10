export const SCRAPER_VERSION = '7.6';
export const DEFAULT_LIMIT = 5;
export const DEFAULT_CHAT_CONCURRENCY = 4;
export const MAX_CHAT_CONCURRENCY = 8;
export const DEFAULT_CHAT_TASKS_PER_WORKER = 2;
export const DEFAULT_CHAT_OVERLAP_SECONDS = 60;
export const MIN_CHAT_TASK_SPAN_SECONDS = 300;

export function cloneJson(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

export function extractVodId(value) {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  const urlMatch = text.match(/(?:https?:\/\/)?(?:www\.)?twitch\.tv\/videos\/(\d+)/i);
  if (urlMatch) return urlMatch[1];
  if (/^\d{7,}$/.test(text)) return text;
  return null;
}

function parsePositiveInt(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function parseCli(argv = process.argv) {
  const streamer = argv[2] || 'alanzoka';
  const args = argv.slice(3);
  const positional = [];
  let force = false;
  let resume = true;
  let requestedThreads = DEFAULT_CHAT_CONCURRENCY;
  let help = false;

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === '--force') {
      force = true;
      continue;
    }
    if (arg === '--no-resume') {
      resume = false;
      continue;
    }
    if (arg === '--sequential') {
      requestedThreads = 1;
      continue;
    }
    if (arg === '--help' || arg === '-h') {
      help = true;
      continue;
    }
    if (arg === '--threads' || arg === '-t') {
      requestedThreads = parsePositiveInt(args[i + 1], DEFAULT_CHAT_CONCURRENCY);
      i += 1;
      continue;
    }
    if (arg.startsWith('--threads=')) {
      requestedThreads = parsePositiveInt(arg.split('=', 2)[1], DEFAULT_CHAT_CONCURRENCY);
      continue;
    }
    positional.push(arg);
  }

  const threads = Math.max(1, Math.min(MAX_CHAT_CONCURRENCY, requestedThreads));
  const targetArg = positional[0] || String(DEFAULT_LIMIT);
  const specificVodId = extractVodId(targetArg);
  const common = {
    streamer,
    force,
    resume,
    requested_threads: requestedThreads,
    threads,
    concurrency_capped: requestedThreads > MAX_CHAT_CONCURRENCY,
    max_threads: MAX_CHAT_CONCURRENCY,
    tasks_per_worker: threads === 1 ? 1 : DEFAULT_CHAT_TASKS_PER_WORKER,
    help,
    targetArg,
  };

  if (specificVodId) {
    return {
      ...common,
      mode: 'specific_vod',
      vodId: specificVodId,
      limit: null,
    };
  }

  const limit = parsePositiveInt(targetArg, DEFAULT_LIMIT);
  return {
    ...common,
    mode: 'latest',
    vodId: null,
    limit,
  };
}

export function buildChatVariables(template, vodId, offset) {
  const variables = cloneJson(template && typeof template === 'object' ? template : {}) || {};
  delete variables.cursor;
  variables.videoID = String(vodId);
  variables.contentOffsetSeconds = Number(offset);
  return variables;
}

export function buildChatSegments({
  startOffset = 0,
  durationSeconds,
  concurrency = DEFAULT_CHAT_CONCURRENCY,
  tasksPerWorker = DEFAULT_CHAT_TASKS_PER_WORKER,
  overlapSeconds = DEFAULT_CHAT_OVERLAP_SECONDS,
  tailSeconds = DEFAULT_CHAT_OVERLAP_SECONDS,
  minTaskSpanSeconds = MIN_CHAT_TASK_SPAN_SECONDS,
}) {
  const duration = Math.max(0, Number(durationSeconds) || 0);
  const start = Math.max(0, Number(startOffset) || 0);
  const logicalEnd = Math.max(start, duration + Math.max(0, tailSeconds));
  const range = Math.max(0, logicalEnd - start);
  if (range <= 0) {
    return [{
      id: 'segment-1',
      index: 0,
      nominal_start: start,
      nominal_end: logicalEnd,
      fetch_start: start,
      fetch_end: logicalEnd,
      is_final: true,
    }];
  }

  const workers = Math.max(1, Number(concurrency) || 1);
  const factor = Math.max(1, Number(tasksPerWorker) || DEFAULT_CHAT_TASKS_PER_WORKER);
  const desiredCount = Math.max(1, Math.ceil(workers * factor));
  const maxBySpan = Math.max(1, Math.floor(range / Math.max(120, Number(minTaskSpanSeconds) || MIN_CHAT_TASK_SPAN_SECONDS)));
  const count = Math.max(1, Math.min(desiredCount, maxBySpan));
  const span = range / count;
  const segments = [];

  for (let index = 0; index < count; index += 1) {
    const nominalStart = start + (span * index);
    const nominalEnd = index === count - 1 ? logicalEnd : start + (span * (index + 1));
    const fetchStart = index === 0
      ? start
      : Math.max(start, Math.floor(nominalStart - overlapSeconds));
    const fetchEnd = index === count - 1
      ? logicalEnd
      : Math.min(logicalEnd, Math.ceil(nominalEnd + overlapSeconds));

    segments.push({
      id: `segment-${index + 1}`,
      index,
      nominal_start: Math.floor(nominalStart),
      nominal_end: Math.ceil(nominalEnd),
      fetch_start: Math.floor(fetchStart),
      fetch_end: Math.ceil(fetchEnd),
      is_final: index === count - 1,
    });
  }

  return segments;
}

export function buildConcurrencyLadder(startConcurrency) {
  let current = Math.max(1, Math.min(MAX_CHAT_CONCURRENCY, Number(startConcurrency) || 1));
  const ladder = [];
  while (true) {
    if (!ladder.includes(current)) ladder.push(current);
    if (current <= 1) break;
    current = Math.max(1, Math.floor(current / 2));
  }
  if (!ladder.includes(1)) ladder.push(1);
  return ladder;
}

export function computeRetryDelayMs({ attempt = 1, status = null, retryAfterSeconds = null, jitterUnit = Math.random() } = {}) {
  if (Number.isFinite(Number(retryAfterSeconds)) && Number(retryAfterSeconds) > 0) {
    const retryMs = Number(retryAfterSeconds) * 1000;
    return Math.round(retryMs + Math.min(1000, retryMs * 0.1) * Math.max(0, Math.min(1, Number(jitterUnit) || 0)));
  }
  const base = status === 429 ? 1500 : (status && status >= 500 ? 800 : 500);
  const exp = base * (2 ** Math.max(0, Number(attempt) - 1));
  const jitter = exp * 0.35 * Math.max(0, Math.min(1, Number(jitterUnit) || 0));
  return Math.round(exp + jitter);
}

export async function runDynamicQueue(items, concurrency, worker, { pollMs = 25, onReduction = null } = {}) {
  const results = new Array(items.length);
  let cursor = 0;
  const initialConcurrency = Math.max(1, Math.min(Number(concurrency) || 1, items.length || 1));
  let activeLimit = initialConcurrency;
  const reductions = [];
  const assignments = [];
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  const reducePressure = (result, reason) => {
    if (activeLimit <= 1) return;
    const nextLimit = Math.max(1, Math.floor(activeLimit / 2));
    if (nextLimit >= activeLimit) return;
    const reduction = {
      from: activeLimit,
      to: nextLimit,
      reason,
      segment_id: result?.segment?.id ?? result?.id ?? null,
      at: new Date().toISOString(),
    };
    reductions.push(reduction);
    activeLimit = nextLimit;
    if (typeof onReduction === 'function') onReduction(reduction);
  };

  const runners = Array.from({ length: initialConcurrency }, (_, slotIndex) => {
    const workerId = slotIndex + 1;
    return (async () => {
      while (true) {
        if (cursor >= items.length) return;
        if (workerId > activeLimit) {
          await sleep(pollMs);
          continue;
        }

        const index = cursor;
        cursor += 1;
        if (index >= items.length) return;
        const item = items[index];
        const startedAt = Date.now();
        const result = await worker(item, index, workerId);
        results[index] = result;
        assignments.push({
          worker_id: workerId,
          segment_id: item?.id ?? null,
          queue_index: index,
          elapsed_ms: Date.now() - startedAt,
          pages: result?.pages ?? null,
          ok: !!result?.ok,
          rate_limited: !!result?.rate_limited,
        });

        if (result?.rate_limited) {
          reducePressure(result, 'rate_limit');
        } else if (!result?.ok && result?.terminal_scope === 'request_error') {
          reducePressure(result, 'request_error');
        }
      }
    })();
  });

  await Promise.all(runners);
  return {
    results,
    initial_concurrency: initialConcurrency,
    final_concurrency: activeLimit,
    reductions,
    assignments,
  };
}

export function versionAtLeast(actual, minimum) {
  const parse = value => String(value ?? '')
    .split('.')
    .map(part => Number.parseInt(part, 10) || 0)
    .slice(0, 3);
  const a = parse(actual);
  const b = parse(minimum);
  while (a.length < 3) a.push(0);
  while (b.length < 3) b.push(0);
  for (let i = 0; i < 3; i += 1) {
    if (a[i] > b[i]) return true;
    if (a[i] < b[i]) return false;
  }
  return true;
}

export function classifyIntegrityComplete(integrity = {}, scraperVersion = null) {
  const terminalScope = integrity.terminal_scope ?? null;
  const terminalReason = integrity.terminal_reason ?? null;
  const terminalOk =
    terminalScope === 'chat_connection_reported_end' ||
    terminalScope === 'archive_duration_boundary' ||
    terminalScope === 'parallel_segment_coverage_complete' ||
    terminalScope === 'dynamic_queue_coverage_complete' ||
    terminalReason === 'hasNextPage_false' ||
    terminalReason === 'post_duration_api_boundary' ||
    terminalReason === 'parallel_segments_complete' ||
    terminalReason === 'dynamic_queue_complete';

  const segmentCoverage = integrity.segment_coverage;
  const segmentOk = !segmentCoverage || segmentCoverage.coverage_status === 'OK';
  const countOk =
    integrity.total_messages === undefined ||
    integrity.unique_message_ids === undefined ||
    Number(integrity.total_messages) === Number(integrity.unique_message_ids);

  const complete =
    Number(integrity.errors_count ?? 0) === 0 &&
    Number(integrity.duplicate_message_ids_in_output ?? 0) === 0 &&
    (integrity.pagination_progression ?? 'OK') === 'OK' &&
    (integrity.output_chronological_order ?? 'OK') === 'OK' &&
    terminalOk &&
    segmentOk &&
    countOk;

  return {
    complete,
    terminal_ok: terminalOk,
    segment_ok: segmentOk,
    count_ok: countOk,
    compatible_version: !scraperVersion || versionAtLeast(scraperVersion, '7.4.1'),
  };
}

export function historicalMatchesCurrentStream(record = {}) {
  const historical = record?.stream?.broadcast_id
    ?? record?.stream?.id
    ?? record?.historical_broadcast_id
    ?? null;
  const current = record?.current_channel_stream?.id ?? null;
  return !!historical && !!current && String(historical) === String(current);
}

export function classifyVodLifecycle({
  integrity = {},
  scraperVersion = null,
  historicalBroadcastId = null,
  currentChannelStream = null,
} = {}) {
  const basis = {
    ...integrity,
    terminal_reason: integrity.source_terminal_reason ?? integrity.terminal_reason,
    terminal_scope: integrity.source_terminal_scope ?? integrity.terminal_scope,
  };
  const integrityClassification = classifyIntegrityComplete(basis, scraperVersion);
  const currentId = currentChannelStream?.id ?? null;
  const currentBroadcastMatch =
    !!historicalBroadcastId &&
    !!currentId &&
    String(historicalBroadcastId) === String(currentId);

  const caughtUp = currentBroadcastMatch && integrityClassification.complete;
  const complete = !currentBroadcastMatch && integrityClassification.complete;

  return {
    ...integrityClassification,
    complete,
    caught_up: caughtUp,
    current_broadcast_match: currentBroadcastMatch,
    status: currentBroadcastMatch ? 'in_progress' : (complete ? 'complete' : 'incomplete'),
    historical_broadcast_id: historicalBroadcastId ? String(historicalBroadcastId) : null,
    current_channel_stream_id: currentId ? String(currentId) : null,
  };
}

export function classifyExistingSkipEligibility({
  integrity = {},
  scraperVersion = null,
  historyEntry = null,
  stateRecord = null,
} = {}) {
  const historicalBroadcastId = historyEntry?.stream?.broadcast_id
    ?? historyEntry?.stream?.id
    ?? historyEntry?.historical_broadcast_id
    ?? null;
  const currentChannelStream = historyEntry?.current_channel_stream ?? null;
  const lifecycle = classifyVodLifecycle({
    integrity,
    scraperVersion,
    historicalBroadcastId,
    currentChannelStream,
  });

  const legacyLiveMatch = historicalMatchesCurrentStream(historyEntry || {});
  const explicitInProgress = stateRecord?.status === 'in_progress';
  const skipAllowed = lifecycle.complete && !legacyLiveMatch && !explicitInProgress;

  return {
    ...lifecycle,
    skip_allowed: skipAllowed,
    legacy_live_match: legacyLiveMatch,
    explicit_in_progress: explicitInProgress,
  };
}

export function resolveLifecycleTerminal({ terminalReason = null, terminalScope = null, lifecycle = null } = {}) {
  if (lifecycle?.current_broadcast_match && lifecycle?.caught_up) {
    return {
      terminal_reason: 'live_edge',
      terminal_scope: 'live_broadcast_edge',
      source_terminal_reason: terminalReason,
      source_terminal_scope: terminalScope,
    };
  }
  return {
    terminal_reason: terminalReason,
    terminal_scope: terminalScope,
    source_terminal_reason: null,
    source_terminal_scope: null,
  };
}

export function canResumeFromStats(stats = {}) {
  const integrity = stats?.integrity || {};
  const messages = Number(integrity.total_messages ?? stats.total_messages ?? 0);
  const maxOffset = Number(integrity.max_offset_seconds);
  const healthyPrefix =
    messages > 0 &&
    Number.isFinite(maxOffset) &&
    maxOffset >= 0 &&
    Number(integrity.duplicate_message_ids_in_output ?? 0) === 0 &&
    (integrity.pagination_progression ?? 'OK') === 'OK' &&
    (integrity.output_chronological_order ?? 'OK') === 'OK';
  return {
    resumable: healthyPrefix,
    max_offset_seconds: healthyPrefix ? maxOffset : null,
    messages,
  };
}

export function sortHistoryVideos(videos) {
  return [...videos].sort((a, b) => {
    const aTime = new Date(a?.timestamps?.published_at ?? a?.timestamps?.created_at ?? 0).getTime();
    const bTime = new Date(b?.timestamps?.published_at ?? b?.timestamps?.created_at ?? 0).getTime();
    if (bTime !== aTime) return bTime - aTime;
    return String(b?.id ?? '').localeCompare(String(a?.id ?? ''), undefined, { numeric: true });
  });
}

export function mergeComments(comments, key = comment => comment?.id) {
  const byId = new Map();
  for (const comment of comments) {
    const id = key(comment);
    if (!id) continue;
    if (!byId.has(String(id))) byId.set(String(id), comment);
  }
  return [...byId.values()].sort((a, b) => {
    const ao = Number(a?.offset_seconds ?? 0);
    const bo = Number(b?.offset_seconds ?? 0);
    if (ao !== bo) return ao - bo;
    return String(a?.id ?? '').localeCompare(String(b?.id ?? ''));
  });
}
