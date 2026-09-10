import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { extractVideoBroadcastAssociations, resolveHistoricalBroadcast } from './vod-broadcast.mjs';
import {
  SCRAPER_VERSION,
  DEFAULT_CHAT_OVERLAP_SECONDS,
  parseCli,
  buildChatVariables,
  buildChatSegments,
  classifyVodLifecycle,
  classifyExistingSkipEligibility,
  resolveLifecycleTerminal,
  canResumeFromStats,
  sortHistoryVideos,
  mergeComments,
  buildConcurrencyLadder,
  computeRetryDelayMs,
  runDynamicQueue,
} from './v76-core.mjs';

const CLI = parseCli(process.argv);
const STREAMER = CLI.streamer;
const BASE_URL = `https://www.twitch.tv/${STREAMER}/videos?filter=archives&sort=time`;
const GQL_URL = 'https://gql.twitch.tv/gql';
const CHAT_OPERATION = 'VideoCommentsByOffsetOrCursor';
const CHAT_HASH = 'b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a';
const DEFAULT_CLIENT_ID = 'kimne78kx3ncx6brgo4mv6wki5h1ko';
const OUT = process.env.CSTUDIO_TWITCH_OUT
  ? path.resolve(process.env.CSTUDIO_TWITCH_OUT)
  : path.join(
      process.env.USERPROFILE || process.env.HOME || '.',
      'zai-scraper',
      'data',
      STREAMER,
    );

const IMPORTANT_OPERATIONS = new Set([
  'VideoMetadata',
  'VideoPlayer_ChapterSelectButtonVideo',
  'VideoPlayer_VODSeekbarPreviewVideo',
  'ChannelVideoCore',
  'ChannelVideoShelvesQuery',
  'FilterableVideoTower_Videos',
  CHAT_OPERATION,
]);

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const nonEmpty = value => value !== null && value !== undefined && value !== '';
const num = value => {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

async function mkdirp(dir) {
  await fs.mkdir(dir, { recursive: true });
}

async function writeJson(file, value) {
  await mkdirp(path.dirname(file));
  await fs.writeFile(file, JSON.stringify(value, null, 2), 'utf8');
}

async function readJson(file, fallback) {
  try {
    return JSON.parse(await fs.readFile(file, 'utf8'));
  } catch {
    return fallback;
  }
}

function hms(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function walk(value, callback, seen = new Set()) {
  if (!value || typeof value !== 'object' || seen.has(value)) return;
  seen.add(value);
  callback(value);
  for (const child of Object.values(value)) walk(child, callback, seen);
}

function findFirst(root, predicate) {
  let hit = null;
  walk(root, object => {
    if (!hit && predicate(object)) hit = object;
  });
  return hit;
}

function findAll(root, predicate) {
  const output = [];
  walk(root, object => {
    if (predicate(object)) output.push(object);
  });
  return output;
}

function unwrapResponseData(response) {
  if (Array.isArray(response)) {
    return response.flatMap(item => {
      if (item?.data) return [item.data];
      return [item];
    });
  }
  if (response?.data) return [response.data];
  return [response];
}

function extractVideoObject(response, vodId = null) {
  return findFirst(response, value =>
    value &&
    typeof value === 'object' &&
    (vodId === null || String(value.id ?? '') === String(vodId)) &&
    (value.title !== undefined || value.owner !== undefined || value.creator !== undefined) &&
    (
      value.lengthSeconds !== undefined ||
      value.viewCount !== undefined ||
      value.publishedAt !== undefined ||
      value.createdAt !== undefined
    ),
  );
}

function extractChapterNodes(response, vodId) {
  const candidates = findAll(response, value =>
    Array.isArray(value?.edges) &&
    value.edges.some(edge =>
      String(edge?.node?.video?.id ?? vodId) === String(vodId) &&
      (
        edge?.node?.positionMilliseconds !== undefined ||
        edge?.node?.durationMilliseconds !== undefined ||
        edge?.node?.description !== undefined
      ),
    ),
  );

  const connection = candidates.find(value =>
    value.edges.some(edge => String(edge?.node?.video?.id ?? vodId) === String(vodId)),
  );

  return connection?.edges?.map(edge => edge?.node).filter(Boolean) || [];
}

function extractStoryUrl(response) {
  const hit = findFirst(response, value => typeof value?.seekPreviewsURL === 'string' && value.seekPreviewsURL);
  return hit?.seekPreviewsURL || null;
}

function extractCommentsPage(response) {
  return findFirst(response, value =>
    Array.isArray(value?.edges) &&
    value?.pageInfo &&
    typeof value.pageInfo.hasNextPage === 'boolean' &&
    (
      value?.__typename === 'VideoCommentConnection' ||
      value?.edges?.some(edge => edge?.node?.__typename === 'VideoComment')
    ),
  );
}

function normalizeChapter(node, durationSeconds) {
  const startMs = num(node.positionMilliseconds);
  const durationMs = num(node.durationMilliseconds);

  const start = startMs !== null ? Math.max(0, startMs / 1000) : 0;
  let end = durationSeconds > 0 ? durationSeconds : start;
  if (durationMs !== null) end = start + Math.max(0, durationMs / 1000);
  end = Math.min(Math.max(end, start), durationSeconds || end);

  const game = node.details?.game || null;
  const title = node.description ?? node.title ?? null;

  return {
    id: node.id ?? null,
    type: node.type ?? null,
    title,
    category: game?.displayName ?? game?.name ?? title,
    sub_description: node.subDescription ?? null,
    start_seconds: start,
    end_seconds: end,
    duration_seconds: Math.max(0, end - start),
    start_timecode: hms(start),
    end_timecode: hms(end),
    thumbnail_url: node.thumbnailURL || null,
    game: game
      ? {
          id: game.id ?? null,
          name: game.name ?? game.displayName ?? null,
          display_name: game.displayName ?? game.name ?? null,
          box_art_url: game.boxArtURL ?? null,
        }
      : null,
  };
}

function normalizeChapters(nodes, durationSeconds) {
  return nodes
    .map(node => normalizeChapter(node, durationSeconds))
    .filter(chapter => nonEmpty(chapter.title))
    .sort((a, b) => a.start_seconds - b.start_seconds)
    .filter((chapter, index, array) =>
      index === array.findIndex(other =>
        other.start_seconds === chapter.start_seconds && other.title === chapter.title,
      ),
    )
    .map((chapter, index, array) => {
      const nextStart = array[index + 1]?.start_seconds ?? null;
      let end = chapter.end_seconds;
      if (chapter.duration_seconds <= 0 && nextStart !== null) end = nextStart;
      if (index === array.length - 1 && durationSeconds > 0) {
        end = Math.max(end, durationSeconds);
      }
      end = Math.min(Math.max(end, chapter.start_seconds), durationSeconds || end);
      return {
        ...chapter,
        index,
        end_seconds: end,
        duration_seconds: Math.max(0, end - chapter.start_seconds),
        end_timecode: hms(end),
      };
    });
}

function buildSegments(chapters) {
  return chapters.map(chapter => ({
    index: chapter.index,
    category: chapter.category,
    title: chapter.title,
    start_seconds: chapter.start_seconds,
    end_seconds: chapter.end_seconds,
    duration_seconds: chapter.duration_seconds,
    start_timecode: chapter.start_timecode,
    end_timecode: chapter.end_timecode,
  }));
}

function buildCategorySummary(chapters, durationSeconds) {
  const totals = new Map();
  const counts = new Map();

  for (const chapter of chapters) {
    const name = chapter.category ?? chapter.title;
    if (!nonEmpty(name)) continue;
    totals.set(name, (totals.get(name) || 0) + chapter.duration_seconds);
    counts.set(name, (counts.get(name) || 0) + 1);
  }

  return [...totals.entries()]
    .map(([name, duration]) => ({
      name,
      duration_seconds: duration,
      duration_human: hms(duration),
      percentage: durationSeconds > 0 ? Number((duration / durationSeconds * 100).toFixed(2)) : null,
      segment_count: counts.get(name) || 0,
    }))
    .sort((a, b) => b.duration_seconds - a.duration_seconds);
}

function buildTransitions(chapters) {
  const transitions = [];
  for (let i = 1; i < chapters.length; i += 1) {
    const from = chapters[i - 1];
    const to = chapters[i];
    if (from.title === to.title && from.category === to.category) continue;
    transitions.push({
      index: transitions.length,
      from: from.title,
      to: to.title,
      from_category: from.category,
      to_category: to.category,
      at_seconds: to.start_seconds,
      at_timecode: to.start_timecode,
    });
  }
  return transitions;
}

function buildCoverage(chapters, durationSeconds) {
  if (!(durationSeconds > 0)) {
    return {
      covered_seconds: null,
      uncovered_seconds: null,
      covered_percentage: null,
    };
  }

  const intervals = chapters
    .map(chapter => [Math.max(0, chapter.start_seconds), Math.min(durationSeconds, chapter.end_seconds)])
    .filter(([start, end]) => end > start)
    .sort((a, b) => a[0] - b[0]);

  let covered = 0;
  let currentStart = null;
  let currentEnd = null;

  for (const [start, end] of intervals) {
    if (currentStart === null) {
      currentStart = start;
      currentEnd = end;
      continue;
    }
    if (start <= currentEnd) {
      currentEnd = Math.max(currentEnd, end);
    } else {
      covered += currentEnd - currentStart;
      currentStart = start;
      currentEnd = end;
    }
  }
  if (currentStart !== null) covered += currentEnd - currentStart;

  return {
    covered_seconds: covered,
    uncovered_seconds: Math.max(0, durationSeconds - covered),
    covered_percentage: Number((covered / durationSeconds * 100).toFixed(2)),
  };
}

function buildThumbnailUrls(original) {
  if (typeof original !== 'string' || !original) {
    return { original: null, '320x180': null, '640x360': null, '1280x720': null };
  }

  const base = original.replace(/-\d+x\d+(\.[a-z0-9]+(?:\?.*)?)$/i, '');
  const extension = original.match(/(\.[a-z0-9]+)(?:\?.*)?$/i)?.[1] || '.jpg';
  const make = size => `${base}-${size}${extension}`;
  return {
    original,
    '320x180': make('320x180'),
    '640x360': make('640x360'),
    '1280x720': make('1280x720'),
  };
}

async function validateUrl(url) {
  if (!url) return { url: null, valid: false, status: null, content_type: null };
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'User-Agent': 'Mozilla/5.0',
        Accept: 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
      },
      signal: AbortSignal.timeout(15000),
    });
    return {
      url,
      valid: response.ok && (response.headers.get('content-type') || '').toLowerCase().startsWith('image/'),
      status: response.status,
      content_type: response.headers.get('content-type'),
    };
  } catch (error) {
    return {
      url,
      valid: false,
      status: null,
      content_type: null,
      error: error?.message ?? String(error),
    };
  }
}

async function validateThumbnails(thumbnails) {
  const validation = {};
  for (const [name, url] of Object.entries(thumbnails)) {
    validation[name] = await validateUrl(url);
  }
  return validation;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let body = null;
  try {
    body = JSON.parse(text);
  } catch {
    // Keep raw text for diagnostics.
  }
  return {
    status: response.status,
    headers: Object.fromEntries(response.headers.entries()),
    body,
    text,
  };
}

