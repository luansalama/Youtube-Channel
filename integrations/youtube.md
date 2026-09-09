# YouTube integration (futura)

Este build não faz upload. Para wire-up real (opcional):

1. Criar projeto Google Cloud + OAuth client (tipo Desktop).
2. Apontar `YOUTUBE_CLIENT_SECRETS` ao JSON baixado.
3. Implementar `integrations/youtube_upload.py` com `google-api-python-client`
   (`pip install -e .[youtube]`) usando o package de `cstudio package`.
4. Manter o bloqueio server-side: só chamar com `publish_lock` + rights + master.

Nada aqui fabrica analytics ou clearance.
