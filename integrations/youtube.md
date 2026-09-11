# YouTube integration — Mirror Resolver

O **YouTube Mirror Resolver** é um ingestor local que encontra versões oficiais/permitidas no
YouTube para VODs Twitch já presentes em uma produção. Ele pode descobrir, indexar, comparar,
verificar, baixar e registrar mídia-fonte. Ele **não** aprova direitos, gates, stage editorial
ou publicação.

## Dependências

Obrigatórias para uso real:

- `numpy` — correlação acústica exata/vetorizada e extração de features acelerada;
- `yt-dlp` — catálogo, metadata, captions, áudio de verificação e download do master;
- `ffmpeg` — decode/normalização do áudio;
- `ffprobe` — inspeção da mídia baixada.

Fortemente recomendado para a extração YouTube atual:

- **Deno >= 2.3.0** — runtime JavaScript/EJS recomendado pelo yt-dlp. Quando disponível, o
  resolver injeta explicitamente `--js-runtimes deno:<path>` em index, metadata, captions,
  áudio e master. Sem Deno suportado o health fica degradado, mas o resolver mantém fallback
  para instalações/extrações do yt-dlp que ainda funcionem sem challenge solving.

Backend textual, usado somente quando necessário:

- `faster-whisper` + CTranslate2 + `large-v3-turbo` — preferido;
- `openai-whisper` — fallback compatível no mesmo ambiente.

Opcional:

- `fpcalc`/Chromaprint — **shadow verifier**. Pode gerar evidência acústica paralela quando o
  áudio já está local, mas não participa da decisão `verified`.

Overrides relevantes:

```text
CSTUDIO_YTDLP
CSTUDIO_FFMPEG
CSTUDIO_FFPROBE
CSTUDIO_DENO
CSTUDIO_FPCALC
CSTUDIO_WHISPER
CSTUDIO_TRANSCRIPTION_BACKEND
CSTUDIO_FASTER_WHISPER_MODEL
CSTUDIO_FASTER_WHISPER_COMPUTE_TYPE
CSTUDIO_FASTER_WHISPER_BATCH_SIZE
CSTUDIO_WHISPER_PYTHON
CSTUDIO_WHISPER_HOME
CSTUDIO_WHISPER_MODEL
CSTUDIO_WHISPER_DEVICE
CSTUDIO_WHISPER_LANGUAGE
CSTUDIO_WHISPER_LANGUAGE_<STREAMER>
CSTUDIO_WHISPER_ENABLED
CSTUDIO_YTDLP_FRAGMENTS
CSTUDIO_YOUTUBE_ANALYSIS_CACHE_GB
```

Nenhum comando externo usa `shell=True`; argumentos são passados como lista. Conteúdo retornado
por YouTube/Twitch é dado não confiável e nunca vira instrução para o harness.

## Configuração de canais

A associação Twitch streamer → canais YouTube é persistida em:

```text
studio/youtube-mirrors.json
```

Ela aceita vários canais por streamer e cada canal pode ser desabilitado sem alterar código.
URLs/canais nunca são hardcoded. Quando um `channel_id` imutável (`UC...`) é conhecido, ele é
**hard gate**: um vídeo que revele outro channel ID é descartado antes de mídia cara. Se a config
só tiver URL/handle, o resolver pode aprender e persistir o channel ID observado para aquela URL
sem sobrescrever um ID conflitante já salvo.

O hint de idioma Whisper é configurável por streamer. `alanzoka` usa `pt` como default; `auto`
remove o hint.

```powershell
python -m cstudio --root . youtube-channel-set --streamer alanzoka --name alanzoka --url https://www.youtube.com/@alanzoka --language pt
```

## Indexação barata

```powershell
python -m cstudio --root . youtube-index <slug> --streamer alanzoka
python -m cstudio --root . youtube-index <slug> --streamer alanzoka --refresh-index
```

O indexador usa `yt-dlp --flat-playlist --dump-json --skip-download` e acrescenta
`youtubetab:approximate_date`. Isso mantém o catálogo barato, mas recupera data/timestamp
aproximados quando o extractor consegue fornecê-los; a data é apenas filtro de shortlist, nunca
prova de identidade.

O baseline de catálogo continua limitado e previsível. O índice não baixa vídeo. Metadata
externa passa pelo scanner de segurança antes de persistência/renderização.

## Candidate score e metadata cache

