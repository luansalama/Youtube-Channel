const nonEmpty = value => value !== null && value !== undefined && value !== '';

function walkWithPath(value, callback, path = 'root', seen = new Set()) {
  if (!value || typeof value !== 'object' || seen.has(value)) return;
  seen.add(value);
  callback(value, path);

  if (Array.isArray(value)) {
    value.forEach((child, index) => walkWithPath(child, callback, `${path}[${index}]`, seen));
    return;
  }

  for (const [key, child] of Object.entries(value)) {
    walkWithPath(child, callback, `${path}.${key}`, seen);
  }
}

function broadcastIdFromVideoObject(value) {
  const candidate =
    value?.broadcastIdentifier?.id ??
    value?.broadcastId ??
    value?.broadcastID ??
    null;
  return nonEmpty(candidate) ? String(candidate) : null;
}

function isVideoLike(value) {
  if (!value || typeof value !== 'object') return false;
  if (value.__typename === 'Video') return true;

  const signals = [
    value.lengthSeconds,
    value.previewThumbnailURL,
    value.animatedPreviewURL,
    value.publishedAt,
    value.broadcastType,
    value.viewCount,
  ].filter(nonEmpty).length;

  return signals >= 2;
}

/**
 * Extract only broadcast IDs that are structurally attached to a Video object.
 * A naked BroadcastIdOnly elsewhere in the response is intentionally ignored.
 */
export function extractVideoBroadcastAssociations(root, { source = 'capture', vodId = null } = {}) {
  const targetVodId = nonEmpty(vodId) ? String(vodId) : null;
  const output = [];
  const seen = new Set();

  walkWithPath(root, (value, objectPath) => {
    if (!isVideoLike(value) || !nonEmpty(value.id)) return;

    const objectVodId = String(value.id);
    if (targetVodId && objectVodId !== targetVodId) return;

    const broadcastId = broadcastIdFromVideoObject(value);
    if (!broadcastId) return;

    const key = `${objectVodId}|${broadcastId}|${source}|${objectPath}`;
    if (seen.has(key)) return;
    seen.add(key);

    output.push({
      vod_id: objectVodId,
      broadcast_id: broadcastId,
      source,
      object_path: objectPath,
      object_typename: value.__typename ?? null,
      evidence_kind: 'vod_scoped_video_broadcast_identifier',
    });
  });

  return output;
}

function normalizeCatalogEvidence(catalogEvidence, vodId) {
  return (Array.isArray(catalogEvidence) ? catalogEvidence : [])
    .filter(item => String(item?.vod_id ?? '') === String(vodId))
    .filter(item => nonEmpty(item?.broadcast_id))
    .map(item => ({
      vod_id: String(vodId),
      broadcast_id: String(item.broadcast_id),
      source: item.source || 'catalog',
      object_path: item.object_path ?? null,
      object_typename: item.object_typename ?? 'Video',
      evidence_kind: item.evidence_kind || 'vod_scoped_video_broadcast_identifier',
    }));
}

function evidenceFromGraphqlRecords(records, vodId) {
  const output = [];

  for (const record of Array.isArray(records) ? records : []) {
    const requestBody = record?.request;
    const requestBatch = Array.isArray(requestBody)
      ? requestBody
      : requestBody
        ? [requestBody]
        : [];

    const responseBody = record?.response;
    const responseBatch = Array.isArray(responseBody)
      ? responseBody
      : responseBody !== null && responseBody !== undefined
        ? [responseBody]
        : [];

    if (requestBatch.length && responseBatch.length === requestBatch.length) {
      for (let index = 0; index < requestBatch.length; index += 1) {
        const operation = requestBatch[index]?.operationName || `batch_${index}`;
        output.push(...extractVideoBroadcastAssociations(responseBatch[index], {
          source: `graphql.${operation}`,
          vodId,
        }));
      }
      continue;
    }

    const operationNames = Array.isArray(record?.operation_names)
      ? record.operation_names.filter(Boolean)
      : [];
    const source = operationNames.length
      ? `graphql.${operationNames.join('+')}`
      : 'graphql.capture';

    output.push(...extractVideoBroadcastAssociations(responseBody, { source, vodId }));
  }

  return output;
}

function dedupeEvidence(evidence) {
  const seen = new Set();
  const output = [];

  for (const item of evidence) {
    if (!item || !nonEmpty(item.broadcast_id)) continue;
    const key = [
      item.vod_id,
      item.broadcast_id,
      item.source,
      item.object_path ?? '',
    ].join('|');
    if (seen.has(key)) continue;
    seen.add(key);
    output.push(item);
  }

  return output;
}

/**
 * Resolve the historical stream/broadcast ID for one VOD.
 *
 * Invariant: every accepted ID must be attached to the exact target VOD object.
 * If exact VOD-scoped sources disagree, resolution is intentionally left null.
 */
export function resolveHistoricalBroadcast({
  vodId,
  video = null,
  channelVideo = null,
  graphqlRecords = [],
  catalogEvidence = [],
} = {}) {
  if (!nonEmpty(vodId)) {
    return {
      id: null,
      status: 'invalid_vod_id',
      confidence: 'none',
      primary_source: null,
      evidence: [],
      distinct_ids: [],
      conflicting_ids: [],
    };
  }

  const targetVodId = String(vodId);
  const evidence = [];

  if (String(video?.id ?? '') === targetVodId) {
    evidence.push(...extractVideoBroadcastAssociations(video, {
      source: 'direct.video',
      vodId: targetVodId,
    }));
  }

  if (String(channelVideo?.id ?? '') === targetVodId) {
    evidence.push(...extractVideoBroadcastAssociations(channelVideo, {
      source: 'direct.channel_video',
      vodId: targetVodId,
    }));
  }

  evidence.push(...normalizeCatalogEvidence(catalogEvidence, targetVodId));
  evidence.push(...evidenceFromGraphqlRecords(graphqlRecords, targetVodId));

  const deduped = dedupeEvidence(evidence);
  const distinctIds = [...new Set(deduped.map(item => item.broadcast_id))];

  if (distinctIds.length === 0) {
    return {
      id: null,
      status: 'not_found',
      confidence: 'none',
      primary_source: null,
      evidence: deduped,
      distinct_ids: [],
      conflicting_ids: [],
    };
  }

  if (distinctIds.length > 1) {
    return {
      id: null,
      status: 'conflict',
      confidence: 'none',
      primary_source: null,
      evidence: deduped,
      distinct_ids: distinctIds,
      conflicting_ids: distinctIds,
    };
  }

  const id = distinctIds[0];
  const supportingEvidence = deduped.filter(item => item.broadcast_id === id);
  const uniqueSources = [...new Set(supportingEvidence.map(item => item.source))];

  return {
    id,
    status: 'resolved',
    confidence: uniqueSources.length >= 2 ? 'confirmed' : 'high',
    primary_source: supportingEvidence[0]?.source ?? null,
    evidence: supportingEvidence,
    distinct_ids: [id],
    conflicting_ids: [],
  };
}
