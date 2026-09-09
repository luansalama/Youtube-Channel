# SnowUI DARK — tokens reais (Copy as CSS do Figma, 2026-09-09)

## Base
- page bg: `#333333`, radius 24
- font: Inter (ss01, cv01); 12/400/lh16 · 14/400/lh20 · 14/600/lh20 · 24/600/lh32

## Texto
- primary: `#FFFFFF`
- secondary: `rgba(255,255,255,0.4)`
- faint: `rgba(255,255,255,0.2)` / `rgba(255,255,255,0.15)`

## Superfícies
- block: `rgba(255,255,255,0.04)`, radius 20, padding 24, gap 16
- card pastel A: `#EDEEFC` / card pastel B: `#E6F1FD`, radius 20, padding 24,
  gap 8, 202×112, texto `#000000` (mesmo no dark!)
- item ativo (nav): `rgba(255,255,255,0.1)`, radius 12
- avatar: `rgba(255,255,255,0.1)`, radius 80 (circular)
- icon chip: `#EDEEFC`/`#E6F1FD`, 24×24, radius 8, glifo `#000000` 16px
- search: `rgba(255,255,255,0.1)` + blur 10, radius 16, 160×28
- tooltip: `rgba(0,0,0,0.8)` + overlay branco 0.1, blur 10, radius 12
- logo footer: blur 20, radius 8; brand `#4C98FD`
- kbd: borda 0.5px `rgba(255,255,255,0.15)`, radius 6

## Bordas / divisórias
- `0.5px solid rgba(255,255,255,0.15)` (sidebar direita, header bottom, strip)

## Layout
- sidebar 212px, padding 16, gap 8; itens 180×36, padding 8, gap 4/8, radius 12
- header 68px (left 212, right 280), padding 20/28, gap 312
- right sidebar 280px, padding 16, gap 16
- conteúdo: left 240, top 140, gap 28, largura 892
- botões pill: padding 4/12, radius 12; botões ação: padding 4/8, radius 8

## Séries (charts)
- `#A0BCE8` · `#6BE6D3` · `#ADADFB` · `#7DBBFF` · `#B899EB` · `#71DD8C`
- barras 28px, radius 8; linha tracejada `#A0BCE8`; donut 120px
- tag: radius 8, padding 2/8/2/4, dot 12px branco

## Tela 2 — eCommerce/Overview longa (Copy as CSS, 2026-09-09)

- Sidebar 220px, itens 188x48 padding 12 gap 12 radius 16, icones 24px; ativo branco 10%.
- Cards gradiente 285x100 radius 24 padding 16/20: Gradient/Primary = linear-gradient(180deg, branco 5%->40%), #0A84FF; Gradient/Black idem sobre #FFFFFF (blend). Titulo 16/400 branco + chip pill branco 20% radius 80; valor 24/600 branco.
- Titulo de bloco 18/600 NA COR do bloco: #BF5AF2 (roxo), #0A84FF (azul), #30D158 (verde), #FF453A (vermelho), #63E6E2 (teal).
- Chips 28px radius 80 padding 4/12: fundo cor@10% + borda 0.5px cor@20% + label 14/400 cor 100%. Cores: #BF5AF2, #30D158, #0A84FF, #FF9F0A, branco 40%.
- Tabela: header 12/400 muted padding 12/16 min-h 40; linhas 52px padding 12/16; zebra rgba(255,255,255,0.04); radius 16 unilateral; avatar 24px + texto 14/400.
- Blocks radius 24 + drop-shadow 0.5px preto 10%; tooltip clara rgba(255,255,255,0.8) texto #000 radius 80; footer 56px padding 20/28 texto 12 muted.
- Accent iOS: #0A84FF (logo usa #0A84FF; tela 1 usava #4C98FD).