`candidate_score` existe apenas para descobrir quais **fontes YouTube** são plausíveis para a
produção. Ele combina
quando disponíveis:

- proximidade de data;
- compatibilidade de duração/subset;
- similaridade do título;
- overlap semântico simples de jogo/chapters.

Canal não recebe mais bônus constante: channel ID conhecido é gate.

Campos desconhecidos são **neutros**. O resolver não concede score artificial para `date` ou
`duration` ausentes; ele renormaliza os pesos dos sinais realmente disponíveis. O score não é
probabilidade e nunca produz `verified` sozinho.

Antes da mídia, metadata detalhada de cada YouTube ID é cacheada por produção e reutilizada entre
VODs. Consultas metadata-only usam `youtube:skip=hls,dash` para não buscar manifests que não são
necessários. O TTL padrão é sete dias.

## Assignment global — uma fonte contra todos os VODs

O resolver não limita mais a fase cara aos `N` melhores candidatos de cada VOD. Esse modelo
perdia episódios que ficavam em 5º/6º lugar quando vários vídeos do mesmo jogo tinham metadata
parecida.

O fluxo atual é orientado por fonte:

1. percorre o índice e monta um conjunto deduplicado de vídeos relevantes usando score, overlap
   de capítulos/jogos e caches existentes;
2. enriquece metadata de cada YouTube ID no máximo uma vez por TTL;
3. cria/reutiliza o fingerprint do vídeo YouTube uma vez;
4. compara essa fonte contra **todos os VODs do mesmo streamer** que não forem impossíveis por
   data;
5. persiste o resultado depois de cada `(youtube_id, vod_id)`;
6. escolhe o melhor VOD globalmente, em vez de escolher os melhores vídeos dentro de cada VOD;
7. se a fase acústica não resolver, até três VODs ainda plausíveis podem entrar em um tiebreak
   textual localizado e resumível; isso inclui pares `candidate` com múltiplos anchors acústicos
   moderados, não apenas `likely`.

Isso transforma o custo de rede em custo **por fonte**, não por par. Depois que fingerprints
existem, comparar dezenas de pares é cálculo local.

## Resume/checkpoint

Cada vídeo recebe:

```text
assignments/<youtube_video_id>.json
```

O arquivo contém `policy_version`, `matcher_engine`, `evaluated_vod_ids`, `pair_results`,
`deep_resolution`, `primary_vod_id` e estado final. Ele é salvo após **cada par** e após cada
tentativa textual profunda, não apenas no final do job. Portanto:

- processo encerrado no meio → a próxima rodada continua nos VODs que faltam;
- vídeo já comparado contra todos os VODs, mas ainda inconclusivo → continua somente na etapa
  profunda; os pares acústicos válidos não são refeitos;
- `VERIFIED` ou deep-resolution concluída/exaurida → o assignment é terminal e é pulado inteiro;
- novo VOD adicionado → somente o novo VOD é comparado aos assignments existentes;
- novo vídeo no índice → apenas esse vídeo cria trabalho novo;
- `--force` invalida intencionalmente o reaproveitamento e recalcula.

Checkpoints antigos criados pelo matcher `stdlib-coarse` são migrados uma única vez: os
fingerprints existentes são preservados e somente a correlação local é refeita com
`numpy-exact`. Depois disso, o novo resultado volta a ser resumível normalmente.

Rejeição manual também invalida o resumo final do assignment para que a próxima rodada escolha o
próximo melhor VOD sem refazer os pares já avaliados.

## Verificação acústica — autoridade do match

A autoridade continua sendo áudio multi-anchor. O fingerprint de features permanece compatível
com os caches existentes (`ffmpeg-temporal-features-v1`); a política de matching é versionada
separadamente como `ffmpeg-temporal-features-v3-piecewise-offset`.

Para cada par avaliado no assignment global:

1. o resolver reutiliza fingerprint existente quando possível;
2. se o YouTube ainda precisa de áudio completo para gerar fingerprint, o bestaudio adquirido é
   guardado em `analysis-audio/` para reuso local;
3. quatro anchors distribuídos no vídeo YouTube são comparados com o VOD Twitch;
4. o primeiro anchor pode fazer busca global;
5. anchors seguintes começam em uma janela prevista a partir do alinhamento anterior;
6. se a janela prevista for fraca, existe fallback de busca para frente para não perder matches
   com cortes longos;
