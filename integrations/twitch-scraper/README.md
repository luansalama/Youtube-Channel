# zai-scraper V7.6

V7.6 é uma atualização de performance do chat construída sobre a integridade e o lifecycle validados na V7.5.1.

A paginação continua usando `VideoCommentsByOffsetOrCursor` + `contentOffsetSeconds`, avançando pelo último offset retornado + 1. A V7.6 não troca esse mecanismo por probes independentes e não altera a deduplicação, resume, skip, resolução histórica do broadcast ou tratamento de VOD em andamento.

## Arquivos necessários

Para uso normal mantenha estes quatro arquivos juntos:

- `scrape.mjs`
- `v76-core.mjs`
- `vod-broadcast.mjs`
- `README.md`

## O que mudou

### 1. Fila dinâmica de tarefas

A V7.5.1 criava aproximadamente uma faixa por worker. Se uma região do VOD tivesse muito mais chat, esse worker continuava trabalhando enquanto os demais ficavam ociosos.

V7.6 cria, por padrão, aproximadamente **2 tarefas por worker** e usa uma fila compartilhada:

```text
8 workers
16 tarefas

worker termina uma tarefa
        ↓
pega imediatamente a próxima disponível
```

Cada tarefa ainda pagina normalmente dentro de sua faixa usando `last contentOffsetSeconds + 1`.

### 2. Overlap preservado

Cada fronteira mantém 60 segundos de overlap. Mensagens repetidas entre tarefas são removidas pela deduplicação global por ID.

### 3. Concorrência conservadora

- padrão: `4`
- máximo efetivo: `8`

Se você solicitar mais:

```powershell
bun run scrape.mjs alanzoka 2864229186 --threads 12
```

o terminal informa:

```text
chat concurrency: requested=12 | effective=8 (safety cap)
```

O pedido fica registrado nos diagnósticos, mas somente oito requests de chat podem trabalhar simultaneamente.

### 4. Redução adaptativa

A fila começa na concorrência efetiva escolhida. Se houver rate limiting ou falha real de request, novas tarefas podem reduzir automaticamente a pressão.

A escada de fallback é:

```text
8 → 4 → 2 → 1
4 → 2 → 1
```

Requests que já estão em voo não são cancelados. A redução afeta a próxima tarefa que cada worker tentaria consumir.

### 5. Backoff exponencial com jitter

Retries de páginas de chat agora usam atraso exponencial com jitter. Se um `Retry-After` válido for fornecido, ele tem prioridade.

### 6. Fallback sequencial continua sendo a autoridade final

Se uma ou mais tarefas não conseguirem provar cobertura depois das tentativas com concorrência reduzida, o scraper mantém o comportamento de segurança:

```text
fila dinâmica
↓
retries com menor concorrência
↓
1 worker
↓
sequential safety recovery
```

Performance pode degradar; integridade não deve ser sacrificada.

## Comandos

Últimos VODs:

```powershell
bun run scrape.mjs alanzoka 3
```

VOD específico:

```powershell
bun run scrape.mjs alanzoka https://www.twitch.tv/videos/2864229186
```

ou:

```powershell
bun run scrape.mjs alanzoka 2864229186
```

Otimização automática padrão:

```powershell
bun run scrape.mjs alanzoka 3
```

Usar até 8 workers:

```powershell
bun run scrape.mjs alanzoka 3 --threads 8
```

Modo totalmente sequencial:

```powershell
bun run scrape.mjs alanzoka 3 --sequential
```

Forçar novo download mesmo se o VOD estiver completo:

```powershell
bun run scrape.mjs alanzoka 2864229186 --force
```

Desabilitar resume:

```powershell
bun run scrape.mjs alanzoka 3 --no-resume
```

## Diagnóstico novo

`stats.integrity.segment_coverage` registra, entre outros:

- `strategy`
- `requested_concurrency`
- `effective_concurrency`
- `final_effective_concurrency`
- `safety_cap_applied`
- `tasks_per_worker`
- `segments_total`
- `concurrency_ladder`
- `adaptive_reductions`
- `queue_phases[].assignments`
- worker responsável por cada tarefa
- fallback sequencial, quando usado

Isso permite comparar tempo/carga real entre V7.5.1 e V7.6 sem inferir apenas pelo log do terminal.

## O que permanece da V7.5.1

- variáveis GraphQL capturadas dinamicamente, inclusive `hasVideoID`
- persisted-query hash capturado do browser
- URL/ID específico
- skip automático somente para arquivos realmente completos
- resume com overlap
- VOD ao vivo = `in_progress/caught_up`, nunca falso `complete`
- `latest.json` baseado no VOD mais recente por `published_at`
- broadcast histórico separado do stream atual do canal
- deduplicação global por ID
- ordenação cronológica
- terminal `hasNextPage_false` / boundary pós-duração

## Verificação offline

```powershell
node regression-v7.6.mjs
```

Para conferir uma pasta de dados:

```powershell
node verify-v7.6.mjs C:\Users\Admin\zai-scraper\data\alanzoka
```

## Nota

A GraphQL usada pelo web client da Twitch é interna e pode mudar. V7.6 conserva o template e hash observados no tráfego real e prefere fallback seguro a continuar agressivamente quando a superfície muda.
