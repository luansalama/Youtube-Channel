# Patch — Twitch scraper no Cuts Studio

Este patch integra o scraper Twitch V7.6 ao harness `Youtube-Channel` sem alterar o modelo de gates/rights.

## Aplicação

Extraia o ZIP diretamente na raiz do repositório `Youtube-Channel`, permitindo sobrescrever os arquivos existentes.

Depois:

```powershell
python -m cstudio --root . maintain
python -m cstudio --root . studio --host 127.0.0.1 --port 8765
```

Abra **Twitch Ingest** no dashboard.

## O que foi adicionado

- `cstudio/twitch.py`: bridge, jobs, logs, import para `assets.csv`.
- `twitch-scrape` na CLI.
- página **Twitch Ingest** no dashboard.
- endpoint local `GET /api/twitch-status?slug=<slug>`.
- scraper V7.6 vendorizado em `integrations/twitch-scraper/`.
- workers 1/2/4/8 e flags `--sequential`, `--force`, `--no-resume`.
- preparação automática de Playwright/Chromium no primeiro run quando necessário.

## Saída

```text
productions/<slug>/.studio/internal/ingest/twitch/<streamer>/
```

Ao terminar, `discovery/<vod>.json` entra como `vod-metadata` e `chat/<vod>.json` como `chat` no ingest.
Ambos começam em `sem_autorizacao_confirmada`; o patch não aprova direitos nem gates.

## Requisito externo

Bun deve estar instalado e disponível no `PATH` (ou definido por `CSTUDIO_BUN`).