7. a correlação global exige **NumPy** e avalia todos os frames de 0,5 s, sem o sampling coarse
   que podia saltar um pico verdadeiro; se o processo do dashboard não conseguir importar NumPy,
   o resolve falha cedo com instrução para instalar o projeto no mesmo ambiente Python, em vez de
   degradar silenciosamente para um matcher menos confiável;
8. cada busca registra melhor pico, segundo melhor pico e `peak_margin` para observabilidade;
9. a decisão temporal usa `offset = twitch_time - youtube_time`: offsets aproximadamente estáveis
   representam continuidade, e saltos positivos podem representar material removido do upload;
10. salto grande para trás enfraquece a consistência e impede `VERIFIED`.

`peak_margin` ainda é métrica de diagnóstico, não threshold de autoridade: ele precisa ser
calibrado com ground truth real antes de participar da decisão.

### Chromaprint em shadow mode

Se `fpcalc` estiver instalado e a mídia necessária já estiver local, o resolver também pode gerar
um fingerprint Chromaprint e calcular anchors paralelos. O resultado aparece em:

```text
verification.audio.chromaprint_shadow
```

com `authority=false`. A ausência de `fpcalc` não muda o resultado, e Chromaprint nunca causa
um download extra apenas para alimentar o shadow verifier. Isso permite coletar comparação real
antes de qualquer futura promoção de provider.

## Texto localizado: captions primeiro, Whisper depois

Texto só entra depois que todos os pares acústicos baratos já foram comparados. O resolver escolhe
no máximo três VODs inconclusivos que tenham pelo menos dois anchors localizados com similaridade
acústica moderada e usa texto como **gate secundário**. Texto sozinho nunca cria `VERIFIED`:
ele apenas promove um par quando as localizações vieram do áudio e pelo menos dois anchors
textuais confirmam o mesmo VOD. As tentativas ficam registradas em `deep_resolution`, portanto um
restart continua do VOD profundo ainda não tentado em vez de repetir transcrições concluídas.

Para YouTube, a ordem é:

1. procurar cache de captions;
2. se não houver, tentar subtitles/auto-subs via yt-dlp sem baixar vídeo;
3. converter WebVTT em segmentos timestamped, removendo duplicação cumulativa comum em auto-captions;
4. usar apenas o texto da janela correspondente ao anchor;
5. se captions não existirem, cair no fluxo de clip de áudio + faster-whisper.

Para Twitch, o resolver usa as janelas acústicas localizadas e faster-whisper. Isso evita pagar
o custo de três/quatro downloads pequenos do YouTube quando o próprio YouTube já oferece
transcrição timestamped.

### Runtime faster-whisper

`transcription.backend=auto` prefere faster-whisper quando existe modelo CTranslate2 local. O
default permanece:

```text
model = large-v3-turbo
device = cuda
compute_type = float16
batch_size = 8
beam_size = 5
vad = on
condition_on_previous_text = false
timestamps = segment
```

O runner é isolado do Python do dashboard. No Windows ele adiciona `torch\lib` do venv ao `PATH`
quando presente para reutilizar DLLs CUDA/cuBLAS/cuDNN do ambiente. Um único processo carrega o
modelo uma vez para o batch de clips da fonte.

OpenAI Whisper permanece fallback e também usa `--condition_on_previous_text False`. O quality
gate continua rejeitando loops/hallucination caches e caches antigos incompatíveis.

## Cache persistente

Dados técnicos ficam sob:

```text
productions/<slug>/.studio/internal/ingest/youtube/
    index/
    metadata/
    captions/
    fingerprints/
        twitch-<vod_id>.features.json
        youtube-<video_id>.features.json
        twitch-<vod_id>.chromaprint.json        # opcional
        youtube-<video_id>.chromaprint.json     # opcional
    transcripts/twitch/
    transcripts/youtube/
    analysis-audio/
    assignments/
    matches/
    jobs/
    logs/
    media/<streamer>/<video_id>/
    tmp/
```

`analysis-audio/` é cache técnico, nunca asset/master. O default de limite é **4 GiB**, ajustável
por `CSTUDIO_YOUTUBE_ANALYSIS_CACHE_GB`; o pruning usa recência de acesso. Isso permite que uma
segunda verificação recorte localmente em vez de reabrir o YouTube para cada janela.