async function fetchStoryboard(infoUrl) {
  if (!infoUrl) {
    return { available: false, url: null, status: null, variants: [] };
  }
  try {
    const response = await fetchJson(infoUrl);
    const variants = Array.isArray(response.body) ? response.body : [];
    return {
      available: response.status >= 200 && response.status < 300 && variants.length > 0,
      url: infoUrl,
      status: response.status,
      content_type: response.headers['content-type'] ?? null,
      variants: variants.map(variant => ({
        quality: variant.quality ?? null,
        frame_count: num(variant.count),
        width: num(variant.width),
        height: num(variant.height),
        rows: num(variant.rows),
        columns: num(variant.cols ?? variant.columns),
        interval_seconds: num(variant.interval),
        sprite_sheets: Array.isArray(variant.images) ? variant.images : [],
      })),
    };
  } catch (error) {
    return {
      available: false,
      url: infoUrl,
      status: null,
      variants: [],
      error: error?.message ?? String(error),
    };
  }
}

async function collectVodIds(page, limit) {
  const ids = new Set();
  const broadcastEvidenceByVod = new Map();
  const catalogOperations = new Set([
    'FilterableVideoTower_Videos',
    'ChannelVideoShelvesQuery',
  ]);
  const pendingCaptures = new Set();
  const captureErrors = [];
  const operationCounts = {};

  const addEvidence = evidence => {
    const vodId = String(evidence.vod_id);
    const rows = broadcastEvidenceByVod.get(vodId) || [];
    const key = `${evidence.broadcast_id}|${evidence.source}|${evidence.object_path ?? ''}`;
    if (!rows.some(item => `${item.broadcast_id}|${item.source}|${item.object_path ?? ''}` === key)) {
      rows.push(evidence);
      broadcastEvidenceByVod.set(vodId, rows);
    }
  };

  const responseHandler = response => {
    if (!response.url().includes('/gql')) return;

    const task = (async () => {
      const request = response.request();
      let requestBody = null;
      try {
        requestBody = request.postDataJSON();
      } catch {
        return;
      }

      const batch = Array.isArray(requestBody)
        ? requestBody
        : requestBody
          ? [requestBody]
          : [];
      if (!batch.some(item => catalogOperations.has(item?.operationName))) return;

      let responseBody = null;
      try {
        responseBody = await response.json();
      } catch (error) {
        captureErrors.push(`Catalog GraphQL JSON parse failed: ${error?.message ?? String(error)}`);
        return;
      }

      const responseBatch = Array.isArray(responseBody) ? responseBody : [responseBody];
      for (let index = 0; index < batch.length; index += 1) {
        const operation = batch[index]?.operationName;
        if (!catalogOperations.has(operation)) continue;
        operationCounts[operation] = (operationCounts[operation] || 0) + 1;

        const scopedResponse = responseBatch.length === batch.length
          ? responseBatch[index]
          : responseBody;
        const evidence = extractVideoBroadcastAssociations(scopedResponse, {
          source: `catalog.${operation}`,
        });
        evidence.forEach(addEvidence);
      }
    })().catch(error => {
      captureErrors.push(`Catalog GraphQL capture failed: ${error?.message ?? String(error)}`);
    });

    pendingCaptures.add(task);
    task.finally(() => pendingCaptures.delete(task));
  };

  page.on('response', responseHandler);
  try {
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(3000);

    for (let pass = 0; pass < 20 && ids.size < limit; pass += 1) {
      const found = await page.locator('a[href*="/videos/"]').evaluateAll(anchors =>
        anchors
          .map(anchor => anchor.getAttribute('href'))
          .filter(Boolean)
          .map(href => href.match(/\/videos\/(\d+)/)?.[1])
          .filter(Boolean),
      );

      for (const id of found) ids.add(id);
      if (ids.size >= limit) break;

      await page.mouse.wheel(0, 3000);
      await sleep(1200);
    }

    // Event listeners are async. Drain every in-flight response capture before
    // freezing the catalog evidence used by the per-VOD resolver.
    while (pendingCaptures.size > 0) {
      await Promise.allSettled([...pendingCaptures]);
    }
  } finally {
    page.off('response', responseHandler);
  }

  const vodIds = [...ids].slice(0, limit);
  return {
    vodIds,
    broadcastEvidenceByVod: Object.fromEntries(
      vodIds.map(vodId => [vodId, broadcastEvidenceByVod.get(String(vodId)) || []]),
    ),
    diagnostics: {
      captured_operations: operationCounts,
      videos_with_broadcast_evidence: broadcastEvidenceByVod.size,
      selected_vods_with_broadcast_evidence: vodIds.filter(
        vodId => (broadcastEvidenceByVod.get(String(vodId)) || []).length > 0,
      ).length,
      errors: captureErrors,
    },
  };
}

async function fetchExactVodBroadcast({
  context,
  page,
  vodId,
  clientId,
  requestHeaders = {},
  authorization = null,
}) {
  const query = `query V75VodBroadcast($videoId: ID!) {
    video(id: $videoId) {
      id
      broadcastIdentifier {
        id
        __typename
      }
      __typename
    }
  }`;

  const diagnostic = {
    attempted: true,
    method: 'raw_graphql_video_by_id',
    vod_id: String(vodId),
    http_status: null,
    graphQL_error: null,
    transport_error: null,
    evidence_count: 0,
  };

  try {
    const response = await context.request.post(`${GQL_URL}#origin=twilight`, {
      headers: {
        'Client-ID': clientId || DEFAULT_CLIENT_ID,
        'Content-Type': 'application/json',
        Accept: 'application/json',
        Origin: 'https://www.twitch.tv',
        Referer: `https://www.twitch.tv/videos/${vodId}`,
        'User-Agent': await page.evaluate(() => navigator.userAgent).catch(() => 'Mozilla/5.0'),
        ...(requestHeaders['client-integrity'] ? { 'Client-Integrity': requestHeaders['client-integrity'] } : {}),
        ...(requestHeaders['x-device-id'] ? { 'X-Device-Id': requestHeaders['x-device-id'] } : {}),
        ...(authorization ? { Authorization: authorization } : {}),
      },
      data: {
        operationName: 'V75VodBroadcast',
        variables: { videoId: String(vodId) },
        query,
      },
      timeout: 30000,
    });

    diagnostic.http_status = response.status();
    const text = await response.text();
    let body = null;
    try { body = JSON.parse(text); } catch { body = null; }
    diagnostic.graphQL_error = summarizeGraphQlError(body);

    const evidence = extractVideoBroadcastAssociations(body, {
      source: 'direct.graphql.video(id)',
      vodId: String(vodId),
    });
    diagnostic.evidence_count = evidence.length;

    return { evidence, diagnostic };
  } catch (error) {
    diagnostic.transport_error = error?.message ?? String(error);
    return { evidence: [], diagnostic };
  }
}

function historicalBroadcastCandidate(evidence) {
  if (!evidence || !nonEmpty(evidence.broadcast_id)) return null;
  return {
    id: String(evidence.broadcast_id),
    viewers_count: null,
    game: null,
    type: null,
    created_at: null,
    is_live: null,
    source: evidence.source ?? null,
    role: 'historical_broadcast',
    vod_id: evidence.vod_id ?? null,
    object_path: evidence.object_path ?? null,
    evidence_kind: evidence.evidence_kind ?? 'vod_scoped_video_broadcast_identifier',
  };
}

function streamCandidate(value, source = 'capture') {
  if (!value || typeof value !== 'object') return null;

  const hasStreamTypename = value.__typename === 'Stream';
  const hasStreamShape = value.id !== undefined && (
    value.viewersCount !== undefined ||
    value.createdAt !== undefined ||
    value.game !== undefined ||
    value.type !== undefined ||
    value.isLive !== undefined
  );
  if (!hasStreamTypename && !hasStreamShape) return null;

  const id = value.id !== null && value.id !== undefined ? String(value.id) : null;
  if (!id) return null;

  return {
    id,
    viewers_count: num(value.viewersCount),
    game: value.game?.displayName ?? value.game?.name ?? null,
    type: value.type ?? null,
    created_at: value.createdAt ?? null,
    is_live: value.isLive ?? null,
    source,
    role: 'stream_object',
  };
}

