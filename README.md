# Cuts Studio v0.1.0

Harness local e determinístico para produzir **um corte/highlight Twitch → YouTube
por vez**, do config ao aprendizado — com propostas revisáveis, gates com
fingerprint e publicação bloqueada por padrão.

> Recuperação Z.AI: o endpoint público retornou `403 {"detail":"Not authenticated"}`
> (ver `CONTEXT/`). Nenhum conteúdo foi fabricado; a especificação da tarefa
> (§§ 4–19) foi usada como requisito. Molde analisado: `luansalama/Youtube-Channel`.

## Requisitos

- Python 3.11+
- O harness permanece majoritariamente stdlib, mas o Mirror Resolver usa **NumPy** para correlação acústica exata e rápida, além de `yt-dlp`, `ffmpeg`/`ffprobe`; recomenda **Deno >= 2.3** para o runtime JavaScript/EJS atual do YouTube e usa `faster-whisper` isolado somente como fallback textual localizado; `openai-whisper` permanece como fallback compatível
- Twitch ingest: [Bun](https://bun.sh/) no `PATH`; Playwright/Chromium são preparados automaticamente no primeiro scrape

## Início rápido

```powershell
cd K:\Applications\Youtube-Channel
python -m cstudio --root . maintain
python -m cstudio --root . new --title "Corte do hype" --source-url "https://www.twitch.tv/videos/000"
python -m cstudio --root . status
python -m cstudio --root . studio --host 127.0.0.1 --port 8765
```

No dashboard, abra **Twitch Ingest** para capturar VOD metadata/chat sem sair do Studio. Depois, **YouTube Mirrors** pode localizar e verificar masters oficiais correspondentes sem liberar direitos.
A mesma operação existe via CLI:

```powershell
python -m cstudio --root . twitch-scrape MEU-CORTE --streamer alanzoka --target 3 --threads 8
python -m cstudio --root . twitch-scrape MEU-CORTE --streamer alanzoka --target 2864229186 --force
```

O scraper V7.6 empacotado mantém resume, fallback sequencial e limite efetivo de 8 workers.
As saídas ficam em `productions/<slug>/.studio/internal/ingest/twitch/<canal>/`; os arquivos
`discovery/<vod>.json` e `chat/<vod>.json` são registrados automaticamente em `assets.csv`
com `sem_autorizacao_confirmada`. Isso **não** aprova direitos, gates nem avança o pipeline.

## YouTube Mirror Resolver

O resolver usa metadata apenas para **descobrir fontes plausíveis** e mantém a autoridade em evidência audiovisual. Cada vídeo YouTube relevante é fingerprintado uma vez e comparado contra **todos os VODs elegíveis do streamer** com correlação NumPy exata. Pares válidos são checkpointados em `assignments/`; assignments ainda inconclusivos seguem para um tiebreak textual limitado e também resumível, sem repetir fingerprints ou correlações já concluídas. Checkpoints antigos do matcher coarse são migrados localmente uma única vez. Captions do YouTube e `faster-whisper` localizado servem apenas como confirmação adicional, nunca como prova isolada. Os manifests e masters ficam em `productions/<slug>/.studio/internal/ingest/youtube/`, e downloads registrados entram em `assets.csv` como `video-source` + `sem_autorizacao_confirmada`.

```powershell
python -m cstudio --root . youtube-channel-set --streamer alanzoka --name alanzoka --url https://www.youtube.com/@alanzoka
python -m cstudio --root . youtube-index MEU-CORTE --streamer alanzoka
python -m cstudio --root . youtube-resolve MEU-CORTE --download-verified
```

`--no-download` bloqueia download mesmo quando o auto-download estiver habilitado. Fingerprints, metadata, captions, assignments e o áudio YouTube já adquirido para análise são reutilizados entre rodadas; `--force` é a forma explícita de invalidar essa retomada. Jobs iniciados pelo dashboard rodam em processo destacado e sobrevivem a restart do servidor. Downloads HLS/DASH usam 8 fragments concorrentes por padrão. Detalhes: `integrations/youtube.md`.

## Fluxo (12 stages)

```text
config → ingest → analysis → sync → highlights → cutlist[cutlist_lock]
→ assembly → graphics[graphics_lock] → composition[master_lock]
→ metadata[rights_lock] → publish[publish_lock] → learn
```

Proposta → revisão humana → aplicação:

```powershell
# manual (sempre funciona, sem CLI externo)
python -m cstudio --root . proposal-import MEU-CORTE --file proposta.json --request "cutlist inicial"
python -m cstudio --root . proposal-list MEU-CORTE
python -m cstudio --root . proposal-apply MEU-CORTE --id <id>
python -m cstudio --root . approve MEU-CORTE --gate cutlist_lock --note "revisado"
python -m cstudio --root . advance MEU-CORTE
```

## Comandos principais

| Comando | Uso |
|---|---|
| `maintain` / `status` / `validate` / `gate` | saúde do repo e da produção |
| `new --title` | cria produção (uma ativa por vez) |
| `propose --request` | roda Runner Manager (codex→opencode→openai) |
| `proposal-import/apply/discard` | fallback manual |
| `ingest --asset-id --kind --path` | registra VOD/chat/transcript |
| `twitch-scrape --streamer --target --threads` | roda scraper Twitch V7.6 e registra metadata/chat no ingest |
| `youtube-channel-set --streamer --url` | associa streamer Twitch a um ou mais canais YouTube |
| `youtube-index SLUG [--streamer]` | indexa uploads dos canais configurados sem baixar vídeo |
| `youtube-resolve SLUG [--vod-id]` | gera candidatos e verifica áudio de matches promissores |
| `youtube-verify` / `youtube-download` | verifica um par ou baixa master `verified` em qualidade máxima |
| `rights --asset --status` | libera direitos (com autor) |
| `cutlist-validate` | valida CSV (duração/overlap/ids) |
| `nle-export` | gera xmeml + scripts Resolve |
| `master --file --duration` | registra master |
| `metadata --title --description --tags` | metadados YouTube |
| `package` | package checksummed |
| `publish` / `publish --execute` | dry-run / real (bloqueado sem gates+creds) |
| `studio` | dashboard local |

## Testes

```powershell
python -m pytest tests/ -q
```

## Limitações honestas

- Sessão Z.AI não recuperável sem auth (403); sem mensagens fabricadas.
- Sem upload YouTube real neste build (dry-run + package funcionam).
- Resolve via scripts gerados (importação), não API live.
- Sem analytics fabricados; sem clearance presumida.
