# Arquitetura — Cuts Studio

Derivada do molde `Youtube-Channel` (`mcstudio`), reescrita para cortes Twitch → YouTube.

## Fluxo obrigatório

```text
runner externo (read-only) → contexto + instruções → proposal JSON
→ validação determinística → revisão humana → aplicação determinística
→ evidência + fingerprint → próximo gate
```

## Stages (studio/stages.json)

`config → ingest → analysis → sync → highlights → cutlist[cutlist_lock] → assembly → graphics[graphics_lock] → composition[master_lock] → metadata[rights_lock] → publish[publish_lock] → learn`

Gates: `cutlist_lock`, `graphics_lock`, `master_lock`, `rights_lock`, `publish_lock`.

## Módulos (cstudio/)

| Módulo | Papel |
|---|---|
| `core.py` | produções, gates, fingerprints sha256, validação, packaging, recovery |
| `proposals.py` | contrato `{summary,document,files,questions,warnings}`, store, apply humano |
| `runners.py` | Codex/OpenCode/OpenAI/manual, mesma saída |
| `workspace.py` | escrita sandbox por produção |
| `session.py` | parsing Z.AI (árvore parent/children) → Markdown |
| `timecode.py` | parse/format HH:MM:SS:FF, MM:SS, segundos |
| `sync.py` | offset multi-POV (mediana nearest-neighbour) |
| `cutlist.py` | CSV + validação (duração, overlap, ids) + timeline |
| `rights.py` | registro explícito; gate bloqueia `sem_autorizacao_confirmada` |
| `security.py` | conteúdo externo = DADO; quarentena de instruções |
| `nle.py` | `NLEDriver` + `ResolveDriver` (xmeml + py/lua + runbook) |
| `pipeline.py` | ingest/score/graphics/master/metadata/publish/learn |
| `twitch.py` | wrapper do scraper V7.6, jobs/logs persistidos e import automático de metadata/chat |
| `server.py` + `dashboard.py` + `static/` | dashboard local 127.0.0.1, server-rendered, progressive enhancement, CSP/CSRF |

## Decisões

- `productions/` é o diretório canônico; `videos/` mantido como alias de leitura (compat. molde).
- Publicação real nunca executa upload: `publish --execute` retorna package + motivo sem credenciais.
- Resolve: scripts gerados, nunca "integração live" fictícia.


### Fronteira do Twitch scraper

`integrations/twitch-scraper/` é uma ferramenta de coleta vendorizada. O harness a executa
com saída forçada para a produção atual (`CSTUDIO_TWITCH_OUT`), persiste o estado da execução
e registra apenas os artefatos primários no ingest normal. O scraper nunca chama `advance`,
`approve_gate` ou altera clearance de direitos.


### Fronteira da UI

O dashboard não possui uma segunda camada de regras de negócio. `dashboard.py` renderiza estado e forms; `server.py` encaminha ações para as mesmas funções usadas pela CLI. CSS/JS em `cstudio/static/` são progressive enhancement. A atualização do Twitch usa o fragmento `GET /ui/twitch-run` e nunca cria um caminho alternativo para gates, rights ou publicação.