function extractStreamInfo({ vodId, video, channelVideo, capture, catalogEvidence = [] }) {
  const historicalResolution = resolveHistoricalBroadcast({
    vodId,
    video,
    channelVideo,
    graphqlRecords: capture,
    catalogEvidence,
  });

  const candidates = [];
  const seen = new Set();
  const add = (value, source) => {
    const candidate = streamCandidate(value, source);
    if (!candidate || seen.has(`${candidate.id}|${candidate.source}`)) return;
    seen.add(`${candidate.id}|${candidate.source}`);
    candidates.push(candidate);
  };

  for (const evidence of historicalResolution.evidence) {
    const candidate = historicalBroadcastCandidate(evidence);
    if (!candidate) continue;
    const key = `${candidate.id}|${candidate.source}|${candidate.object_path ?? ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    candidates.push(candidate);
  }

  // Current channel stream information is diagnostic only. It can never fill
  // the historical broadcast ID of an archived VOD.
  for (const [key, value] of [
    ['video.owner.stream', video?.owner?.stream],
    ['video.creator.stream', video?.creator?.stream],
    ['video.user.stream', video?.user?.stream],
    ['channel_video.owner.stream', channelVideo?.owner?.stream],
    ['channel_video.creator.stream', channelVideo?.creator?.stream],
    ['channel_video.user.stream', channelVideo?.user?.stream],
  ]) {
    add(value, key);
  }

  walk(capture, value => add(value, 'capture'));

  const currentChannelStream = streamCandidate(
    video?.owner?.stream || video?.creator?.stream || channelVideo?.owner?.stream,
    'channel.current_stream',
  );

  const primary = historicalResolution.id
    ? historicalBroadcastCandidate({
        vod_id: String(vodId),
        broadcast_id: historicalResolution.id,
        source: historicalResolution.primary_source,
        object_path: historicalResolution.evidence[0]?.object_path ?? null,
        evidence_kind: 'vod_scoped_video_broadcast_identifier',
      })
    : null;

  return {
    primary,
    historical_broadcast_id: historicalResolution.id,
    historical_resolution: historicalResolution,
    current_channel_stream: currentChannelStream,
    candidates,
  };
}

function analyzeChatIntegrity(comments, chatRawPages, durationSeconds, pagesScraped, chatErrors, terminalContext = {}) {
  const rawEdges = [];
  const pageSummaries = [];

  for (const pageRecord of Array.isArray(chatRawPages) ? chatRawPages : []) {
    const page = extractCommentsPage(pageRecord.response);
    const edges = Array.isArray(page?.edges) ? page.edges : [];
    const offsets = edges
      .map(edge => num(edge?.node?.contentOffsetSeconds))
      .filter(value => value !== null);

    const firstOffset = offsets.length ? offsets[0] : null;
    const lastOffset = offsets.length ? offsets.at(-1) : null;

    pageSummaries.push({
      page_number: pageRecord.page_number ?? null,
      source: pageRecord.source ?? null,
      http_status: pageRecord.http_status ?? null,
      edge_count: edges.length,
      first_offset_seconds: firstOffset,
      last_offset_seconds: lastOffset,
      has_next_page: page?.pageInfo?.hasNextPage ?? null,
    });

    for (const edge of edges) {
      const id = edge?.node?.id;
      if (id) {
        rawEdges.push({
          id: String(id),
          offset_seconds: num(edge?.node?.contentOffsetSeconds),
          page_number: pageRecord.page_number ?? null,
        });
      }
    }
  }

  const rawIdCounts = new Map();
  for (const row of rawEdges) {
    rawIdCounts.set(row.id, (rawIdCounts.get(row.id) ?? 0) + 1);
  }

  // Twitch can return an overlapping time window on adjacent offset pages.
  // These repeated raw IDs are expected transport overlap; the final output
  // is deduplicated by message ID before it is written.
  let rawRepeatedEdgeCount = 0;
  let rawRepeatedMessageIds = 0;
  for (const count of rawIdCounts.values()) {
    if (count > 1) {
      rawRepeatedMessageIds += 1;
      rawRepeatedEdgeCount += count - 1;
    }
  }

  const successfulPages = pageSummaries.filter(page =>
    page.http_status >= 200 &&
    page.http_status < 300 &&
    page.edge_count > 0,
  );

  const successfulPageOffsets = successfulPages
    .map(page => page.last_offset_seconds)
    .filter(value => value !== null);

  let paginationProgressionOk = true;
  for (let index = 1; index < successfulPageOffsets.length; index += 1) {
    if (successfulPageOffsets[index] <= successfulPageOffsets[index - 1]) {
      paginationProgressionOk = false;
      break;
    }
  }

  const commentOffsets = comments
    .map(comment => num(comment.offset_seconds))
    .filter(value => value !== null);

  const minOffset = commentOffsets.length ? Math.min(...commentOffsets) : null;
  const maxOffset = commentOffsets.length ? Math.max(...commentOffsets) : null;

  let outputChronologicalOrderOk = true;
  for (let index = 1; index < commentOffsets.length; index += 1) {
    if (commentOffsets[index] < commentOffsets[index - 1]) {
      outputChronologicalOrderOk = false;
      break;
    }
  }

  const terminalPage = pageSummaries.at(-1) ?? null;
  const terminalIsClean = terminalPage?.has_next_page === false;

  const lastError = Array.isArray(chatErrors) && chatErrors.length
    ? chatErrors.at(-1)
    : null;

  const uniqueOutputIds = new Set(
    comments.map(comment => comment.id).filter(nonEmpty),
  );

  return {
    total_messages: comments.length,
    unique_message_ids: uniqueOutputIds.size,
    duplicate_message_ids_in_output: comments.length - uniqueOutputIds.size,
    raw_edges: rawEdges.length,
    raw_unique_message_ids: rawIdCounts.size,
    raw_repeated_edge_count: rawRepeatedEdgeCount,
    raw_repeated_message_ids: rawRepeatedMessageIds,
    pages_scraped: pagesScraped,
    raw_page_attempts: pageSummaries.length,
    successful_raw_pages: successfulPages.length,
    pagination_progression: paginationProgressionOk ? 'OK' : 'FAIL',
    output_chronological_order: outputChronologicalOrderOk ? 'OK' : 'FAIL',
    min_offset_seconds: minOffset,
    max_offset_seconds: maxOffset,
    duration_seconds: durationSeconds,
    beyond_duration_seconds: maxOffset !== null ? Math.max(0, maxOffset - durationSeconds) : 0,
    terminal_page_has_next: terminalPage?.has_next_page ?? null,
    terminal_page_clean: terminalIsClean,
    terminal_scope: terminalContext.scope ?? (terminalIsClean ? 'chat_connection_reported_end' : 'undetermined'),
    terminal_boundary_detected: !!terminalContext.boundaryDetected,
    errors_count: Array.isArray(chatErrors) ? chatErrors.length : 0,
    last_error: lastError,
    page_summaries: pageSummaries,
  };
}

function getChatConnectionFromCapture(gql, important) {
  const records = [
    ...(Array.isArray(gql) ? gql.filter(record =>
      Array.isArray(record?.operation_names) && record.operation_names.includes(CHAT_OPERATION),
    ).map(record => record.response) : []),
    important?.[CHAT_OPERATION],
  ].filter(value => value !== undefined && value !== null);

  for (const response of records) {
    const page = extractCommentsPage(response);
    if (page) return { page, response };
  }
  return { page: null, response: null };
}

function commentsPageIdentity(page) {
  const ids = Array.isArray(page?.edges)
    ? page.edges.map(edge => edge?.node?.id).filter(Boolean).slice(0, 3)
    : [];
  return ids.join('|');
}

function summarizeGraphQlError(body) {
  if (!body) return null;
  const errors = findAll(body, value => Array.isArray(value?.errors) && value.errors.length > 0)
    .flatMap(value => value.errors)
    .slice(0, 5);
  if (!errors.length) return null;
  return errors.map(error => error?.message || JSON.stringify(error)).join(' | ');
}

function normalizeMetadata(video, chapters, storyboard, thumbnailValidation, scrapedAt, streamInfo) {
  const owner = video.owner || video.creator || video.user || {};
  const stream = streamInfo?.primary || {};
  const game = video.game || {};
  const duration = num(video.lengthSeconds) ?? 0;
  const thumbnails = buildThumbnailUrls(video.previewThumbnailURL || video.thumbnailURL || null);
  const segments = buildSegments(chapters);
  const categorySummary = buildCategorySummary(chapters, duration);
  const transitions = buildTransitions(chapters);

  return {
    id: String(video.id),
    url: `https://www.twitch.tv/videos/${video.id}`,
    title: video.title ?? null,
    description: video.description ?? null,
    broadcaster: {
      id: owner.id ?? null,
      login: owner.login ?? null,
      display_name: owner.displayName ?? owner.display_name ?? null,
      avatar_url: owner.profileImageURL ?? owner.avatar_url ?? video.user?.profileImageURL ?? null,
      primary_color: owner.primaryColorHex ?? owner.primary_color ?? video.user?.primaryColorHex ?? null,
    },
    timestamps: {
      created_at: video.createdAt ?? null,
      published_at: video.publishedAt ?? null,
      recorded_at: video.recordedAt ?? null,
    },
    duration: {
      seconds: duration,
      timecode: hms(duration),
    },
    views: {
      current: num(video.viewCount),
    },
    language: video.language ?? null,
    broadcast_type: video.broadcastType ?? null,
    stream: {
      id: streamInfo?.historical_broadcast_id ?? null,
      broadcast_id: streamInfo?.historical_broadcast_id ?? null,
      viewers_count_at_scrape: null,
      candidates: streamInfo?.candidates ?? [],
      primary_source: stream.source ?? null,
      primary_role: stream.role ?? null,
      resolution: streamInfo?.historical_resolution ?? null,
    },
    current_channel_stream: streamInfo?.current_channel_stream ?? null,
    game: {
      id: game.id ?? null,
      name: game.name ?? game.displayName ?? null,
      display_name: game.displayName ?? game.name ?? null,
      slug: game.slug ?? null,
      box_art_url: game.boxArtURL ?? null,
    },
    tags: Array.isArray(video.tags) ? video.tags : [],
    content_tags: Array.isArray(video.contentTags) ? video.contentTags : [],
    thumbnails: {
      ...thumbnails,
      validation: thumbnailValidation,
    },
    playback: {
      storyboard_url: storyboard?.url ?? null,
      storyboard_available: !!storyboard?.available,
    },
    chapters,
    segments,
    category_summary: categorySummary,
    derived: {
      dominant_category: categorySummary[0]?.name ?? chapters[0]?.title ?? game.name ?? null,
      category_count: categorySummary.length,
      chapter_count: chapters.length,
      transition_count: transitions.length,
      transitions,
      coverage: buildCoverage(chapters, duration),
    },
    storyboard,
    scraper_version: SCRAPER_VERSION,
    sources: {
      metadata: 'VideoMetadata',
      chapters: 'VideoPlayer_ChapterSelectButtonVideo',
      storyboard: 'VideoPlayer_VODSeekbarPreviewVideo',
      channel_video: 'ChannelVideoCore',
      broadcast_identifier: streamInfo?.historical_resolution?.primary_source ?? null,
    },
    scraped_at: scrapedAt,
  };
}

function normalizeComment(edge, chapters) {
  const node = edge?.node || {};
  const message = node.message || {};
  const fragments = Array.isArray(message.fragments)
    ? message.fragments.map(fragment => ({
        type: fragment.emote ? 'emote' : 'text',
        text: fragment.text ?? '',
        emote_id: fragment.emote?.emoteID ?? fragment.emote?.id ?? null,
        from: fragment.emote?.from ?? null,
      }))
    : [];

  const offset = num(node.contentOffsetSeconds) ?? 0;
  const chapter = chapters.find(item =>
    offset >= item.start_seconds && offset < item.end_seconds,
  ) || null;

  return {
    id: node.id ?? null,
    cursor: edge?.cursor ?? null,
    offset_seconds: offset,
    timestamp: hms(offset),
    created_at: node.createdAt ?? null,
    user: {
      id: node.commenter?.id ?? null,
      login: node.commenter?.login ?? null,
      display_name: node.commenter?.displayName ?? null,
    },
    message: fragments.map(fragment => fragment.text).join(''),
    fragments,
    badges: Array.isArray(message.userBadges)
      ? message.userBadges.map(badge => ({
          set_id: badge.setID ?? null,
          version: badge.version ?? null,
          id: badge.id ?? null,
        }))
      : [],
    user_color: message.userColor ?? null,
    chapter_index: chapter?.index ?? null,
    chapter_title: chapter?.title ?? null,
  };
}

function chatStats(comments, chapters, duration) {
  const users = new Set(
    comments.map(comment => comment.user.id || comment.user.login).filter(nonEmpty),
  );
  const emotes = comments.reduce(
    (total, comment) => total + comment.fragments.filter(fragment => fragment.type === 'emote').length,
    0,
  );
  const subscriberMessages = comments.filter(comment =>
    comment.badges.some(badge => /subscriber/i.test(String(badge.set_id))),
  ).length;
  const botMessages = comments.filter(comment =>
    comment.badges.some(badge => /bot/i.test(String(badge.set_id))),
  ).length;

  const byChapter = chapters.map(chapter => {
    const rows = comments.filter(comment => comment.chapter_index === chapter.index);
    const unique = new Set(
      rows.map(comment => comment.user.id || comment.user.login).filter(nonEmpty),
    );
    const chapterDuration = Math.max(0, chapter.end_seconds - chapter.start_seconds);
    return {
      chapter_index: chapter.index,
      title: chapter.title,
      category: chapter.category,
      start_seconds: chapter.start_seconds,
      end_seconds: chapter.end_seconds,
      duration_seconds: chapterDuration,
      total_messages: rows.length,
      unique_users: unique.size,
      messages_per_minute: rows.length / Math.max(chapterDuration / 60, 1 / 60),
      emote_count: rows.reduce(
        (total, row) => total + row.fragments.filter(fragment => fragment.type === 'emote').length,
        0,
      ),
    };
  });

  return {
    total_messages: comments.length,
    unique_users: users.size,
    duration_seconds: duration,
    messages_per_minute: comments.length / Math.max(duration / 60, 1 / 60),
    emote_count: emotes,
    subscriber_messages: subscriberMessages,
    bot_messages: botMessages,
    by_chapter: byChapter,
  };
}

