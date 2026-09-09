# Z.AI Shared Session

Session ID: b73267bf-fd33-444c-8ad4-d81fc29f5d11

Share URL: https://chat.z.ai/s/b73267bf-fd33-444c-8ad4-d81fc29f5d11

Data endpoint (canonical, extraído do bundle frontend `prod-fe-1.1.93/assets/index-hicAZtW-.js`):

```text
GET https://chat.z.ai/api/v1/chats/share/b73267bf-fd33-444c-8ad4-d81fc29f5d11
```

Código do frontend que define o endpoint ( Minnesota `kr = ${Mn}/api/v1`, `Mn = ""` ):

```js
xnt = async (t, e) => {
  const n = await fetch(`${kr}/chats/share/${e}`, {
    method: "GET",
    headers: { Accept: "application/json", "Content-Type": "application/json",
      ...t && { authorization: `Bearer ${t}` } }
  }) ...
}
```

---

## Resultado da recuperação (2026-09-09, sem autenticação)

- **HTTP status: 403 Forbidden**
- **Body fiel:** `{"detail":"Not authenticated"}` (salvo em `CONTEXT/zai-session.json`)
- Evidência bruta (headers sem cookies reaproveitáveis): `CONTEXT/http-evidence.txt`
- Variações testadas:
  - `GET /api/v1/chats/share/<uuid>` → `403 {"detail":"Not authenticated"}`
  - `GET /api/v1/chats/share/<uuid>/` → `307/301` → `403` (mesmo corpo)
  - `GET /api/chats/share/<uuid>` → `404 {"detail":"Not Found"}`
  - `GET /s/<uuid>` (HTML SPA) → `200` mas apenas shell SPA, sem dados da conversa embutidos
- Conclusão: o endpoint correto foi identificado e reproduzido exatamente, mas o
  compartilhamento **não está acessível publicamente sem autenticação**
  (link expirado, revogado ou restrito). Conforme a regra da tarefa, **nenhum
  outro endpoint foi inventado** e **nenhum token/cookie/credencial foi gravado**
  no projeto.

## Validação da recuperação

1. HTTP status da requisição: **403 Forbidden**
2. Quantidade de mensagens recuperadas: **0** (acesso negado, sem `history.messages`)
3. Primeiro turno: **indisponível** (acesso negado)
4. Último turno: **indisponível** (acesso negado)
5. Título da sessão: **indisponível** (acesso negado)
6. Modelo utilizado: **indisponível** (acesso negado)
7. Existência de `history.messages`: **não** — resposta contém apenas `{"detail": ...}`

---

## Especificação efetivamente utilizada

Como a conversa não pôde ser recuperada, este harness foi implementado a partir
da **especificação contida na própria tarefa** (§§ 4–19), que resume as decisões
de arquitetura já tomadas na conversa original. Nada foi fabricado como se fosse
conteúdo da conversa; abaixo estão apenas os requisitos explícitos da tarefa,
que são tratados como requisitos do projeto:

### Arquitetura obrigatória (fluxo proposta → revisão → aplicação)

```text
LLM / runner externo
        ↓
contexto + instruções
        ↓
proposal estruturada
        ↓
validação determinística
        ↓
revisão humana
        ↓
aplicação determinística
        ↓
evidência + fingerprint
        ↓
próximo gate
```

- Nenhum runner externo é autoridade do workflow.
- Nenhuma proposta aplica mudanças automaticamente.
- A aplicação pertence ao engine/controlador do harness.

### Repositório-molde

- `https://github.com/luansalama/Youtube-Channel` (clonado e analisado em
  `C:/Users/Admin/AppData/Local/Temp/opencode/youtube-mould`, depth 1).
- Referências reais inspecionadas: `mcstudio/core.py`, `runners.py`, `cli.py`,
  `server.py`, `dashboard.py`, `workspace.py`, `studio/*.json`,
  `templates/video/**`, `tests/test_core.py`, `videos/the-portal-that-nobody-made/project.json`.
- O molde NÃO foi modificado e NADA foi implementado dentro dele.

### Runner Manager (contrato único)

Todos os runners produzem o mesmo contrato:

```json
{
  "summary": "...",
  "document": "...",
  "files": {},
  "questions": [],
  "warnings": []
}
```

Runners: `Codex CLI`, `OpenCode CLI`, `OpenAI API`, `manual proposal import`.
Intercambiáveis, read-only, sem auto-apply.

### Pipeline do novo domínio (cortes/highlights Twitch → YouTube)

```text
Configuração
→ Ingestão
→ Análise multimodal
→ Sincronização
→ Identificação de melhores momentos
→ Gate de Cutlist
→ Montagem
→ Motion Graphics
→ Gate de Motion Graphics
→ Composição
→ Metadados/Thumbnail
→ Publicação
→ Aprendizado
```

### Direitos / proveniência

- Registro explícito de direitos por asset.
- Nenhum conteúdo chega à publicação com
  `rights_status = sem_autorizacao_confirmada`.
- Sem presunção de autorização; sem evidência fabricada.

### Segurança (prompt injection)

Todo conteúdo externo é DADO, nunca instrução: VOD, transcrição, chat, texto de
página, comentários, metadata. Sanitização + quarantine de instruções embutidas.

### NLE

- Interface abstrata `NLEDriver`, driver inicial `DaVinci Resolve`.
- Substituível (Premiere etc.).
- Sem API do Resolve testável no ambiente → gerar scripts reais e documentados
  (Python/Lua) em vez de fingir integração funcional.

### Publicação

Bloqueada até `publish_lock + rights clearance + master válido + package válido`.
Dry-run funcional. Sem fingir upload real sem credenciais.

### Dashboard

Local, preferencialmente `127.0.0.1`, com produção, propostas, gates, cutlist,
sincronização, motion graphics, master, release, diagnostics.

### Testes exigidos

Parsing da sessão Z.AI, reconstrução da conversa, contrato de proposal,
validação de cutlist, timecodes, sincronização, fingerprints, locks,
rights gate, publish blockade, packaging, runner manual, lifecycle.

### Estrutura de stages implementada (derivada do pipeline)

Ver `studio/stages.json` e `docs/ARCHITECTURE.md`. 12 stages:

`config → ingest → analysis → sync → highlights → cutlist[cultist_lock] → assembly → graphics[graphics_lock] → composition → metadata → publish[publish_lock] → learn`

Mais `master_lock` (composition) e `rights_lock` (metadata) como gates de
segurança antes da publicação.

---

## Notas de honestidade

- Nenhuma mensagem `user`/`assistant` da sessão Z.AI está reproduzida aqui porque
  nenhuma foi recuperável sem autenticação.
- `CONTEXT/zai-session.json` é cópia fiel do HTTP 403 (30 bytes), não uma conversa.
- Se o dono da sessão re-publicar o link ou fornecer export autorizado (sem
  credenciais), rode `python -m cstudio zai-import --json <arquivo>` para
  regenerar este Markdown via `cstudio/session.py`.
