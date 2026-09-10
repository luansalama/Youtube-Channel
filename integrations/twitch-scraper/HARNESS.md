# Cuts Studio bridge

Esta pasta contém o scraper Twitch V7.6 fornecido, vendorizado para uso pelo harness.
O código de integração fica em `cstudio/twitch.py`; não execute esta cópia esperando a saída
padrão do scraper original quando ela for iniciada pelo Studio.

O wrapper define `CSTUDIO_TWITCH_OUT` para gravar em:

```text
productions/<slug>/.studio/internal/ingest/twitch/<streamer>/
```

O dashboard e a CLI expõem `--threads 1|2|4|8`, `--sequential`, `--force` e
`--no-resume`. O safety cap do scraper continua em 8 workers.

Dependências são locais a esta pasta e não entram no patch/repositório. No primeiro run,
se `node_modules/playwright` não existir, o wrapper executa `bun install --frozen-lockfile`
e `bun x playwright install chromium` antes da captura.