Metadata e captions têm TTL padrão de sete dias e também possuem negative cache para captions
indisponíveis, evitando consultas repetidas do mesmo candidato.

`assignments/` não tem TTL. A validade dos pares é controlada por `policy_version` e
`matcher_engine`; a validade da segunda etapa é controlada separadamente por
`deep_resolution.policy_version`. Isso permite evoluir o desempate textual sem invalidar
fingerprints ou comparações acústicas já corretas.

## Timeline mapping

Cada par Twitch/YouTube mantém anchors e segmentos piecewise. Além de slope/confidence, os
segmentos registram offsets inicial/final e classificam saltos compatíveis com cut gap:

```json
{
  "youtube_start": 120.0,
  "youtube_end": 900.0,
  "twitch_start": 4385.0,
  "twitch_end": 5168.0,
  "slope": 1.00385,
  "confidence": 0.94,
  "offset_start": 4265.0,
  "offset_end": 4268.0,
  "offset_delta": 3.0,
  "kind": "continuous"
}
```

Helpers de domínio fazem `youtube_time → twitch_time` e `twitch_time → youtube_time` apenas
quando o instante cai em um segmento conhecido. Lacunas/cortes permanecem sem mapeamento.
Par-manifests independentes preservam 1 VOD → N vídeos e N VODs → 1 master.

## Jobs resilientes do dashboard

CLI explícita (`youtube-index`, `youtube-resolve`, `youtube-sizes`, `youtube-verify`, `youtube-download`) continua
síncrona e retorna código de saída normal.

O dashboard, porém, não executa mais jobs longos em daemon thread. `start_job()`:

1. persiste o registro do job;
2. inicia `python -m cstudio ... youtube-job-worker` como processo destacado;
3. persiste `worker_pid` e `worker_mode=process`;
4. o worker escreve diretamente status/log/result no job;
5. restart/encerramento do servidor HTTP não mata o worker;
6. ao reabrir, jobs `running` só viram `failed` se o PID persistido não estiver ativo.

No Windows a checagem de PID usa a API de processo do sistema, não `os.kill(pid, 0)`, evitando
que uma simples health check possa sinalizar/encerrar o worker.

Continua existindo no máximo um job YouTube incompatível por produção.

## Download do master

Download automático acontece somente para `verified`, salvo override manual explícito:

```powershell
python -m cstudio --root . youtube-download <slug> --vod-id 1234567890 --video-id ABCdef12345
```

O comando usa `bv*+ba/b` e merge via FFmpeg, sem limite artificial de 1080p; 2160p/4K é usado
quando for a melhor qualidade disponível. As mesmas opções de runtime Deno/EJS são aplicadas ao
master.

## Planejamento de armazenamento

Antes de baixar mídia, o dashboard pode consultar apenas metadata e estimar o espaço das sources:

```powershell
python -m cstudio --root . youtube-sizes <slug> --force
```

O cálculo usa o mesmo seletor `bv*+ba/b` do download real. Para cada master YouTube `VERIFIED`
e cada VOD Twitch conhecido, o resolver prefere `filesize`, depois `filesize_approx`; quando o
servidor não informa tamanho, usa `bitrate × duração`. Valores derivados aparecem como estimativa
na UI. Se um master YouTube já existe localmente, o tamanho do arquivo em disco passa a ser a
autoridade. O job de tamanhos é metadata-only e não baixa o payload audiovisual.

## Direitos

Todo asset YouTube entra obrigatoriamente como:

```text
sem_autorizacao_confirmada
```

Encontrar a mesma live em um canal oficial **não** é clearance para republicação. O resolver não
chama `approve_gate`, não altera `rights_lock`, não avança stage e não publica.

## Dashboard

A página **YouTube Mirrors** exibe health de yt-dlp/FFmpeg/Deno/Whisper, canais, índice, VODs,
assignments globais, evidência técnica e um painel de storage com tamanho por VOD Twitch, tamanho
por master YouTube `VERIFIED`, total combinado e espaço livre no volume da produção. Ausência de
Deno suportado aparece como degradação explícita.

O browser consulta `GET /ui/youtube-run` enquanto houver job ativo. Falhas ficam persistidas como
`failed`; restart do dashboard não é tratado como falha se o worker continua vivo.

## Upload/publicação

Este resolver não implementa upload para o YouTube. A publicação continua sob o fluxo existente
de package/gates/credenciais e permanece separada deste ingestor.
