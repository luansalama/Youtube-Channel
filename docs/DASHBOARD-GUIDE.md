# Dashboard — Cuts Studio

Inicialização:

```powershell
python -m cstudio --root . studio --host 127.0.0.1 --port 8765
```

O dashboard continua **local, server-rendered e stdlib-first**. A autoridade de negócio permanece nos módulos de domínio (`core.py`, `proposals.py`, `twitch.py`, etc.); JavaScript é apenas progressive enhancement.

## Organização da UI

A navegação foi reorganizada para refletir o harness em vez de um template genérico de analytics:

- **Operação**
  - Visão geral
  - Captura Twitch
- **Revisão humana**
  - Propostas
  - Aprovações
- **Construção**
  - Cutlist
  - Sincronização
  - Gráficos
  - Master
  - Release
- **Sistema**
  - Diagnóstico

A Visão geral prioriza **Próxima ação**, readiness da fase, propostas pendentes, gates e posição no pipeline. Não existe light mode.

## Estrutura técnica

```text
cstudio/dashboard.py
    HTML server-rendered + fragments

cstudio/static/dashboard.css
    design system SnowUI/Cuts Studio, dark-only e responsivo

cstudio/static/dashboard.js
    drawers, confirmations, filtros, animações WAAPI e polling Twitch

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
- atualização parcial do run Twitch.

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
GET  /ui/twitch-run
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
POST /action/maintain
```

A regra continua sendo:

```text
Dashboard/CLI → mesma função de domínio → mesma validação → mesma persistência
```
