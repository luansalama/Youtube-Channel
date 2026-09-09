# Twitch ingest (notas)

- Registrar cada VOD/POV com `cstudio ingest <slug> --asset-id ... --kind vod --path ...`.
- Chat exportado (ex.: TwitchDownloader) entra como `kind=chat` + `import_untrusted_rows()`.
- Transcrição entra como `kind=transcript`.
- Sincronizar POVs: extrair listas de eventos (claps, picos) e rodar `cstudio` sync-report
  (ver `cstudio/sync.py:estimate_offset`); gravar `.studio/internal/sync/sync-report.json`
  com `{offset_seconds, method, confidence}`.
- Direitos: tudo começa `sem_autorizacao_confirmada`; liberar com `cstudio rights ...`.
