# Publicação (publish)

1. Dry-run (sempre seguro): `python -m cstudio --root . publish <slug>`
2. Real: `python -m cstudio --root . publish <slug> --execute`

O upload real permanece **bloqueado** até:

- `publish_lock` aprovado (com fingerprints íntegros),
- rights gate passando (nenhum `sem_autorizacao_confirmada`),
- master válido registrado (`cstudio master ...`),
- package válido (`cstudio package ...`).

Mesmo com tudo aprovado, sem `YOUTUBE_CLIENT_SECRETS` configurado o comando
retorna `{"executed": false, ...}` com o caminho do package — nunca finge upload.
Com credenciais, este build orienta usar o package + YouTube Studio
(a API wire-up documentada em `integrations/youtube.md`).
