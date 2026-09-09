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
| `server.py` + `dashboard.py` | dashboard local 127.0.0.1 |

## Decisões

- `productions/` é o diretório canônico; `videos/` mantido como alias de leitura (compat. molde).
- Publicação real nunca executa upload: `publish --execute` retorna package + motivo sem credenciais.
- Resolve: scripts gerados, nunca "integração live" fictícia.
