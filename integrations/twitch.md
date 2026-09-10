# Twitch ingest (notas)

- Registrar cada VOD/POV com `cstudio ingest <slug> --asset-id ... --kind vod --path ...`.
- Chat exportado (ex.: TwitchDownloader) entra como `kind=chat` + `import_untrusted_rows()`.
- Transcrição entra como `kind=transcript`.
- Sincronizar POVs: extrair listas de eventos (claps, picos) e rodar `cstudio` sync-report
  (ver `cstudio/sync.py:estimate_offset`); gravar `.studio/internal/sync/sync-report.json`
  com `{offset_seconds, method, confidence}`.
- Direitos: tudo começa `sem_autorizacao_confirmada`; liberar com `cstudio rights ...`.


## Scraper V7.6 acoplado ao harness

O scraper fornecido está vendorizado em `integrations/twitch-scraper/`. O wrapper
`cstudio/twitch.py` define `CSTUDIO_TWITCH_OUT` para impedir que a captura vaze para
`~/zai-scraper/data`; por produção, a saída canônica é:

`productions/<slug>/.studio/internal/ingest/twitch/<streamer>/`

Uso CLI:

```powershell
python -m cstudio --root . twitch-scrape <slug> --streamer alanzoka --target 3 --threads 8
```

Flags espelhadas no dashboard: `--threads {1,2,4,8}`, `--sequential`, `--force`,
`--no-resume`. O primeiro run executa `bun install --frozen-lockfile` e garante o Chromium
do Playwright se as dependências ainda não estiverem presentes.

A captura é ingest, não aprovação: metadata/chat registrados continuam
`sem_autorizacao_confirmada` até uma ação humana explícita de direitos.