function normalizeHistory(raw) {
  const videos = {};

  if (raw && Array.isArray(raw.videos)) {
    for (const video of raw.videos) {
      if (video?.id) videos[String(video.id)] = video;
    }
  }

  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    for (const [key, value] of Object.entries(raw)) {
      if (/^\d+$/.test(key) && value && typeof value === 'object' && value.id) {
        videos[String(value.id)] = value;
      }
    }
  }

  return videos;
}

function buildHistoryDocument(channel, videos, updatedAt) {
  const sorted = sortHistoryVideos(Object.values(videos));

  return {
    schema_version: 2,
    channel,
    updated_at: updatedAt,
    count: sorted.length,
    videos: sorted,
  };
}

function buildChatRawRecord({ vodId, pageNumber, variables, responseBody, status, clientId, source, requestHeaders = null, persistedQueryHash = CHAT_HASH, workerId = null, segmentId = null, phase = null }) {
  return {
    source,
    page_number: pageNumber,
    operation_names: [CHAT_OPERATION],
    request: {
      operationName: CHAT_OPERATION,
      variables,
      extensions: {
        persistedQuery: {
          version: 1,
          sha256Hash: persistedQueryHash,
        },
      },
    },
    response: responseBody,
    http_status: status,
    client_id: clientId,
    request_headers: requestHeaders,
    vod_id: String(vodId),
    timestamp: new Date().toISOString(),
    worker_id: workerId,
    segment_id: segmentId,
    phase,
  };
}


async function fileExists(file) {
  try {
    await fs.access(file);
    return true;
  } catch {
    return false;
  }
}

async function fileSize(file) {
  try {
    return (await fs.stat(file)).size;
  } catch {
    return null;
  }
}

function emptyVodCatalog(vodIds = []) {
  return {
    vodIds: vodIds.map(String),
    broadcastEvidenceByVod: Object.fromEntries(vodIds.map(id => [String(id), []])),
    diagnostics: {
      mode: 'specific_vod',
      captured_operations: {},
      videos_with_broadcast_evidence: 0,
      selected_vods_with_broadcast_evidence: 0,
      errors: [],
    },
  };
}

async function evaluateExistingVod(vodId, historyVideos, state = null) {
  const id = String(vodId);
  const files = {
    raw: path.join(OUT, 'raw', `${id}.json`),
    discovery: path.join(OUT, 'discovery', `${id}.json`),
    chat: path.join(OUT, 'chat', `${id}.json`),
    stats: path.join(OUT, 'chat', `${id}-stats.json`),
  };
  const presenceEntries = await Promise.all(
    Object.entries(files).map(async ([name, file]) => [name, await fileExists(file)]),
  );
  const present = Object.fromEntries(presenceEntries);
  const allFilesPresent = Object.values(present).every(Boolean);
  const sizeEntries = await Promise.all(
    Object.entries(files).map(async ([name, file]) => [name, present[name] ? await fileSize(file) : null]),
  );
  const fileSizes = Object.fromEntries(sizeEntries);
  const historyEntry = historyVideos[id] || null;
  const stats = present.stats ? await readJson(files.stats, null) : null;
  const version = historyEntry?.scraper_version ?? null;
  const stateRecord = state?.vods?.[id] || null;
  const classification = stats
    ? classifyExistingSkipEligibility({
        integrity: stats.integrity || {},
        scraperVersion: version,
        historyEntry,
        stateRecord,
      })
    : { complete: false, skip_allowed: false, compatible_version: false };

  // Fast path for outputs previously verified by V7.5+. A V7.5 record that
  // captured the same historical/current stream is deliberately NOT eligible
  // for this fast path: it may have been a live VOD incorrectly marked complete.
  const fingerprintsMatch =
    classification.skip_allowed === true &&
    stateRecord?.complete === true &&
    stateRecord?.file_sizes &&
    Object.entries(fileSizes).every(([name, size]) =>
      size !== null && Number(stateRecord.file_sizes?.[name]) === Number(size),
    );

  let chatDocumentValid = false;
  if (allFilesPresent && classification.skip_allowed && classification.compatible_version) {
    if (fingerprintsMatch) {
      chatDocumentValid = true;
    } else {
      const chatDoc = await readJson(files.chat, null);
      const comments = Array.isArray(chatDoc?.comments) ? chatDoc.comments : null;
      const expected = Number(stats?.integrity?.total_messages ?? stats?.total_messages ?? -1);
      chatDocumentValid =
        !!chatDoc &&
        comments !== null &&
        comments.length === expected &&
        Number(chatDoc.total ?? comments.length) === expected;
    }
  }

  return {
    vod_id: id,
    files,
    present,
    file_sizes: fileSizes,
    fingerprints_match: fingerprintsMatch,
    chat_document_valid: chatDocumentValid,
    all_files_present: allFilesPresent,
    history_entry: historyEntry,
    stats,
    version,
    complete:
      allFilesPresent &&
      !!historyEntry &&
      classification.skip_allowed &&
      classification.compatible_version &&
      chatDocumentValid,
    lifecycle_status: classification.status ?? 'incomplete',
    classification,
  };
}

async function loadResumeSeed(existing) {
  if (!existing?.stats || !existing?.present?.chat || !existing?.present?.raw) return null;
  const resumeCheck = canResumeFromStats(existing.stats);
  if (!resumeCheck.resumable) return null;

  const chatDoc = await readJson(existing.files.chat, null);
  if (!chatDoc || !Array.isArray(chatDoc.comments) || chatDoc.comments.length === 0) return null;

  const rawDoc = await readJson(existing.files.raw, null);
  const successfulRawPages = Array.isArray(rawDoc?.chat_pagination)
    ? rawDoc.chat_pagination.filter(record => {
        const page = extractCommentsPage(record?.response);
        return !!page &&
          Number(record?.http_status ?? 0) >= 200 &&
          Number(record?.http_status ?? 0) < 300 &&
          Array.isArray(page.edges) &&
          page.edges.length > 0;
      })
    : [];

  const comments = mergeComments(chatDoc.comments);
  const maxOffset = Math.max(
    resumeCheck.max_offset_seconds ?? 0,
    ...comments.map(comment => num(comment?.offset_seconds) ?? 0),
  );

  return {
    comments,
    max_offset_seconds: maxOffset,
    previous_total_messages: comments.length,
    previous_scraper_version: chatDoc.scraper_version ?? existing.version ?? null,
    previous_terminal_reason: existing.stats?.integrity?.terminal_reason ?? null,
    previous_errors: Array.isArray(chatDoc.errors) ? chatDoc.errors : [],
    raw_pages: successfulRawPages,
  };
}

function findCapturedChatOperation(gql) {
  for (const record of Array.isArray(gql) ? gql : []) {
    const requestBatch = Array.isArray(record?.request)
      ? record.request
      : record?.request
        ? [record.request]
        : [];
    const responseBatch = Array.isArray(record?.response)
      ? record.response
      : record?.response !== undefined
        ? [record.response]
        : [];

    for (let index = 0; index < requestBatch.length; index += 1) {
      const requestItem = requestBatch[index];
      if (requestItem?.operationName !== CHAT_OPERATION) continue;
      const scopedResponse = responseBatch.length === requestBatch.length
        ? responseBatch[index]
        : record.response;
      const pageData = extractCommentsPage(scopedResponse);
      if (!pageData) continue;
      return {
        request: requestItem,
        response: scopedResponse,
        page: pageData,
        http_status: record.http_status ?? 200,
        source_record: record,
      };
    }
  }
  return null;
}

function addPageComments(pageData, chapters, destination) {
  const output = [];
  const edges = Array.isArray(pageData?.edges) ? pageData.edges : [];
  for (const edge of edges) {
    const comment = normalizeComment(edge, chapters);
    if (comment?.id) output.push(comment);
  }
  destination.push(...output);
  return output.length;
}

function maxPageOffset(pageData) {
  const offsets = (pageData?.edges || [])
    .map(edge => num(edge?.node?.contentOffsetSeconds))
    .filter(value => value !== null);
  return offsets.length ? Math.max(...offsets) : null;
}

function minPageOffset(pageData) {
  const offsets = (pageData?.edges || [])
    .map(edge => num(edge?.node?.contentOffsetSeconds))
    .filter(value => value !== null);
  return offsets.length ? Math.min(...offsets) : null;
}

function buildChatHeaders({ clientId, requestHeaders, authorization, vodId, userAgent }) {
  return {
    'Client-ID': clientId,
    'Content-Type': 'application/json',
    Accept: 'application/json',
    Origin: 'https://www.twitch.tv',
    Referer: `https://www.twitch.tv/videos/${vodId}`,
    'User-Agent': userAgent || 'Mozilla/5.0',
    ...(requestHeaders['client-integrity'] ? { 'Client-Integrity': requestHeaders['client-integrity'] } : {}),
    ...(requestHeaders['x-device-id'] ? { 'X-Device-Id': requestHeaders['x-device-id'] } : {}),
    ...(authorization ? { Authorization: authorization } : {}),
  };
}

async function fetchChatOffsetPage({
  context,
  vodId,
  offset,
  variableTemplate,
  persistedQueryHash,
  clientId,
  requestHeaders,
  authorization,
  userAgent,
  workerId,
  segmentId,
  phase,
  nextPageNumber,
}) {
  const attempts = [];
  let rateLimited = false;
  let lastTransportError = null;

  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const variables = buildChatVariables(variableTemplate, vodId, offset);
    const payload = [{
      operationName: CHAT_OPERATION,
      variables,
      extensions: {
        persistedQuery: {
          version: 1,
          sha256Hash: persistedQueryHash,
        },
      },
    }];

    let status = null;
    let body = null;
    let graphQlError = null;
    let transportError = null;
    let retryAfterSeconds = null;
    try {
      const response = await context.request.post(`${GQL_URL}#origin=twilight`, {
        headers: buildChatHeaders({
          clientId,
          requestHeaders,
          authorization,
          vodId,
          userAgent,
        }),
        data: payload,
        timeout: 30000,
      });
      status = response.status();
      rateLimited = rateLimited || status === 429;
      const responseHeaders = response.headers();
      const retryAfterHeader = responseHeaders?.['retry-after'];
      if (retryAfterHeader !== undefined && retryAfterHeader !== null) {
        const parsedRetryAfter = Number(retryAfterHeader);
        if (Number.isFinite(parsedRetryAfter) && parsedRetryAfter > 0) {
          retryAfterSeconds = parsedRetryAfter;
        } else {
          const retryAt = Date.parse(String(retryAfterHeader));
          if (Number.isFinite(retryAt)) {
            retryAfterSeconds = Math.max(0, (retryAt - Date.now()) / 1000);
          }
        }
      }
      const text = await response.text();
      try { body = JSON.parse(text); } catch { body = text; }
      graphQlError = summarizeGraphQlError(body);
    } catch (error) {
      transportError = error?.message ?? String(error);
      lastTransportError = transportError;
    }

    const pageData = extractCommentsPage(body);
    const rawRecord = buildChatRawRecord({
      vodId,
      pageNumber: nextPageNumber(),
      variables,
      responseBody: body,
      status,
      clientId,
      source: `parallel_${segmentId}_offset_${offset}_attempt_${attempt}`,
      requestHeaders: {
        ...requestHeaders,
        'client-id': clientId,
        'content-type': 'application/json',
        accept: 'application/json',
        origin: 'https://www.twitch.tv',
        referer: `https://www.twitch.tv/videos/${vodId}`,
      },
      persistedQueryHash,
      workerId,
      segmentId,
      phase,
    });
    attempts.push(rawRecord);

    if (pageData) {
      return {
        ok: true,
        page: pageData,
        raw_records: attempts,
        status,
        graphQL_error: graphQlError,
        transport_error: transportError,
        rate_limited: rateLimited,
      };
    }

    if (attempt < 3) {
      const backoff = computeRetryDelayMs({
        attempt,
        status,
        retryAfterSeconds,
      });
      await sleep(backoff);
    }
  }

  const last = attempts.at(-1);
  return {
    ok: false,
    page: null,
    raw_records: attempts,
    status: last?.http_status ?? null,
    graphQL_error: summarizeGraphQlError(last?.response),
    transport_error: lastTransportError,
    rate_limited: rateLimited,
  };
}

