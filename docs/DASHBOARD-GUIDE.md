# Dashboard

```powershell
python -m cstudio --root . studio --host 127.0.0.1 --port 8765
```

Páginas: Production, Proposals, Gates, Cutlist, Sync, Graphics, Master,
Release, Diagnostics. API: `GET /health`, `GET /api/status?slug=...`,
`POST /action/{approve,advance,apply-proposal}`.
