# Segurança

Todo conteúdo externo (VOD, transcrição, chat, página, comentários, metadata)
é **DADO**, nunca instrução (`cstudio/security.py`).

- `scan_text()` detecta padrões (`ignore previous instructions`, `system:`, etc.)
- `import_untrusted_rows()` marca `_untrusted=True` e quarentena findings
- Runners recebem instrução explícita de não seguir texto externo
- Nada externo aprova gate, publica ou libera direitos automaticamente