async function downloadChatSegment({
  segment,
  phase,
  workerId = null,
  context,
  vodId,
  duration,
  chapters,
  variableTemplate,
  persistedQueryHash,
  clientId,
  requestHeaders,
  authorization,
  userAgent,
  nextPageNumber,
}) {
  const comments = [];
  const rawPages = [];
  const errors = [];
  let offset = Math.max(0, Math.floor(segment.fetch_start));
  let lastSuccessfulOffset = null;
  let firstReturnedOffset = null;
  let pages = 0;
  let progressionOk = true;
  let rateLimited = false;
  let terminalReason = null;
  let terminalScope = null;
  let terminalProbe = null;

  for (let guard = 0; guard < 10000; guard += 1) {
    const requestedOffset = offset;
    const fetched = await fetchChatOffsetPage({
      context,
      vodId,
      offset: requestedOffset,
      variableTemplate,
      persistedQueryHash,
      clientId,
      requestHeaders,
      authorization,
      userAgent,
      workerId: workerId ?? (segment.index + 1),
      segmentId: segment.id,
      phase,
      nextPageNumber,
    });
    rawPages.push(...fetched.raw_records);
    rateLimited = rateLimited || fetched.rate_limited;

    if (!fetched.ok) {
      const atOrPastDuration = duration > 0 && requestedOffset >= duration;
      const nearEnd = lastSuccessfulOffset !== null && lastSuccessfulOffset >= Math.max(0, duration - 60);
      if (segment.is_final && atOrPastDuration && nearEnd) {
        terminalReason = 'post_duration_api_boundary';
        terminalScope = 'archive_duration_boundary';
        terminalProbe = {
          offset_seconds: requestedOffset,
          attempts: fetched.raw_records.length,
          graphQL_error: fetched.graphQL_error,
          transport_error: fetched.transport_error,
          http_status: fetched.status,
        };
        return {
          segment,
          worker_id: workerId,
          ok: true,
          comments,
          raw_pages: rawPages,
          pages,
          progression_ok: progressionOk,
          rate_limited: rateLimited,
          first_returned_offset: firstReturnedOffset,
          last_successful_offset: lastSuccessfulOffset,
          terminal_reason: terminalReason,
          terminal_scope: terminalScope,
          terminal_probe: terminalProbe,
          errors,
        };
      }

      const reason = fetched.graphQL_error
        ? `GraphQL at offset ${requestedOffset}: ${fetched.graphQL_error}`
        : fetched.transport_error
          ? `Chat request failed at offset ${requestedOffset}: ${fetched.transport_error}`
          : `No valid comments page at offset ${requestedOffset} (HTTP ${fetched.status ?? 'n/a'})`;
      errors.push(reason);
      return {
        segment,
        worker_id: workerId,
        ok: false,
        comments,
        raw_pages: rawPages,
        pages,
        progression_ok: false,
        rate_limited: rateLimited,
        first_returned_offset: firstReturnedOffset,
        last_successful_offset: lastSuccessfulOffset,
        terminal_reason: 'segment_request_failed',
        terminal_scope: 'request_error',
        terminal_probe: {
          offset_seconds: requestedOffset,
          attempts: fetched.raw_records.length,
          graphQL_error: fetched.graphQL_error,
          transport_error: fetched.transport_error,
          http_status: fetched.status,
        },
        errors,
      };
    }

    const pageData = fetched.page;
    pages += 1;
    addPageComments(pageData, chapters, comments);
    const firstOffset = minPageOffset(pageData);
    const lastOffset = maxPageOffset(pageData);
    if (firstReturnedOffset === null && firstOffset !== null) firstReturnedOffset = firstOffset;

    const hasNextPage = !!pageData?.pageInfo?.hasNextPage;
    if (lastOffset === null) {
      if (!hasNextPage) {
        terminalReason = 'hasNextPage_false';
        terminalScope = 'chat_connection_reported_end';
        return {
          segment,
          worker_id: workerId,
          ok: true,
          comments,
          raw_pages: rawPages,
          pages,
          progression_ok: progressionOk,
          rate_limited: rateLimited,
          first_returned_offset: firstReturnedOffset,
          last_successful_offset: lastSuccessfulOffset,
          terminal_reason: terminalReason,
          terminal_scope: terminalScope,
          terminal_probe: null,
          errors,
        };
      }
      errors.push(`Segment ${segment.id} returned no offsets while hasNextPage=true`);
      return {
        segment,
        worker_id: workerId,
        ok: false,
        comments,
        raw_pages: rawPages,
        pages,
        progression_ok: false,
        rate_limited: rateLimited,
        first_returned_offset: firstReturnedOffset,
        last_successful_offset: lastSuccessfulOffset,
        terminal_reason: 'segment_no_progress',
        terminal_scope: 'request_error',
        terminal_probe: null,
        errors,
      };
    }

    if (lastSuccessfulOffset !== null && lastOffset <= lastSuccessfulOffset) {
      progressionOk = false;
    }
    lastSuccessfulOffset = lastOffset;

    if (!segment.is_final && lastOffset >= segment.fetch_end) {
      return {
        segment,
        worker_id: workerId,
        ok: true,
        comments,
        raw_pages: rawPages,
        pages,
        progression_ok: progressionOk,
        rate_limited: rateLimited,
        first_returned_offset: firstReturnedOffset,
        last_successful_offset: lastSuccessfulOffset,
        terminal_reason: 'segment_end_reached',
        terminal_scope: 'parallel_segment_coverage',
        terminal_probe: null,
        errors,
      };
    }

    if (!hasNextPage) {
      terminalReason = 'hasNextPage_false';
      terminalScope = 'chat_connection_reported_end';
      return {
        segment,
        worker_id: workerId,
        ok: true,
        comments,
        raw_pages: rawPages,
        pages,
        progression_ok: progressionOk,
        rate_limited: rateLimited,
        first_returned_offset: firstReturnedOffset,
        last_successful_offset: lastSuccessfulOffset,
        terminal_reason: terminalReason,
        terminal_scope: terminalScope,
        terminal_probe: null,
        errors,
      };
    }

    const nextOffset = lastOffset + 1;
    if (nextOffset <= requestedOffset) {
      progressionOk = false;
      errors.push(`Segment ${segment.id} did not advance: requested ${requestedOffset}, returned ${lastOffset}`);
      return {
        segment,
        worker_id: workerId,
        ok: false,
        comments,
        raw_pages: rawPages,
        pages,
        progression_ok: false,
        rate_limited: rateLimited,
        first_returned_offset: firstReturnedOffset,
        last_successful_offset: lastSuccessfulOffset,
        terminal_reason: 'segment_no_progress',
        terminal_scope: 'request_error',
        terminal_probe: null,
        errors,
      };
    }

    offset = nextOffset;
    await sleep(100);
  }

  errors.push(`Segment ${segment.id} exceeded the 10000-page safety guard`);
  return {
    segment,
    worker_id: workerId,
    ok: false,
    comments,
    raw_pages: rawPages,
    pages,
    progression_ok: false,
    rate_limited: rateLimited,
    first_returned_offset: firstReturnedOffset,
    last_successful_offset: lastSuccessfulOffset,
    terminal_reason: 'segment_page_guard',
    terminal_scope: 'request_error',
    terminal_probe: null,
    errors,
  };
}

