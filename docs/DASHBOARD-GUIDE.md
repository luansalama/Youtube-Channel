# Dashboard — Cuts Studio

Inicialização:

```powershell
python -m cstudio --root . studio --host 127.0.0.1 --port 8765
```

O dashboard continua **local, server-rendered e stdlib-first**. A autoridade de negócio permanece nos módulos de domínio (`core.py`, `proposals.py`, `twitch.py`, etc.); JavaScript é apenas progressive enhancement.

## Organização da UI

A navegação principal reflete o fluxo operacional, sem expor todas as estruturas internas de uma vez:

- **Produção** — próxima ação, estado geral e compatibilidade com os stages técnicos;
- **Fontes** — captura Twitch, YouTube Mirrors, download de source, áudio temporário e transcrição;
- **Vídeos** — proposals editoriais Parte 1 → perguntas → Parte 2 e candidates;
- **Premiere** — organização de mídia, handoff e diagnóstico do MCP.

Revisões/gates técnicos continuam acessíveis como suporte ao harness legado, mas o caminho editorial cotidiano é **Fontes → Vídeos → Premiere**. Não existe light mode.

## Estrutura técnica

```text
cstudio/dashboard.py
    HTML server-rendered + fragments

cstudio/static/dashboard.css
    design system SnowUI/Cuts Studio, dark-only e responsivo

cstudio/static/dashboard.js
    drawers, confirmations, filtros, animações WAAPI e polling de jobs Twitch/YouTube

cstudio/server.py
    ThreadingHTTPServer, static assets, CSP/headers, CSRF e actions/API
```

O HTML não depende de build Node, CDN ou framework SPA. CSS e JS são package data do wheel.

## Progressive enhancement

Forms continuam sendo forms HTML tradicionais:

```text
POST /action/...
→ domínio Python
→ 303 redirect
→ página atualizada
```

Sem JavaScript, o fluxo principal continua utilizável. Com JavaScript habilitado, a UI adiciona:

- sidebar/drawer responsivo;
- painel de contexto em telas menores;
- confirmação via `<dialog>` para ações destrutivas;
- filtro client-side da cutlist;
- animações de entrada via Web Animations API;
- atualização parcial dos runs Twitch/YouTube;
- busca e filtros client-side dos assignments globais do YouTube.

Nenhuma dessas camadas pode contornar validações do backend.

## Twitch Ingest

A página **Twitch Ingest** executa o scraper V7.6 empacotado em `integrations/twitch-scraper/` e mantém a captura isolada na produção selecionada.

Controles expostos:

- `Canal Twitch`;
- `Target`: quantidade dos VODs mais recentes (`3`), ID de VOD ou URL `twitch.tv/videos/...`;
- `Workers`: `1`, `2`, `4` ou `8` (`--threads N`);
- `Sequencial`: `--sequential`, força um worker;
- `Forçar captura`: `--force`;
- `Desabilitar resume`: `--no-resume`.

A opção de 8 workers continua equivalendo literalmente a:

```text
--threads 8
```

Durante um job ativo, somente o fragmento da execução é atualizado:

```text
GET /ui/twitch-run?slug=<slug>
```

O browser consulta esse fragmento a cada ~2 s enquanto o run estiver `running`. Não existe mais reload completo da página. Quando o run termina, o polling para automaticamente.

Cada execução persiste registro e log em:

```text
.studio/internal/ingest/twitch/runs/
```

Ao terminar com sucesso, o harness registra os artefatos primários no registry normal:

```text
discovery/<vod>.json → vod-metadata
chat/<vod>.json      → chat
```

Todos entram como `sem_autorizacao_confirmada`. O scraper nunca aprova gate, altera rights ou avança stage.

API JSON de observabilidade permanece disponível:

```text
GET /api/twitch-status?slug=<slug>
```

## Fontes: download e transcrição independentes

Na aba **Fontes**, o VOD não possui mais uma única ação obrigatória “baixar + transcrever”. As operações são independentes e combináveis por VOD:

