# Whisper word_timestamps — Benchmark local (RTX 4070 SUPER)

Data: 2026-09-11 (UTC-3, máquina local Windows)
Pasta isolada (fora do harness): `K:\Applications\Youtube-Channel\.studio-benchmark\whisper-word-timestamps\`
Nenhum arquivo de `cstudio/`, dashboard, resolver, pipeline, schemas ou tests foi alterado.
Nenhum modelo, VOD, transcript, cache ou venv foi apagado. Nenhuma transcrição em andamento foi interrompida (nenhum `python.exe` de transcrição ativo no início).

## 1. Ambiente detectado (real, não suposição)

- Python Whisper: `K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe`
  - `sys.version`: `3.11.15 (main, Jun 11 2026, 04:59:07) [MSC v.1944 64 bit (AMD64)]`
- `torch==2.6.0+cu124`, `torch.version.cuda=12.4`, `torch.cuda.is_available()=True`
  - GPU: `NVIDIA GeForce RTX 4070 SUPER`, capability `(8, 9)`, 12281 MB, 56 SMs, L2 48 MB
  - `torch/lib`: `cublas64_12.dll`, `cublasLt64_12.dll`, `cudart64_12.dll`, `cudnn_*_9.dll`, `nvrtc-builtins64_124.dll`, `torch_cuda.dll` (runtime bundled com o wheel, não requer CUDA Toolkit global)
- `openai-whisper==20250625` em `K:\Applications\LLMS\Whisper\.venv\Lib\site-packages\whisper\`
- `faster-whisper==1.2.1`, `ctranslate2==4.8.2`, `ctranslate2.get_cuda_device_count()=1`
- `triton` antes: ausente (`find_spec(triton)=None`, `find_spec(triton_windows)=None`)
- `triton` depois (instalação experimental registrada abaixo): `triton==3.2.0` via `triton-windows==3.2.0.post21`
- Executável `whisper` resolvido: `K:\Applications\LLMS\Whisper\.venv\Scripts\whisper.exe` (do venv, não global)
- `where.exe`/`Get-Command`: `python` global em `K:\Applications\Python 3.11.9\python.exe`, venv em `...\Whisper\.venv\Scripts\python.exe`; `nvcc`: não encontrado em nenhum PATH
- `PATH`: contém `K:\Applications\LLMS\Whisper\.venv\Scripts`, `C:\Users\Admin\AppData\Local\ffmpeg\bin`, `C:\Program Files\NVIDIA Corporation\NVIDIA App\NvDLISR`, sem entrada de CUDA Toolkit
- `CUDA_PATH=` (vazio), `CUDA_HOME=` (vazio)
- CUDA Toolkit global: `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA` inexistente; `where nvcc` vazio; `Get-Command nvcc` vazio
- Driver: `NVIDIA-SMI 616.56`, KMD 616.56, CUDA UMD 13.4, WDDM, driver `32.0.16.1656`
- FFmpeg: `9.0.1-essentials_build-www.gyan.dev`, `C:\Users\Admin\AppData\Local\ffmpeg\bin\ffmpeg.exe`
- Modelos locais verificados:
  - `K:\Applications\LLMS\Whisper\large-v3-turbo.pt` (1617941637 bytes)
  - `K:\Applications\LLMS\Whisper\faster-whisper-large-v3-turbo\model.bin` (1617884929 bytes) + `config.json`, `tokenizer.json`, `vocabulary.json`
- Pipeline editorial atual (lido em `cstudio/source_media.py` + `cstudio/youtube_resolver.py`, sem alterar):
  - CLI equivalente: `python -m whisper AUDIO --model turbo --model_dir K:\Applications\LLMS\Whisper --output_dir TMP --output_format json --verbose False --task transcribe --word_timestamps True --condition_on_previous_text False --device cuda --language pt`
  - `model=turbo` + `model_dir` preserva alias oficial para `large-v3-turbo.pt`
  - `chunk_seconds=1800` (30 min), `progress.json` confirma `twitch-video-2861744268`: 25966.884 s, 15 chunks, `language=pt`, `word_timestamps=true`, `device=cuda`, `model=turbo`

Conclusão Fase 1: inferência CUDA saudável; ausência de CUDA Toolkit global confirmada por inspeção direta (pasta, `nvcc`, `CUDA_PATH/HOME`, PATH), não apenas pelo warning.

## 2. Causa do fallback Triton (exata, reproduzida)

Arquivo: `K:\Applications\LLMS\Whisper\.venv\Lib\site-packages\whisper\timing.py`

- `median_filter()` (linhas 36-45): tenta `from .triton_ops import median_filter_cuda`; captura `except (RuntimeError, subprocess.CalledProcessError)` e emite `timing.py:42 ... falling back to a slower median kernel`.
- `dtw()` (linhas 141-149): tenta `dtw_cuda()` → `from .triton_ops import dtw_kernel`; captura mesmos exceptions e emite `timing.py:146 ... falling back to a slower DTW`.
- `whisper/triton_ops.py` linhas 6-10: `try: import triton ... except ImportError: raise RuntimeError("triton import failed; try pip install --pre triton")`.

Reprodução isolada (sem inferência completa):
- `from whisper.triton_ops import median_filter_cuda` → `ModuleNotFoundError: No module named 'triton'` encapsulado em `RuntimeError: triton import failed`.
- `median_filter(torch.randn(..., device='cuda'), 7)` + `dtw(...)` emitem ambos warnings e caem para `sort()[...]` e `dtw_cpu` (numba).

Portanto a causa nesta máquina é **import do Triton ausente**, não compilação, driver, compiler, PATH ou versão. O texto do warning (“likely due to missing CUDA toolkit”) é enganoso: o `except` cobre qualquer `RuntimeError`, incluindo módulo inexistente. CUDA Toolkit global ausente é real, mas irrelevante para o fallback atual — e irrelevante para `triton-windows>=3.2.0.post13`, que já traz compiler+Cuda bundlados.

## 3. Amostra (mesmo arquivo para todos os benchmarks)

- Origem sem cópia de VOD inteiro: `.../.studio/internal/ingest/twitch/media/2861744268/2861744268.mp4` (24790942720 bytes, 25966.884 s, aac 48 kHz + h264)
- Derivação via FFmpeg para pasta temporária fora dos assets oficiais:
  - `ffmpeg -hide_banner -y -ss 600 -i 2861744268.mp4 -t 600 -vn -ac 1 -ar 16000 -c:a pcm_s16le sample_10min_16k_mono.wav`
  - Resultado: `K:\Applications\Youtube-Channel\.studio-benchmark\whisper-word-timestamps\sample_10min_16k_mono.wav`, 19200078 bytes, 600.000 s, `pcm_s16le 16000 Hz mono`
  - Janela: 600-1200 s do VOD (10-20 min, fala densa PT, sem música de intro). Mesmo WAV 16 k usado em A/B/C/D.

## 4. Benchmarks (mesmo WAV 600 s, `language=pt`, `condition_on_previous_text=False`, `device=cuda`)

Scripts isolados (não integrados ao harness):
- `bench_openai.py` (load + transcribe via `whisper.load_model(turbo, device=cuda, download_root=K:\Applications\LLMS\Whisper)`)
- `bench_faster.py` (via `WhisperModel` plain ou `BatchedInferencePipeline`, `local_files_only=True`)
- Warm-up: forward dummy (falhou por shape proposital, registrado) + run1 inclui init CUDA/numba/triton-JIT; run2 é steady-state. Reporto ambos; comparação justa usa run2.

| Backend | Word timestamps | Triton | Tempo run1 (cold) | Tempo run2 (warm) | RTF run2 | VRAM | Segs | Words | Observações |
|---|---|---|---|---|---|---|---|---|---|
| A OpenAI Turbo | False | n/a (sem align) | 31.21 s | 23.37 s | 0.039 | torch 3.26 GB | 237 | 0 | baseline sem words; load ~10.1 s |
| B OpenAI Turbo | True | fallback (ausente) | 41.44 s | 27.56 s | 0.046 | torch 3.54 GB | 227 | 1312 | estado atual; 2 warnings; load ~7.5 s |
| C OpenAI Turbo | True | `triton-windows==3.2.0.post21` funcional | 28.62 s | 25.67 s | 0.043 | torch 3.54 GB | 227 | 1312 | sem warnings; load ~6.8 s |
| D FW plain `float16` | True | n/a (CTranslate2) | 15.28 s | 15.06 s | 0.025 | pico total nvidia-smi 3559 MiB (~2.4 GB líquido além de 1140 idle) | 245 | 1329 | apples-to-apples; load ~1.7 s; `beam=5 batch=8` |
| D FW batched `float16 b8` | True | n/a | 4.65 s | 4.05 s | 0.007 | torch 0.00 (não rastreia CTranslate2) | 16 | 1237 | 6x mais rápido mas segmentos longos (~37 s média) e -7% words vs plain |

Notas:
- `median_total_s` nos JSONs usa lógica “upper-median” para n=2; para relatório use run2 (warm) como mediana steady-state e run1 como cold. Com n=2, média seria (run1+run2)/2, mas esconderia efeito warmup; por isso tabela mostra ambos.
- FW VRAM via `torch.cuda.max_memory_allocated` é 0.00 por design (CTranslate2 aloca fora do torch). Medição real via `nvidia-smi --query-gpu=memory.used` a 1 s durante D-plain: idle 1140 MiB → pico 3559 MiB.
- D-batched segmentos 16 vs OpenAI 227: mesmo conteúdo textual, granularidade diferente (ex.: 0-31.82 s em um segmento FW vs 10+ segmentos OpenAI). Words similares em texto, mas contagem -75 words (-5.7%) vs B/C.
- D-plain segmentos 245 vs OpenAI 227: granularidade equivalente (2-3 s média), words +17 (+1.3%), esperado por `beam_size=5` (FW) vs greedy+temperature (OpenAI).

## 5. Impacto do alinhamento (`word_timestamps=True` vs `False`, OpenAI)

Steady-state (run2, mesma máquina, mesmo WAV):
- A 23.37 s → B 27.56 s: **+4.19 s (+17.9%) para 10 min**, +0.007 RTF (0.039→0.046), +0.28 GB VRAM.
- Cold (run1, inclui compilação numba na primeira vez): 31.21 s → 41.44 s: +10.23 s (+32.8%).
- Extrapolação linear ingênua para VOD 25966 s: +181 s (~3 min) de custo align em ~17-20 min totais. Porém `find_alignment` faz DTW `tokens × frames` global por chunk; custo escala ~quadrático com `chunk_seconds`. Chunks de 30 min (1800 s) sofrem mais que 3×10 min. Isso reconcilia observado “2m50s-3m por chunk 30 min” (média 164 s/chunk em 41 min totais para 15 chunks) vs 27.6 s/10 min medidos aqui (que dariam ~83 s/30 min lineares). Não afirmei 30 min sem medir; deixo como hipótese quantificada a validar com um run 30 min futuro se necessário.

## 6. Impacto do Triton (B fallback vs C funcional, mesmo áudio/parâmetros)

- Warnings somem 100% (validado com `warnings.simplefilter('error')`: `median_filter` + `dtw` CUDA passam sem exceção).
- Run2: 27.56 s → 25.67 s: **-1.89 s (-6.9%) para 10 min**, -0.003 RTF.
- Run1: 41.44 s → 28.62 s: -12.82 s (-30.9%), porque evita compilação numba `dtw_cpu` na primeira vez (troca por JIT Triton, mais barato neste caso).
- Qualidade: **timestamps bit-idênticos** B vs C (`max start/end diff=0.0000 s`, 1312/1312 words iguais, probabilidades iguais). Triton aqui é pura aceleração, sem mudança editorial.
- Conclusão: Triton funcional ajuda, mas ganho steady-state é pequeno para 10 min. Ganho cresce com chunk maior (DTW maior), mas não muda ordem de grandeza.

## 7. Faster-Whisper (mesmo áudio, `pt`, `word_timestamps=True`)

- D-plain `float16` (apples-to-apples): 15.06 s run2 vs B 27.56 s (**-45%**), vs C 25.67 s (**-41%**); RTF 0.025 vs 0.046/0.043; load 1.7 s vs 7-10 s; VRAM líquida ~2.4 GB vs 3.54 GB torch.
- D-batched `float16 b8`: 4.05 s run2 (**-85% vs B**, ~6.8× mais rápido), RTF 0.007, mas segmentação grosseira (16 vs 227) e -75 words. Útil para “segment-first” rápido, não como substituto editorial direto sem validar fronteiras.
- Qualidade words (primeiras 15 + janela 60-90 s, `compare_quality.py`):
  - B vs C: idênticos.
  - FW-plain vs OpenAI: timestamps dentro de **0.00-0.02 s** (ex.: `60.08→60.10`, `60.22→60.20`, `64.66→64.62`), mesmo texto, probabilidades ±0.01 (ex.: `friendslop 0.41→0.52`). Zero `neg_dur`, zero `overlaps>50 ms`, zero `bad_order`, gaps>2 s refletem silêncios reais (OpenAI 45 em 10 min; FW sample 5 em 50 segs, padrão similar).
  - Nenhum problema óbvio: sem deslocamento grande, repetição, inversão, gaps excessivos ou fronteiras ruins em trechos verificados.
- Limitação: FW-plain usou `beam_size=5` (default do runner) vs OpenAI greedy; mesmo assim mais rápido. `compute_type=float16` é seguro para Ada (sm_89). Não testei `int8_float16`/`int8` para não introduzir perda sem necessidade.

## 8. Recomendação: D — estratégia híbrida (UMA escolha)

**Escolha D. Híbrida**, pelos números reais:

1. Transcrever VOD inteiro rapidamente com **segment timestamps** (sem pagar DTW global em 8 h);
2. Proposals buscam candidate moments por transcript;
3. Quando intervalo 30-120 s vira candidato real, gerar **word timestamps precisos apenas naquele intervalo**;
4. Premiere faz sync audiovisual exato posteriormente.

Por quê, com custo medido:
- Pagar `word_timestamps=True` em todas as horas de todos os VODs custa +18% (fallback) / +10% (Triton) sobre segment-only no OpenAI para 10 min, e piora superlinearmente com `chunk_seconds=1800` por causa do DTW global. Para 7.2 h isso é ~+3 min lineares, mas na prática observada são ~41 min totais vs ~28 min que seriam sem words (estimativa), mais VRAM e JSONs maiores.
- FW-plain com words (RTF 0.025) já é mais rápido que OpenAI sem words (RTF 0.039). Ou seja, migrar backend resolve velocidade mesmo sem híbrido. Mas híbrido economiza ainda mais: ex. 20 candidatos ×60 s =1200 s de áudio → FW-plain ~30 s / OpenAI-Triton ~51 s, vs 650 s / 1118 s para VOD inteiro com words. **80-95% de economia** no estágio word-level, independente de backend.
- Híbrido preserva segurança editorial: words só onde há decisão de edição, reduz superfície de drift de fingerprint (menos artefatos word-level para aprovar), mantém `rights_lock`/`publish_lock` fail-closed, e evita “inventar sync” global.
- Mantém OpenAI onde comportamento específico dele for necessário (fallback determinístico, compatibilidade com `editorial-detailed-v1`), e usa FW onde ele vence (velocidade/VRAM).

Fases sugeridas (não implementadas nesta tarefa):
- Fase 0 (já feita, manter): `triton-windows==3.2.0.post21` no venv Whisper. Zero mudança de código, warnings zerados, -7% steady, -31% cold, output idêntico. Reversível via `pip uninstall triton-windows`.
- Fase 1: migrar transcrição editorial para **Faster-Whisper plain `float16`** (apples-to-apples, 245 segs, qualidade ±0.02 s). Requer mudança de provider/perfil, testes e re-aprovação de gates (fingerprints mudam).
- Fase 2: implementar **segment-first + on-demand word alignment 30-120 s** + readback Premiere. Esta é a arquitetura D completa.

Se forçado a escolher backend único hoje sem arquitetura nova: **C (FW plain)** vence B em velocidade (-41%), VRAM (-32%) e qualidade equivalente. Mas D continua superior a C puro porque evita pagar words em horas descartadas.

## 9. Comandos executados (registro)

```powershell
# Diagnóstico (sem alterar nada)
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe -c "import sys,torch,whisper,..."
Get-Command python/whisper/nvcc -All
nvidia-smi
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe -m pip freeze
Get-ChildItem K:\Applications\LLMS\Whisper\.venv\Lib\site-packages\torch\lib
# Fallback
Get-Content K:\Applications\LLMS\Whisper\.venv\Lib\site-packages\whisper\timing.py
Get-Content K:\Applications\LLMS\Whisper\.venv\Lib\site-packages\whisper\triton_ops.py
# Amostra (fora de assets oficiais)
New-Item -ItemType Directory -Path K:\Applications\Youtube-Channel\.studio-benchmark\whisper-word-timestamps -Force
C:\Users\Admin\AppData\Local\ffmpeg\bin\ffmpeg.exe -hide_banner -y -ss 600 -i ...\2861744268.mp4 -t 600 -vn -ac 1 -ar 16000 -c:a pcm_s16le sample_10min_16k_mono.wav
# Baseline
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe .studio-benchmark\whisper-word-timestamps\bench_openai.py --audio sample_10min_16k_mono.wav --word-timestamps False --repeats 2 --output bench_A_noWT.json
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe .studio-benchmark\whisper-word-timestamps\bench_openai.py --audio sample_10min_16k_mono.wav --word-timestamps True --repeats 2 --output bench_B_WT_fallback.json
# Triton
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe -m pip freeze > K:\Applications\LLMS\Whisper\pip-before-triton.txt
Copy-Item pip-before-triton.txt .studio-benchmark\whisper-word-timestamps\pip-before-triton.txt
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe -m pip index versions triton-windows
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe -m pip install "triton-windows==3.2.0.post21"
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe .studio-benchmark\whisper-word-timestamps\bench_openai.py --audio sample_10min_16k_mono.wav --word-timestamps True --repeats 2 --output bench_C_WT_triton.json
# Faster
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe .studio-benchmark\whisper-word-timestamps\bench_faster.py --audio sample_10min_16k_mono.wav --word-timestamps True --compute-type float16 --batch-size 8 --repeats 2 --output bench_D_FW_float16_b8.json
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe .studio-benchmark\whisper-word-timestamps\bench_faster.py --audio sample_10min_16k_mono.wav --word-timestamps True --compute-type float16 --batch-size 8 --repeats 1 --output bench_D2_FW_plain.json --batched False
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe .studio-benchmark\whisper-word-timestamps\bench_faster.py --audio sample_10min_16k_mono.wav --word-timestamps True --compute-type float16 --batch-size 8 --repeats 2 --output bench_D_plain_float16.json --batched False
K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe .studio-benchmark\whisper-word-timestamps\compare_quality.py
```

## 10. Pacotes instalados/removidos

- Instalado (único, mínimo, reversível): `triton-windows==3.2.0.post21` (wheel `cp311-win_amd64`, 39.7 MB, fornece `triton==3.2.0`). Compatível com `torch==2.6.0+cu124` (matriz PyTorch 2.6→Triton 3.2) e Python 3.11. Não atualizou torch/CUDA/FW/CTranslate2. Comando acima.
- Removidos: nenhum.
- Reversão: `K:\Applications\LLMS\Whisper\.venv\Scripts\python.exe -m pip uninstall -y triton-windows` (restaura warnings/fallback, sem tocar em modelos).
- `pip-before-triton.txt` salvo em `K:\Applications\LLMS\Whisper\pip-before-triton.txt` + cópia na pasta benchmark. `pip` não atualizado (permanece 24.0).

## 11. Scripts e resultados brutos (todos em `.studio-benchmark/whisper-word-timestamps/`)

- `sample_10min_16k_mono.wav` (19200078 bytes, 600 s)
- `bench_openai.py`, `bench_faster.py`, `compare_quality.py`
- `bench_A_noWT.json` + `.full_run0.json`
- `bench_B_WT_fallback.json` + `.full_run0.json`
- `bench_C_WT_triton.json` + `.full_run0.json`
- `bench_D_FW_float16_b8.json` + `.full_run0.json`
- `bench_D_plain_float16.json` + `.full_run0.json` (+ `bench_D2_FW_plain.json` run único)
- `pip-before-triton.txt`
- Este relatório (`REPORT.md`)

## 12. Mudanças sugeridas para o harness (NÃO implementadas)

1. Manter `triton-windows==3.2.0.post21` pinado no ambiente Whisper (documentar em `integrations/twitch.md` ou guia de setup, sem mudar `stages.json`).
2. Adicionar perfil `editorial-segments-v1` (FW batched/plain, `word_timestamps=False`, `without_timestamps` conforme resolver) para full-VOD rápido.
3. Adicionar runner on-demand `word-align-range` (FW plain `float16`, 30-120 s, `word_timestamps=True`) acionado apenas quando proposal vira candidato real; saída como proposal estruturada (`summary/document/files/questions/warnings`) via `validate_proposal()` → revisão humana → `apply_proposal()`, nunca auto-aprovação.
4. Reduzir `chunk_seconds` para word-level (ex. 600 s) ou eliminar chunk global com words; manter 1800 s apenas para segment-first.
5. Atualizar `studio/automation-policy.json`/`source-policy.json` se necessário para proibir `word_timestamps=True` em multi-horas sem aprovação, e registrar `candidate_score` como filtro de custo (não autoridade editorial).
6. Testes: happy/invalid/missing-dep/flags/paths/rights-bloqueados/subprocess/dashboard/gates para ambos backends + regressão de segurança (sem segunda produção ativa, sem runner auto-apply, sem publish automático, sem output Twitch fora da produção).
7. Docs: `README.md`, `docs/ARCHITECTURE.md`, `docs/DASHBOARD-GUIDE.md` com CLI+Dashboard coerentes para `segment-first` e `align-range`.

## 13. Limites e próximos passos

- 10 min é suficiente para ciclos rápidos, mas DTW escala superlinearmente; um run 30 min único (B vs C vs D-plain) quantificaria exatamente o blowup de `chunk_seconds=1800`.
- FW-plain usou `beam=5`; comparar `beam=1` (greedy, mais próximo do OpenAI) mediria tradeoff qualidade/velocidade.
- VRAM FW medida via `nvidia-smi` total; para comparação processo-a-processo use `torch` (OpenAI) vs `nvidia-smi líquido` (FW) como feito, documentando método.
- Nenhuma validação de scrape real Twitch, upload YouTube ou gates foi feita aqui; publicação permanece `executed:false` por design.