async function downloadChatParallel({
  context,
  vodId,
  duration,
  chapters,
  variableTemplate,
  persistedQueryHash,
  clientId,
  requestHeaders,
  authorization,
  userAgent,
  scanStart,
  sequentialRecoveryStart = scanStart,
  requestedConcurrency,
  requestedConcurrencyRaw = requestedConcurrency,
  tasksPerWorker = 2,
  initialComments = [],
  initialRawPages = [],
}) {
  const segments = buildChatSegments({
    startOffset: scanStart,
    durationSeconds: duration,
    concurrency: requestedConcurrency,
    tasksPerWorker,
    overlapSeconds: DEFAULT_CHAT_OVERLAP_SECONDS,
    tailSeconds: 0,
  });
  console.log(`  chat scheduler: ${segments.length} task(s) for ${requestedConcurrency} worker(s) | overlap=${DEFAULT_CHAT_OVERLAP_SECONDS}s`);

  let pageCounter = initialRawPages.reduce(
    (maxValue, record) => Math.max(maxValue, Number(record?.page_number) || 0),
    0,
  );
  const nextPageNumber = () => {
    pageCounter += 1;
    return pageCounter;
  };

  const allComments = [...initialComments];
  const allRawPages = [...initialRawPages];
  const finalResults = new Map();
  const attemptHistory = [];
  const queueTelemetry = [];
  let remaining = [...segments];

  const phaseConcurrency = buildConcurrencyLadder(requestedConcurrency);

  for (let phaseIndex = 0; phaseIndex < phaseConcurrency.length && remaining.length > 0; phaseIndex += 1) {
    const concurrency = Math.min(phaseConcurrency[phaseIndex], Math.max(1, remaining.length));
    const phaseName = `phase_${phaseIndex + 1}_concurrency_${concurrency}`;
    if (phaseIndex > 0) {
      console.log(`  chat fallback: retrying ${remaining.length} task(s) with concurrency=${concurrency}`);
      await sleep(computeRetryDelayMs({ attempt: phaseIndex + 1, status: 503, jitterUnit: 0.5 }));
    }

    const queueRun = await runDynamicQueue(remaining, concurrency, async (segment, _index, workerId) =>
      downloadChatSegment({
        segment,
        phase: phaseName,
        workerId,
        context,
        vodId,
        duration,
        chapters,
        variableTemplate,
        persistedQueryHash,
        clientId,
        requestHeaders,
        authorization,
        userAgent,
        nextPageNumber,
      }),
    );
    const phaseResults = queueRun.results;
    queueTelemetry.push({
      phase: phaseName,
      initial_concurrency: queueRun.initial_concurrency,
      final_concurrency: queueRun.final_concurrency,
      reductions: queueRun.reductions,
      assignments: queueRun.assignments,
    });

    for (const reduction of queueRun.reductions) {
      console.log(`  chat adaptive concurrency: ${reduction.from} -> ${reduction.to} (${reduction.reason})`);
    }

    const failed = [];
    for (const result of phaseResults) {
      if (!result) continue;
      allComments.push(...result.comments);
      allRawPages.push(...result.raw_pages);
      attemptHistory.push({
        phase: phaseName,
        worker_id: result.worker_id ?? null,
        segment_id: result.segment.id,
        ok: result.ok,
        pages: result.pages,
        rate_limited: result.rate_limited,
        last_successful_offset: result.last_successful_offset,
        terminal_reason: result.terminal_reason,
        errors: result.errors,
      });
      if (result.ok && result.progression_ok) {
        finalResults.set(result.segment.id, result);
      } else {
        failed.push(result.segment);
        finalResults.set(result.segment.id, result);
      }
    }
    remaining = failed;
  }

  let finalSegmentResults = segments.map(segment => finalResults.get(segment.id)).filter(Boolean);
  let unresolved = finalSegmentResults.filter(result => !result.ok || !result.progression_ok);
  let safetyRecovery = null;

  // Correctness wins over speed. Dynamic scheduling only changes who performs
  // each independent offset range. If any range still cannot prove coverage
  // after the concurrency ladder, make one final sequential pass using the
  // proven offset+1 pagination from the last contiguous prefix.
  if (unresolved.length > 0) {
    console.log(`  chat safety fallback: sequential recovery from ${hms(sequentialRecoveryStart)}`);
    const recoverySegment = {
      id: 'sequential-recovery',
      index: 0,
      nominal_start: sequentialRecoveryStart,
      nominal_end: duration,
      fetch_start: sequentialRecoveryStart,
      fetch_end: duration,
      is_final: true,
    };
    safetyRecovery = await downloadChatSegment({
      segment: recoverySegment,
      phase: 'safety_sequential_recovery',
      workerId: 1,
      context,
      vodId,
      duration,
      chapters,
      variableTemplate,
      persistedQueryHash,
      clientId,
      requestHeaders,
      authorization,
      userAgent,
      nextPageNumber,
    });
    allComments.push(...safetyRecovery.comments);
    allRawPages.push(...safetyRecovery.raw_pages);
    attemptHistory.push({
      phase: 'safety_sequential_recovery',
      worker_id: 1,
      segment_id: safetyRecovery.segment.id,
      ok: safetyRecovery.ok,
      pages: safetyRecovery.pages,
      rate_limited: safetyRecovery.rate_limited,
      last_successful_offset: safetyRecovery.last_successful_offset,
      terminal_reason: safetyRecovery.terminal_reason,
      errors: safetyRecovery.errors,
    });
    if (safetyRecovery.ok && safetyRecovery.progression_ok) {
      unresolved = [];
    }
  }

  finalSegmentResults = segments.map(segment => finalResults.get(segment.id)).filter(Boolean);
  const finalSegment = safetyRecovery?.ok
    ? safetyRecovery
    : (finalSegmentResults.find(result => result.segment.is_final) || null);
  const comments = mergeComments(allComments);
  const successfulPages = allRawPages.filter(record => !!extractCommentsPage(record?.response)).length;
  const allComplete = unresolved.length === 0 && (finalSegmentResults.length === segments.length || !!safetyRecovery?.ok);
  const terminalReason = allComplete
    ? (finalSegment?.terminal_reason === 'hasNextPage_false' || finalSegment?.terminal_reason === 'post_duration_api_boundary'
        ? finalSegment.terminal_reason
        : 'dynamic_queue_complete')
    : 'dynamic_queue_incomplete';
  const terminalScope = allComplete
    ? (finalSegment?.terminal_scope === 'chat_connection_reported_end' || finalSegment?.terminal_scope === 'archive_duration_boundary'
        ? finalSegment.terminal_scope
        : 'dynamic_queue_coverage_complete')
    : 'request_error';

  const allReductions = queueTelemetry.flatMap(phase => phase.reductions || []);
  const finalEffectiveConcurrency = queueTelemetry.length
    ? queueTelemetry.at(-1).final_concurrency
    : requestedConcurrency;
  const completedSegments = finalSegmentResults.filter(result => result.ok && result.progression_ok).length;

  return {
    comments,
    raw_pages: allRawPages,
    pages: successfulPages,
    errors: allComplete ? [] : unresolved.flatMap(result => result.errors || []),
    terminal_reason: terminalReason,
    terminal_scope: terminalScope,
    terminal_boundary_detected: finalSegment?.terminal_reason === 'post_duration_api_boundary',
    terminal_probe: finalSegment?.terminal_probe ?? unresolved[0]?.terminal_probe ?? null,
    segment_coverage: {
      strategy: 'dynamic_work_queue_offset_ranges_with_adaptive_concurrency_and_sequential_safety_fallback',
      requested_concurrency: requestedConcurrencyRaw,
      effective_concurrency: requestedConcurrency,
      final_effective_concurrency: finalEffectiveConcurrency,
      safety_cap_applied: Number(requestedConcurrencyRaw) > Number(requestedConcurrency),
      tasks_per_worker: tasksPerWorker,
      overlap_seconds: DEFAULT_CHAT_OVERLAP_SECONDS,
      scan_start_seconds: scanStart,
      sequential_recovery_start_seconds: sequentialRecoveryStart,
      duration_seconds: duration,
      segments_total: segments.length,
      segments_complete: allComplete ? segments.length : completedSegments,
      segments_failed: allComplete ? 0 : unresolved.length,
      coverage_status: allComplete ? 'OK' : 'FAIL',
      concurrency_ladder: phaseConcurrency,
      adaptive_reductions: allReductions,
      queue_phases: queueTelemetry,
      safety_sequential_recovery: safetyRecovery
        ? {
            used: true,
            ok: safetyRecovery.ok,
            pages: safetyRecovery.pages,
            start_seconds: sequentialRecoveryStart,
            last_successful_offset: safetyRecovery.last_successful_offset,
            terminal_reason: safetyRecovery.terminal_reason,
            terminal_scope: safetyRecovery.terminal_scope,
          }
        : { used: false },
      segments: finalSegmentResults.map(result => ({
        id: result.segment.id,
        worker_id: result.worker_id ?? null,
        nominal_start: result.segment.nominal_start,
        nominal_end: result.segment.nominal_end,
        fetch_start: result.segment.fetch_start,
        fetch_end: result.segment.fetch_end,
        is_final: result.segment.is_final,
        ok: result.ok,
        pages: result.pages,
        progression: result.progression_ok ? 'OK' : 'FAIL',
        first_returned_offset: result.first_returned_offset,
        last_successful_offset: result.last_successful_offset,
        terminal_reason: result.terminal_reason,
        terminal_scope: result.terminal_scope,
        rate_limited: result.rate_limited,
      })),
      attempt_history: attemptHistory,
    },
  };
}

function updateStateRecord(state, vodId, patch) {
  state.schema_version = 2;
  state.scraper_version = SCRAPER_VERSION;
  state.channel = STREAMER;
  state.updated_at = new Date().toISOString();
  state.vods = state.vods && typeof state.vods === 'object' ? state.vods : {};
  state.vods[String(vodId)] = {
    ...(state.vods[String(vodId)] || {}),
    ...patch,
    updated_at: new Date().toISOString(),
  };
}

async function writeHistoryLatestAndState(historyPath, historyVideos, statePath, state) {
  const now = new Date().toISOString();
  const historyDocument = buildHistoryDocument(STREAMER, historyVideos, now);
  await writeJson(historyPath, historyDocument);
  if (historyDocument.videos.length > 0) {
    await writeJson(path.join(OUT, 'latest.json'), historyDocument.videos[0]);
  }
  await writeJson(statePath, state);
}

function printHelp() {
  console.log(`zai-scraper V${SCRAPER_VERSION}\n\n` +
    `Usage:\n` +
    `  bun run scrape.mjs <channel> <count> [--threads N] [--force] [--no-resume]\n` +
    `  bun run scrape.mjs <channel> <vod-url-or-id> [--threads N] [--force] [--no-resume]\n\n` +
    `Examples:\n` +
    `  bun run scrape.mjs alanzoka 2\n` +
    `  bun run scrape.mjs alanzoka https://www.twitch.tv/videos/2868864059\n` +
    `  bun run scrape.mjs alanzoka 2868864059 --force\n` +
    `  bun run scrape.mjs alanzoka 2 --threads 1\n\n` +
    `Defaults: 4 chat workers, safety cap 8, dynamic queue with ~2 tasks per worker; completed archives are skipped; incomplete and in-progress VODs resume automatically.`);
}

