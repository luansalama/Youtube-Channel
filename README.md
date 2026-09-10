# Cuts Studio v0.1.0

Harness local e determinístico para produzir **um corte/highlight Twitch → YouTube
por vez**, do config ao aprendizado — com propostas revisáveis, gates com
fingerprint e publicação bloqueada por padrão.

> Recuperação Z.AI: o endpoint público retornou `403 {"detail":"Not authenticated"}`
> (ver `CONTEXT/`). Nenhum conteúdo foi fabricado; a especificação da tarefa
> (§§ 4–19) foi usada como requisito. Molde analisado: `luansalama/Youtube-Channel`.

## Requisitos

- Python 3.11+
- Sem dependências Python obrigatórias (stdlib). Extra YouTube: `pip install -e .[youtube]`
- Twitch ingest: [Bun](https://bun.sh/) no `PATH`; Playwright/Chromium são preparados automaticamente no primeiro scrape

## Início rápido

```powershell
cd K:\Applications\Youtube-Channel
python -m cstudio --root . maintain
python -m cstudio --root . new --title "Corte do hype" --source-url "https://www.twitch.tv/videos/000"
python -m cstudio --root . status
python -m cstudio --root . studio --host 127.0.0.1 --port 8765
```

No dashboard, abra **Twitch Ingest** para capturar VOD metadata/chat sem sair do Studio.
A mesma operação existe via CLI:

```powershell
python -m cstudio --root . twitch-scrape MEU-CORTE --streamer alanzoka --target 3 --threads 8
python -m cstudio --root . twitch-scrape MEU-CORTE --streamer alanzoka --target 2864229186 --force
```

O scraper V7.6 empacotado mantém resume, fallback sequencial e limite efetivo de 8 workers.
As saídas ficam em `productions/<slug>/.studio/internal/ingest/twitch/<canal>/`; os arquivos
`discovery/<vod>.json` e `chat/<vod>.json` são registrados automaticamente em `assets.csv`
com `sem_autorizacao_confirmada`. Isso **não** aprova direitos, gates nem avança o pipeline.

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
