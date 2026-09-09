# DaVinci Resolve

O driver (`cstudio/nle.py:ResolveDriver`) gera a partir de
`.studio/internal/assembly/timeline.json`:

- `timeline.xmeml` — interchange FCP7 XML (File > Import > Timeline)
- `resolve_assemble.py` — script Console/Python
- `resolve_assemble.lua` — variante Lua
- `RUNBOOK.md` — passo a passo

Gerar: `python -m cstudio --root . nle-export <slug>`

`available()` retorna True se `fuscript`/`resolve` estiver no PATH ou
`RESOLVE_SCRIPT_API` definido — apenas informativo; a montagem é
reproduzível por importação, sem exigir API live nos testes.
