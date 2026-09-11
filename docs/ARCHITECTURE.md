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
| `runners.py` | catálogo central Codex/OpenCode/Agy, seleção modelo/reasoning e contrato único; API/manual legados |
| `workspace.py` | escrita sandbox por produção |
| `session.py` | parsing Z.AI (árvore parent/children) → Markdown |
| `timecode.py` | parse/format HH:MM:SS:FF, MM:SS, segundos |
| `sync.py` | offset multi-POV (mediana nearest-neighbour) |
| `cutlist.py` | CSV + validação (duração, overlap, ids) + timeline |
| `rights.py` | registro explícito; gate bloqueia `sem_autorizacao_confirmada` |
| `security.py` | conteúdo externo = DADO; quarentena de instruções |
| `nle.py` | `NLEDriver` + `PremiereMCPDriver` (edit spec determinístico + MCP handoff + xmeml de recuperação) |
| `pipeline.py` | ingest/score/graphics/master/metadata/publish/learn |
| `source_media.py` | materialização Twitch, áudio temporário, transcrição editorial e precisão dos candidates |
| `video_plans.py` | pool compartilhado de evidência, proposals Parte 1/Parte 2 e work items de vídeo |
| `jobs.py` | workers persistidos para downloads, transcrição, proposals e preparação do Premiere |
| `twitch.py` | wrapper do scraper V7.6, jobs/logs persistidos e import automático de metadata/chat |
| `youtube_resolver.py` | config/índice YouTube, candidate scoring, verificação multi-anchor, timeline piecewise, download e jobs |
| `server.py` + `dashboard.py` + `static/` | dashboard local 127.0.0.1, server-rendered, progressive enhancement, CSP/CSRF |

## Decisões

- `productions/` é o diretório canônico; `videos/` mantido como alias de leitura (compat. molde).
- Publicação real nunca executa upload: `publish --execute` retorna package + motivo sem credenciais.
- NLE de produção: Premiere Pro MCP local/stdio; schemas descobertos em runtime, `unsafe-script` desabilitado e readback obrigatório. `nle-doctor` nunca é tratado como prova de conexão live.


### Fronteira do Twitch scraper

`integrations/twitch-scraper/` é uma ferramenta de coleta vendorizada. O harness a executa
com saída forçada para a produção atual (`CSTUDIO_TWITCH_OUT`), persiste o estado da execução
e registra apenas os artefatos primários no ingest normal. O scraper nunca chama `advance`,
`approve_gate` ou altera clearance de direitos.


### Fronteira do YouTube Mirror Resolver

`youtube_resolver.py` é outro **ingestor**, não uma etapa editorial. A cadeia atual é `Twitch VODs + índice YouTube → discovery global de fontes plausíveis → fingerprint por fonte → comparação all-VOD → consistência por offsets piecewise → captions/Whisper localizado somente se borderline → optional master download → register_asset`. Metadata score e evidência audiovisual são conceitos separados. A comparação usa correlação NumPy exata quando disponível e mantém fallback stdlib. `verified` exige evidência acústica coerente ou, em um único vencedor global borderline, áudio forte + confirmação textual localizada; texto sozinho nunca basta.

Persistência pesada é por produção em `.studio/internal/ingest/youtube/`; somente a associação streamer → canais e a preferência de auto-download são globais em `studio/youtube-mirrors.json`. Metadata, captions, fingerprints, áudio de análise YouTube e `assignments/<video_id>.json` são caches/checkpoints reproduzíveis; o áudio de análise não é registrado como asset. Cada assignment registra os VODs já avaliados e é salvo após cada par, permitindo retomada sem refazer trabalho concluído. Cada relação Twitch/YouTube continua com manifest próprio, preservando mapeamentos piecewise em cenários 1→N e N→1. Jobs do dashboard usam workers de processo com PID persistido, separados da vida do servidor HTTP. Assets resultantes continuam `sem_autorizacao_confirmada`, portanto o `rights_lock` permanece fail-closed.

### Fronteira das fontes editoriais e precisão temporal

O dashboard trata **mídia durável** e **evidência textual** como decisões independentes. Um VOD Twitch pode seguir qualquer uma destas rotas: baixar o source completo sem transcrever, transcrever um source já local, ou baixar somente a rendition de áudio para descoberta. O áudio de descoberta fica em `.studio/tmp/transcription-audio/<vod>/`, não entra em `assets.csv` e é apagado somente depois que `transcript.json` foi persistido com sucesso. Em falha, ele permanece disponível para retry.

A identidade durável da transcrição Twitch é o VOD (`twitch-vod:<id>`), e não o hash do container usado para transcrever. Portanto uma transcrição feita a partir do áudio temporário continua válida quando o MP4 completo é baixado mais tarde. O transcript de descoberta usa **timestamps por segmento** e não persiste word timestamps do VOD inteiro. No backend Faster-Whisper, discovery e candidate precision usam `WhisperModel.transcribe()` (plain); `BatchedInferencePipeline` fica reservado aos clips localizados do YouTube Mirror Resolver. Isso evita trocar granularidade editorial por throughput onde os segmentos alimentam proposals.

A política temporal é deliberadamente em três níveis:

```text
VOD completo → segment timestamps → candidate moments
→ somente candidates selecionados → word timestamps → cutlist
→ Premiere waveform/readback → frame-level + sync Twitch/YouTube
```

`candidate-word-timestamps.json` pertence ao vídeo planejado e só pode ser gerado quando as fontes físicas referenciadas pelos candidates estão disponíveis. A saída auxilia os pontos finos de entrada/saída; não substitui o waveform/readback do Premiere como autoridade final.

### Proposals editoriais por vídeo

Cada proposal editorial representa exatamente **um vídeo** e reutiliza o pool compartilhado de VODs/transcrições. O fluxo é explícito: **Parte 1** recebe a ideia geral e produz uma primeira direção baseada em evidência + perguntas dinâmicas; as respostas humanas são persistidas sem chamada de modelo; **Parte 2** reaplica essas respostas como decisões autoritativas e consolida a proposta. Uma proposal com perguntas respondidas ainda não pode ser aceita antes dessa consolidação. O download do source completo não é gate para a proposal; a transcrição canônica do VOD é.

### Catálogo de runners

`runners.py` é a única fonte de verdade para as escolhas exibidas pelo dashboard. Cada modelo possui label, lista de reasonings válidos e reasoning default. As telas de fase e de proposals de vídeo consomem esse mesmo contrato; JavaScript apenas troca as opções dependentes. Codex, OpenCode e Agy são os três CLIs de UI. OpenAI API/manual permanecem compatíveis para caminhos legados explícitos, mas não fazem parte do fallback automático, evitando troca silenciosa para um provider pago.

O OpenCode é propositalmente allowlisted para a linha Zen Free da máquina; modelos que não publicam variants executam sem `--variant`. No Agy, o dashboard usa famílias legíveis (por exemplo `gemini-3.8-flash`) e o runner converte modelo+effort ao slug concreto aceito pelo CLI (por exemplo `gemini-3.8-flash-high`).

### Fronteira da UI

O dashboard não possui uma segunda camada de regras de negócio. `dashboard.py` renderiza estado e forms; `server.py` encaminha ações para as mesmas funções usadas pela CLI. CSS/JS em `cstudio/static/` são progressive enhancement. A atualização do Twitch usa o fragmento `GET /ui/twitch-run` e nunca cria um caminho alternativo para gates, rights ou publicação.
