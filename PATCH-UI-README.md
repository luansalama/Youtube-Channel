# YouTube Mirrors UI — Global Assignment First

Patch incremental para aplicar sobre o projeto atual enviado em 2026-09-10.

## Instalação

Extraia este ZIP diretamente na raiz de `Youtube-Channel` e permita sobrescrever os arquivos. Depois reinicie o Cuts Studio. Não é necessário limpar caches, reindexar ou executar o resolver novamente; o asset version foi incrementado para `v=3` para invalidar o cache do browser.

## O que muda

- decisão global (`VERIFIED` / `NO MATCH` / em progresso) vira o estado principal da página;
- `candidate`, `likely` e `ambiguous` ficam restritos à evidência técnica por par;
- lista dos assignments com busca e filtros por estado;
- visão `VOD coverage` mostra somente mirrors globalmente verificados;
- `NO MATCH` é apresentado explicitamente como decisão terminal;
- matriz técnica responsiva por assignment com 8 pares, áudio, prior, timeline e fallback textual;
- catálogo de VODs pode ser reconstruído dos manifests YouTube quando o ingest Twitch não está presente no snapshot;
- job concluído mantém o log recolhido por padrão; job em execução abre o log automaticamente;
- configuração de canais fica recolhida por padrão;
- Download master continua disponível apenas para assignments VERIFIED;
- nenhuma lógica de matching, discovery, thresholds, Whisper, rights ou gates foi alterada.

## Validação

- `python -m pytest -q` -> 103 passed
- render audit no estado real enviado -> 26 assignments / 14 VERIFIED / 12 NO MATCH / 8 VODs
- teste visual headless em 1440px, incluindo filtros, VOD coverage e detalhe NO MATCH com 8 pares