- **Baixar source completo** — materializa o Twitch VOD para edição sem exigir transcrição;
- **Transcrever source local** — usa uma mídia completa já existente;
- **Baixar só áudio** — baixa `bestaudio` para a área temporária, sem registrar como source de edição;
- **Áudio → transcrever** — baixa o áudio se necessário, gera a transcrição de descoberta e remove o áudio somente após sucesso.

Em lote, **Áudio → transcrever selecionados** processa cada VOD sequencialmente para evitar disputa desnecessária de GPU/disco. **Baixar sources selecionados** é uma ação separada. Uma falha de Whisper não apaga o áudio temporário, permitindo retry.

A transcrição completa de descoberta usa Whisper Large Turbo via Faster-Whisper **plain** (`WhisperModel.transcribe`) com **timestamps por segmento**. `word_timestamps` não são gerados para o VOD inteiro. O modo batched permanece apenas nas verificações localizadas do resolver, não na transcrição editorial usada por proposals. Depois que uma proposal vira vídeo e define candidate moments, o botão **Gerar word timestamps dos candidates** decodifica somente aqueles intervalos (com pequena margem) e persiste `candidate-word-timestamps.json`. A precisão frame-level e o sync Twitch/YouTube continuam no Premiere por waveform/readback.

## Vídeos: proposal em duas partes

Cada proposal corresponde a um vídeo. **Parte 1** parte de uma ideia geral, usa somente evidência transcrita e devolve uma proposta inicial + perguntas específicas derivadas dela. Responder às perguntas apenas salva estado local e não usa IA. Depois, **Consolidar Parte 2 com agente** aplica as respostas humanas à proposta. A ação **Aceitar e criar vídeo** só é habilitada quando não existem perguntas abertas e a Parte 2 já foi consolidada.

O MP4 completo não é requisito para iniciar a proposal: basta a transcrição canônica do VOD. O source físico passa a ser necessário quando um candidate escolhido precisar de word timestamps/cutlist ou quando a edição for efetivamente materializada.

## Seletor de CLI, modelo e reasoning

Sempre que uma ação usa agente, a UI oferece **Codex CLI**, **OpenCode CLI** e **Antigravity CLI**. Ao trocar o CLI, o dropdown de modelos é reconstruído apenas com o catálogo daquele provider; ao trocar o modelo, o reasoning mostra apenas os níveis válidos daquele modelo. Isso vale tanto para o assistente de cada fase quanto para Parte 1/Parte 2 das proposals de vídeo.

Defaults: OpenCode = **Muse Spark 1.3 Free / xhigh**; Agy = **Gemini 3.8 Flash / high**. OpenCode mostra somente o lineup gratuito allowlisted. Quando um modelo free não possui variant selecionável, a única opção é `Default · model-managed`, que omite `--variant`. Agy mostra também os modelos Claude/GPT disponíveis no plano Free, lembrando que a conta continua sujeita às quotas do plano/modelo. OpenAI API não aparece nesse seletor nem no fallback automático.

## YouTube Mirrors

A página **YouTube Mirrors** é operacional e usa a mesma camada `cstudio.youtube_resolver` da CLI. A apresentação é **assignment-global first**: cada vídeo YouTube possui uma decisão principal (`VERIFIED`, `NO MATCH` ou em progresso), e estados locais como `candidate`, `likely` e `ambiguous` aparecem somente dentro da evidência técnica de cada par VOD↔vídeo. Isso evita apresentar um par local como pendência quando o assignment global já terminou.

A tela principal mostra KPIs de cobertura, busca e filtros por estado, uma lista compacta dos assignments e uma grade **VOD coverage** que contém apenas mirrors `VERIFIED`. `NO MATCH` é exibido como decisão terminal, nunca como “pendente”. A matriz de VODs, metadata prior, anchors, timeline, fallback textual e controles de reverificação/rejeição ficam em um painel expansível por vídeo. O catálogo de VODs pode ser reconstruído dos manifests YouTube persistidos, então a leitura histórica continua útil mesmo quando o ingest Twitch pesado não está presente no snapshot.