async function main() {
  if (CLI.help) {
    printHelp();
    return;
  }

  await mkdirp(OUT);
  await mkdirp(path.join(OUT, 'raw'));
  await mkdirp(path.join(OUT, 'discovery'));
  await mkdirp(path.join(OUT, 'chat'));

  const historyPath = path.join(OUT, 'history.json');
  const statePath = path.join(OUT, 'state.json');
  const previousHistory = await readJson(historyPath, {});
  const historyVideos = normalizeHistory(previousHistory);
  const state = await readJson(statePath, { schema_version: 2, vods: {} });
  state.schema_version = 2;
  state.scraper_version = SCRAPER_VERSION;
  state.channel = STREAMER;

  console.log(`V${SCRAPER_VERSION} ${STREAMER}`);
  console.log(`mode: ${CLI.mode === 'specific_vod' ? `specific VOD ${CLI.vodId}` : `latest ${CLI.limit} VOD(s)`}`);
  const concurrencyLabel = CLI.concurrency_capped
    ? `requested=${CLI.requested_threads} | effective=${CLI.threads} (safety cap)`
    : `${CLI.threads}`;
  console.log(`chat concurrency: ${concurrencyLabel}${CLI.force ? ' | force' : ''}${CLI.resume ? ' | resume=on' : ' | resume=off'}`);

  let browser = null;
  let context = null;
  let page = null;
  let vodCatalog = null;

  try {
    if (CLI.mode === 'specific_vod') {
      vodCatalog = emptyVodCatalog([CLI.vodId]);
    } else {
      browser = await chromium.launch({ headless: true });
      context = await browser.newContext();
      page = await context.newPage();
      vodCatalog = await collectVodIds(page, CLI.limit);
      console.log(
        `catalog broadcast evidence: ${vodCatalog.diagnostics.selected_vods_with_broadcast_evidence}/${vodCatalog.vodIds.length} selected VOD(s)`
        + `${vodCatalog.diagnostics.errors.length ? ` | capture errors=${vodCatalog.diagnostics.errors.length}` : ''}`,
      );
    }

    const vodIds = vodCatalog.vodIds;
    const decisions = new Map();
    let processCount = 0;

    for (const vodId of vodIds) {
      const existing = await evaluateExistingVod(vodId, historyVideos, state);
      if (!CLI.force && existing.complete) {
        decisions.set(String(vodId), { action: 'skip', existing });
        updateStateRecord(state, vodId, {
          complete: true,
          status: 'complete',
          caught_up: false,
          current_broadcast_match: false,
          skipped: true,
          messages: existing.stats?.integrity?.total_messages ?? existing.stats?.total_messages ?? null,
          max_offset_seconds: existing.stats?.integrity?.max_offset_seconds ?? null,
          source_scraper_version: existing.version,
          file_sizes: existing.file_sizes,
        });
        console.log(`[VOD ${vodId}] ✓ already complete — skipping`);
      } else {
        decisions.set(String(vodId), { action: 'process', existing });
        processCount += 1;
      }
    }

    if (processCount === 0) {
      await writeHistoryLatestAndState(historyPath, historyVideos, statePath, state);
      console.log('\nNothing to download.');
      console.log(`OK -> ${OUT}`);
      return;
    }

    if (!browser) {
      browser = await chromium.launch({ headless: true });
      context = await browser.newContext();
      page = await context.newPage();
    }

    for (const vodId of vodIds) {
      const decision = decisions.get(String(vodId));
      if (decision?.action !== 'process') continue;
      const existing = decision.existing;
      console.log(`\n[VOD ${vodId}]`);
      if (existing?.classification?.legacy_live_match && existing?.classification?.skip_allowed === false) {
        console.log('  migration: previous V7.5 state matches the current broadcast — treating as in-progress');
      } else if (existing?.classification?.explicit_in_progress) {
        console.log('  state: in-progress VOD — refreshing before it can become skippable');
      }

      let resumeSeed = null;
      if (!CLI.force && CLI.resume && existing && !existing.complete) {
        resumeSeed = await loadResumeSeed(existing);
        if (resumeSeed) {
          console.log(
            `  resume: ${resumeSeed.previous_total_messages} existing comments through ${hms(resumeSeed.max_offset_seconds)}`,
          );
        }
      }

      const gql = [];
      const important = {};
      const pendingCaptures = new Set();
      let clientId = null;
      let gqlRequestHeaders = {};
      let gqlAuthorization = null;
      let chatRequestHeaders = {};
      let chatAuthorization = null;

      const handler = request => {
        if (!request.url().includes('/gql')) return;
        const task = (async () => {
          const requestBody = (() => {
            try { return request.postDataJSON(); } catch { return null; }
          })();
          const batch = Array.isArray(requestBody)
            ? requestBody
            : requestBody
              ? [requestBody]
              : [];
          const operationNames = batch.map(item => item?.operationName).filter(Boolean);
          if (operationNames.length === 0) return;

          const requestHeaders = request.headers();
          const requestClientId = requestHeaders['client-id'];
          if (requestClientId) clientId = requestClientId;
          gqlRequestHeaders = Object.fromEntries(
            ['client-id', 'client-integrity', 'x-device-id']
              .filter(name => requestHeaders[name])
              .map(name => [name, requestHeaders[name]]),
          );
          if (requestHeaders.authorization) gqlAuthorization = requestHeaders.authorization;
          if (operationNames.includes(CHAT_OPERATION)) {
            chatRequestHeaders = Object.fromEntries(
              ['client-id', 'client-integrity', 'x-device-id']
                .filter(name => requestHeaders[name])
                .map(name => [name, requestHeaders[name]]),
            );
            chatAuthorization = requestHeaders.authorization || null;
          }

          try {
            const response = await request.response();
            if (!response) return;
            let responseBody = null;
            try { responseBody = await response.json(); } catch { responseBody = null; }
            const record = {
              source: 'page',
              operation_names: operationNames,
              request: requestBody,
              response: responseBody,
              http_status: response.status(),
              timestamp: new Date().toISOString(),
            };
            gql.push(record);
            for (const operation of operationNames) {
              if (IMPORTANT_OPERATIONS.has(operation) && important[operation] === undefined) {
                important[operation] = responseBody;
              }
            }
          } catch {
            // Diagnostic capture failures must never abort the VOD.
          }
        })();
        pendingCaptures.add(task);
        task.finally(() => pendingCaptures.delete(task));
      };

      page.on('request', handler);
      try {
        await page.goto(`https://www.twitch.tv/videos/${vodId}`, {
          waitUntil: 'domcontentloaded',
          timeout: 60000,
        });
        await page.waitForTimeout(8000);
        while (pendingCaptures.size > 0) {
          await Promise.allSettled([...pendingCaptures]);
        }

        const metadataVideo = extractVideoObject(important.VideoMetadata, vodId);
        const channelVideo = extractVideoObject(important.ChannelVideoCore, vodId);
        const fallbackVideo = extractVideoObject(gql, vodId);
        const video = metadataVideo || channelVideo || fallbackVideo;
        if (!video) throw new Error(`Video metadata not found for VOD ${vodId}`);

        const duration = num(video.lengthSeconds) ?? 0;
        const chapterNodes = extractChapterNodes(important.VideoPlayer_ChapterSelectButtonVideo, vodId);
        const chapters = normalizeChapters(chapterNodes, duration);
        const storyUrl = extractStoryUrl(important.VideoPlayer_VODSeekbarPreviewVideo);
        const storyboard = await fetchStoryboard(storyUrl);
        const catalogBroadcastEvidence = vodCatalog.broadcastEvidenceByVod[String(vodId)] || [];
        const directBroadcastProbe = await fetchExactVodBroadcast({
          context,
          page,
          vodId: String(vodId),
          clientId: clientId || DEFAULT_CLIENT_ID,
          requestHeaders: gqlRequestHeaders,
          authorization: gqlAuthorization,
        });
        const broadcastEvidence = [
          ...directBroadcastProbe.evidence,
          ...catalogBroadcastEvidence,
        ];
        const streamInfo = extractStreamInfo({
          vodId: String(vodId),
          video,
          channelVideo,
          capture: gql,
          catalogEvidence: broadcastEvidence,
        });

        console.log(
          `  duration: ${hms(duration)} | chapters: ${chapters.length} | broadcast: ${streamInfo.historical_broadcast_id || 'null'}`
          + `${streamInfo.primary ? ` | primary=${streamInfo.primary.id} (${streamInfo.primary.source})` : ''}`,
        );

        const thumbnails = buildThumbnailUrls(video.previewThumbnailURL || video.thumbnailURL || null);
        console.log('  validating thumbnails...');
        const thumbnailValidation = await validateThumbnails(thumbnails);

        const capturedChat = findCapturedChatOperation(gql);
        if (!capturedChat) {
          throw new Error('Initial comments page was not found in captured GraphQL responses');
        }
        const variableTemplate = capturedChat.request?.variables || { videoID: String(vodId) };
        const chatPersistedHash = capturedChat.request?.extensions?.persistedQuery?.sha256Hash || CHAT_HASH;
        const clientIdForChat = clientId || DEFAULT_CLIENT_ID;
        const userAgent = await page.evaluate(() => navigator.userAgent).catch(() => 'Mozilla/5.0');

        console.log(
          `  chat query: hash=${chatPersistedHash.slice(0, 12)}… | template keys=${Object.keys(variableTemplate).join(',') || '(none)'}`,
        );

        const seedComments = [];
        const seedRawPages = [];
        if (resumeSeed) {
          seedComments.push(...resumeSeed.comments);
          seedRawPages.push(...resumeSeed.raw_pages.map(record => ({
            ...record,
            source: `resume_seed_${record.source || 'page'}`,
          })));
        }

        addPageComments(capturedChat.page, chapters, seedComments);
        const initialPageNumber = seedRawPages.reduce(
          (maxValue, record) => Math.max(maxValue, Number(record?.page_number) || 0),
          0,
        ) + 1;
        seedRawPages.push(buildChatRawRecord({
          vodId,
          pageNumber: initialPageNumber,
          variables: capturedChat.request?.variables || { videoID: String(vodId) },
          responseBody: capturedChat.response,
          status: capturedChat.http_status,
          clientId: clientIdForChat,
          source: 'page_initial_current_run',
          requestHeaders: chatRequestHeaders,
          persistedQueryHash: chatPersistedHash,
          phase: 'initial_capture',
        }));

        const initialLastOffset = maxPageOffset(capturedChat.page) ?? 0;
        const resumeStart = resumeSeed
          ? Math.max(0, resumeSeed.max_offset_seconds - DEFAULT_CHAT_OVERLAP_SECONDS)
          : Math.max(0, initialLastOffset + 1);

        console.log(`  chat: dynamic queue from ${hms(resumeStart)} with ${CLI.threads} worker(s)`);
        const chatDownload = await downloadChatParallel({
          context,
          vodId: String(vodId),
          duration,
          chapters,
          variableTemplate,
          persistedQueryHash: chatPersistedHash,
          clientId: clientIdForChat,
          requestHeaders: chatRequestHeaders,
          authorization: chatAuthorization,
          userAgent,
          scanStart: resumeStart,
          sequentialRecoveryStart: resumeSeed ? Math.max(0, resumeSeed.max_offset_seconds - DEFAULT_CHAT_OVERLAP_SECONDS) : Math.max(0, initialLastOffset + 1),
          requestedConcurrency: CLI.threads,
          requestedConcurrencyRaw: CLI.requested_threads,
          tasksPerWorker: CLI.tasks_per_worker,
          initialComments: seedComments,
          initialRawPages: seedRawPages,
        });

        const comments = mergeComments(chatDownload.comments);
        const chatRawPages = chatDownload.raw_pages;
        const pages = chatDownload.pages;
        const chatErrors = [...new Set(chatDownload.errors)];
        const terminalReason = chatDownload.terminal_reason;
        const terminalScope = chatDownload.terminal_scope;
        const terminalBoundaryDetected = chatDownload.terminal_boundary_detected;
        const terminalProbe = chatDownload.terminal_probe;

        const scrapedAt = new Date().toISOString();
        const metadata = normalizeMetadata(
          video,
          chapters,
          storyboard,
          thumbnailValidation,
          scrapedAt,
          streamInfo,
        );
        const chatIntegrity = analyzeChatIntegrity(
          comments,
          chatRawPages,
          duration,
          pages,
          chatErrors,
          { scope: terminalScope, boundaryDetected: terminalBoundaryDetected },
        );
        chatIntegrity.pagination_progression = chatDownload.segment_coverage.coverage_status === 'OK' ? 'OK' : 'FAIL';
        chatIntegrity.terminal_reason = terminalReason;
        chatIntegrity.terminal_scope = terminalScope;
        chatIntegrity.terminal_boundary_detected = terminalBoundaryDetected;
        chatIntegrity.terminal_probe = terminalProbe;
        chatIntegrity.segment_coverage = chatDownload.segment_coverage;
        chatIntegrity.resume = resumeSeed
          ? {
              used: true,
              previous_total_messages: resumeSeed.previous_total_messages,
              previous_max_offset_seconds: resumeSeed.max_offset_seconds,
              scan_restart_seconds: resumeStart,
              overlap_seconds: DEFAULT_CHAT_OVERLAP_SECONDS,
              previous_scraper_version: resumeSeed.previous_scraper_version,
              previous_terminal_reason: resumeSeed.previous_terminal_reason,
            }
          : { used: false };

        const sourceTerminalReason = terminalReason;
        const sourceTerminalScope = terminalScope;
        const lifecycleBeforeTerminalRewrite = classifyVodLifecycle({
          integrity: chatIntegrity,
          scraperVersion: SCRAPER_VERSION,
          historicalBroadcastId: streamInfo.historical_broadcast_id,
          currentChannelStream: streamInfo.current_channel_stream,
        });
        const lifecycleTerminal = resolveLifecycleTerminal({
          terminalReason: sourceTerminalReason,
          terminalScope: sourceTerminalScope,
          lifecycle: lifecycleBeforeTerminalRewrite,
        });
        if (lifecycleTerminal.source_terminal_reason) {
          chatIntegrity.source_terminal_reason = lifecycleTerminal.source_terminal_reason;
          chatIntegrity.source_terminal_scope = lifecycleTerminal.source_terminal_scope;
        }
        chatIntegrity.terminal_reason = lifecycleTerminal.terminal_reason;
        chatIntegrity.terminal_scope = lifecycleTerminal.terminal_scope;

        const completion = classifyVodLifecycle({
          integrity: chatIntegrity,
          scraperVersion: SCRAPER_VERSION,
          historicalBroadcastId: streamInfo.historical_broadcast_id,
          currentChannelStream: streamInfo.current_channel_stream,
        });
        chatIntegrity.download_complete = completion.complete;
        chatIntegrity.download_caught_up = completion.caught_up;
        chatIntegrity.vod_lifecycle = {
          status: completion.status,
          current_broadcast_match: completion.current_broadcast_match,
          caught_up: completion.caught_up,
          historical_broadcast_id: completion.historical_broadcast_id,
          current_channel_stream_id: completion.current_channel_stream_id,
        };

        const stats = chatStats(comments, chapters, duration);
        stats.scraper_version = SCRAPER_VERSION;
        stats.integrity = {
          total_messages: chatIntegrity.total_messages,
          unique_message_ids: chatIntegrity.unique_message_ids,
          duplicate_message_ids_in_output: chatIntegrity.duplicate_message_ids_in_output,
          raw_edges: chatIntegrity.raw_edges,
          raw_unique_message_ids: chatIntegrity.raw_unique_message_ids,
          raw_repeated_edge_count: chatIntegrity.raw_repeated_edge_count,
          raw_repeated_message_ids: chatIntegrity.raw_repeated_message_ids,
          pages_scraped: chatIntegrity.pages_scraped,
          raw_page_attempts: chatIntegrity.raw_page_attempts,
          successful_raw_pages: chatIntegrity.successful_raw_pages,
          pagination_progression: chatIntegrity.pagination_progression,
          output_chronological_order: chatIntegrity.output_chronological_order,
          min_offset_seconds: chatIntegrity.min_offset_seconds,
          max_offset_seconds: chatIntegrity.max_offset_seconds,
          duration_seconds: chatIntegrity.duration_seconds,
          beyond_duration_seconds: chatIntegrity.beyond_duration_seconds,
          terminal_page_has_next: chatIntegrity.terminal_page_has_next,
          terminal_page_clean: chatIntegrity.terminal_page_clean,
          terminal_reason: chatIntegrity.terminal_reason,
          terminal_scope: chatIntegrity.terminal_scope,
          source_terminal_reason: chatIntegrity.source_terminal_reason ?? null,
          source_terminal_scope: chatIntegrity.source_terminal_scope ?? null,
          terminal_probe: chatIntegrity.terminal_probe,
          terminal_boundary_detected: chatIntegrity.terminal_boundary_detected,
          errors_count: chatIntegrity.errors_count,
          download_complete: chatIntegrity.download_complete,
          download_caught_up: chatIntegrity.download_caught_up,
          vod_lifecycle: chatIntegrity.vod_lifecycle,
          segment_coverage: chatIntegrity.segment_coverage,
          resume: chatIntegrity.resume,
        };

        metadata.chat = {
          file: `chat/${vodId}.json`,
          stats_file: `chat/${vodId}-stats.json`,
          total_messages: comments.length,
          pages_scraped: pages,
          errors: chatErrors,
          integrity: chatIntegrity,
        };

        const rawRecord = {
          scraper_version: SCRAPER_VERSION,
          vod_id: String(vodId),
          graphql: gql,
          chat_pagination: chatRawPages,
          chat_integrity: chatIntegrity,
          chat_request_template: {
            operation: CHAT_OPERATION,
            captured_variables: variableTemplate,
            persisted_query_hash: chatPersistedHash,
            policy: 'clone captured variables; replace only videoID/contentOffsetSeconds; remove cursor',
          },
          chat_parallel: chatDownload.segment_coverage,
          resume: chatIntegrity.resume,
          historical_broadcast_id: streamInfo.historical_broadcast_id,
          historical_broadcast_resolution: streamInfo.historical_resolution,
          vod_broadcast_probe: directBroadcastProbe.diagnostic,
          vod_catalog_capture: vodCatalog.diagnostics,
          terminal_probe: terminalProbe,
          vod_lifecycle: chatIntegrity.vod_lifecycle,
          source_terminal_reason: chatIntegrity.source_terminal_reason ?? null,
          source_terminal_scope: chatIntegrity.source_terminal_scope ?? null,
          captured_client_id: clientId,
          scraped_at: scrapedAt,
        };

        const discovery = {
          vod_id: String(vodId),
          scraper_version: SCRAPER_VERSION,
          important_operations: Object.fromEntries(
            Object.entries(important).filter(([name]) => IMPORTANT_OPERATIONS.has(name)),
          ),
          stream_resolution: {
            historical_broadcast_id: streamInfo.historical_broadcast_id,
            historical_resolution: streamInfo.historical_resolution,
            direct_probe: directBroadcastProbe.diagnostic,
            exact_vod_evidence: broadcastEvidence,
            primary: streamInfo.primary,
            current_channel_stream: streamInfo.current_channel_stream,
            candidates: streamInfo.candidates,
          },
          chapter_schema: {
            path: 'data.video.moments.edges[].node',
            fields: [
              'id', 'type', 'description', 'subDescription',
              'positionMilliseconds', 'durationMilliseconds', 'details.game',
            ],
          },
          chapters_extracted: chapters.length,
          storyboard,
          thumbnails: {
            urls: thumbnails,
            validation: thumbnailValidation,
          },
          chat_pagination: {
            operation: CHAT_OPERATION,
            strategy: 'dynamic_work_queue_contentOffsetSeconds_ranges',
            captured_variable_template: variableTemplate,
            subsequent_variables: {
              ...variableTemplate,
              videoID: String(vodId),
              contentOffsetSeconds: '<worker offset>',
              cursor: undefined,
            },
            persisted_query_hash: chatPersistedHash,
            pages_scraped: pages,
            errors: chatErrors,
            terminal_reason: chatIntegrity.terminal_reason,
            terminal_scope: chatIntegrity.terminal_scope,
            source_terminal_reason: chatIntegrity.source_terminal_reason ?? null,
            source_terminal_scope: chatIntegrity.source_terminal_scope ?? null,
            terminal_probe: terminalProbe,
            terminal_boundary_detected: terminalBoundaryDetected,
            segment_coverage: chatDownload.segment_coverage,
            resume: chatIntegrity.resume,
            integrity: {
              ...chatIntegrity,
              page_summaries: undefined,
            },
            raw_pages: chatRawPages.map(rawPage => ({
              page_number: rawPage.page_number,
              source: rawPage.source,
              worker_id: rawPage.worker_id,
              segment_id: rawPage.segment_id,
              phase: rawPage.phase,
              http_status: rawPage.http_status,
              variables: rawPage.request.variables,
              has_next_page: extractCommentsPage(rawPage.response)?.pageInfo?.hasNextPage ?? null,
              edge_count: extractCommentsPage(rawPage.response)?.edges?.length ?? 0,
            })),
          },
        };

        await writeJson(path.join(OUT, 'raw', `${vodId}.json`), rawRecord);
        await writeJson(path.join(OUT, 'discovery', `${vodId}.json`), discovery);
        await writeJson(path.join(OUT, 'chat', `${vodId}.json`), {
          schema_version: 3,
          scraper_version: SCRAPER_VERSION,
          vod_id: String(vodId),
          total: comments.length,
          pages,
          status: completion.status,
          complete: completion.complete,
          caught_up: completion.caught_up,
          current_broadcast_match: completion.current_broadcast_match,
          errors: chatErrors,
          comments,
        });
        await writeJson(path.join(OUT, 'chat', `${vodId}-stats.json`), stats);

        const outputFileSizes = {
          raw: await fileSize(path.join(OUT, 'raw', `${vodId}.json`)),
          discovery: await fileSize(path.join(OUT, 'discovery', `${vodId}.json`)),
          chat: await fileSize(path.join(OUT, 'chat', `${vodId}.json`)),
          stats: await fileSize(path.join(OUT, 'chat', `${vodId}-stats.json`)),
        };

        const previous = historyVideos[String(vodId)] || {};
        historyVideos[String(vodId)] = {
          ...previous,
          ...metadata,
          first_seen_at: previous.first_seen_at ?? scrapedAt,
          last_seen_at: scrapedAt,
        };

        updateStateRecord(state, vodId, {
          complete: completion.complete,
          status: completion.status,
          caught_up: completion.caught_up,
          current_broadcast_match: completion.current_broadcast_match,
          historical_broadcast_id: completion.historical_broadcast_id,
          current_channel_stream_id: completion.current_channel_stream_id,
          skipped: false,
          messages: comments.length,
          max_offset_seconds: chatIntegrity.max_offset_seconds,
          terminal_reason: chatIntegrity.terminal_reason,
          terminal_scope: chatIntegrity.terminal_scope,
          source_terminal_reason: chatIntegrity.source_terminal_reason ?? null,
          source_terminal_scope: chatIntegrity.source_terminal_scope ?? null,
          errors_count: chatIntegrity.errors_count,
          resume_used: !!resumeSeed,
          scraper_version: SCRAPER_VERSION,
          file_sizes: outputFileSizes,
        });
        await writeHistoryLatestAndState(historyPath, historyVideos, statePath, state);

        console.log(`  chapters: ${chapters.length}`);
        console.log(`  chat: ${comments.length} comments | ${pages} successful page fetches | ${stats.unique_users} users`);
        console.log(
          `  chat integrity: coverage=${chatDownload.segment_coverage.coverage_status} | `
          + `order=${chatIntegrity.output_chronological_order} | `
          + `duplicates=${chatIntegrity.duplicate_message_ids_in_output} | `
          + `terminal=${chatIntegrity.terminal_reason} | complete=${completion.complete ? 'YES' : 'NO'}`
          + `${completion.status === 'in_progress' ? ` | status=IN_PROGRESS | caught_up=${completion.caught_up ? 'YES' : 'NO'}` : ''}`,
        );
        console.log(
          `  tasks: ${chatDownload.segment_coverage.segments_complete}/${chatDownload.segment_coverage.segments_total} complete`
          + `${chatDownload.segment_coverage.attempt_history.some(item => !item.ok) ? ' | fallback used' : ''}`,
        );
        console.log(`  storyboard: ${storyboard.available ? `${storyboard.variants.length} variant(s)` : 'no'}`);
        console.log(
          `  thumbnails: ${Object.entries(thumbnailValidation)
            .map(([name, result]) => `${name}=${result.valid ? 'OK' : 'FAIL'}`)
            .join(' ')}`,
        );
      } catch (error) {
        updateStateRecord(state, vodId, {
          complete: false,
          status: 'failed',
          skipped: false,
          error: error?.message ?? String(error),
          scraper_version: SCRAPER_VERSION,
        });
        await writeJson(statePath, state);
        console.error(`  FAILED: ${error?.message ?? String(error)}`);
      } finally {
        page.off('request', handler);
      }
    }

    await writeHistoryLatestAndState(historyPath, historyVideos, statePath, state);
  } finally {
    if (browser) await browser.close();
  }

  console.log(`\nOK -> ${OUT}`);
}

main().catch(error => {
  console.error(error?.stack ?? error);
  process.exit(1);
});