O painel **Storage planning** mostra o tamanho estimado de cada source Twitch e de cada master YouTube `VERIFIED`, os totais agregados, o pior caso de manter Twitch + YouTube e o espaço livre do volume da produção. **Atualizar tamanhos** executa somente consultas de metadata via yt-dlp; não baixa mídia. `filesize` e arquivos locais são tratados como tamanho exato; `filesize_approx` ou `bitrate × duração` aparecem com `~`.

O job atual fica compacto: durante execução o log abre para acompanhamento ao vivo; depois de concluído ele fica recolhido por padrão, preservando o log completo, scroll e botão de cópia. Configuração de canais também fica em painel recolhível para não competir com os resultados.

Ações disponíveis: cadastrar/ativar/desativar canais, `Refresh index`, `Resolve production`, `Atualizar tamanhos`, reverificar/rejeitar pares na área técnica, `Download master` e `Auto-download verified sources`. Operações longas iniciam jobs em background e atualizam somente o fragmento:

```text
GET /ui/youtube-run?slug=<slug>
```

Os jobs longos de YouTube iniciados pelo dashboard rodam em **processos destacados**, com PID e log persistidos. Além disso, `Resolve production` é incremental: cada vídeo relevante é comparado contra todos os VODs elegíveis e o assignment é salvo depois de cada par. Reexecutar o comando pula assignments concluídos e continua assignments parciais somente nos VODs faltantes; `--force` força recálculo. O polling para quando o job deixa `running`; um restart do servidor HTTP não encerra o worker, e o dashboard só marca um job antigo como falho quando o PID persistido realmente não está mais ativo. Falhas externas são persistidas como `failed`, nunca mascaradas como `completed`.

## Segurança do dashboard

O servidor adiciona uma Content Security Policy sem `unsafe-inline`:

```text
default-src 'self'
script-src 'self'
style-src 'self'
connect-src 'self'
form-action 'self'
frame-ancestors 'none'
object-src 'none'
```

Também envia headers de hardening, incluindo `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cross-Origin-Opener-Policy` e `Permissions-Policy`.

Forms renderizados pelo servidor recebem um token CSRF por processo. POSTs de browser com `Sec-Fetch-Site: cross-site` são recusados antes da mutação. JSON/API sem sessão continua compatível com os clientes locais existentes.

Valores de Twitch, logs, nomes, proposals e paths são escapados antes de entrar no HTML.

## Responsividade e movimento

- desktop largo: sidebar + workspace + contexto;
- desktop/laptop: contexto vira drawer;
- tablet/mobile: sidebar vira drawer;
- tabelas usam scroll horizontal quando necessário;
- `prefers-reduced-motion: reduce` elimina animações não essenciais;
- a única animação contínua relevante é o indicador de job Twitch enquanto ele está realmente rodando.

## Endpoints principais

```text
GET  /
GET  /health
GET  /api/status
GET  /api/twitch-status
GET  /api/youtube-status
GET  /ui/twitch-run
GET  /ui/youtube-run
GET  /static/dashboard.css
GET  /static/dashboard.js

POST /action/approve
POST /action/advance
POST /action/apply-proposal
POST /action/discard-proposal
POST /action/new
POST /action/pause
POST /action/resume
POST /action/abandon
POST /action/twitch-scrape
POST /action/source-download-twitch
POST /action/source-batch-download-twitch
POST /action/source-download-audio
POST /action/source-audio-transcribe
POST /action/source-batch-audio-transcribe
POST /action/source-transcribe
POST /action/video-proposal-run
POST /action/video-proposal-answers
POST /action/video-proposal-refine
POST /action/video-proposal-accept
POST /action/video-candidate-precision
POST /action/youtube-channel-set
POST /action/youtube-channel-toggle
POST /action/youtube-auto-download
POST /action/youtube-index
POST /action/youtube-resolve
POST /action/youtube-verify
POST /action/youtube-download
POST /action/youtube-reject
POST /action/maintain
```

A regra continua sendo:

```text
Dashboard/CLI → mesma função de domínio → mesma validação → mesma persistência
```
