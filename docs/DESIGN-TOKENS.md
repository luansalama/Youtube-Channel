# DESIGN TOKENS — Dashboard UI Kit / Dashboard Overview (549:8646)

Fonte: `figma-file.json` (file response, 10,2 MB) lido via stdlib. `variables/local` e `variables/published` retornaram **403** (token sem escopo `file_variables:read`); **0 variáveis resolvidas por valor**. Catalogados **48 VARIABLE_ALIAS** com fallback hex do JSON (r/g/b 0-1 → hex). Tema do frame é **claro (light)** — não há variante dark no nó.

## 1. Paleta (fallback hex + onde é usada)

| Slot | Hex | Uso no Overview |
|---|---|---|
| bg | `#FFFFFF` | Page 1440×1024, cr 24 (var `…/78205:129`) |
| sidebar | transparente + stroke `#000000` @0.1 | Coluna 212×1024 (var `…/78205:110`) |
| card A / card B | `#EDEEFC` / `#E6F1FD` | 4 KPI 202×112 alternados (vars `…/79350:1` e `…/79350:0`) |
| elevated/panel | `#F9F9FA` | 5 Blocks (var `…/78205:124`) |
| border | `#000000` @0.1 | Stroke sidebar; cards/blocks sem stroke |
| text | `#1C1C1C` (var `…/19373:600`) + `#000000` (var `…/78205:106`, 115 usos) | Valores rollers, títulos, legendas escuras |
| muted | `#000000` @0.4 (45 usos, `…/78205:108`) | Labels sidebar, títulos KPI |
| faint | `#000000` @0.2 (`…/78205:109`) + @0.04 (`…/78205:111`, item ativo) | Dots, fundo item selecionado |
| accent/brand | `#4C98FD` (var `…/78206:205`) | Ícones/ações (plus, toggles); gradientes primários só como style `Gradient/Primary` |
| success | `#94E9B8` / `#71DD8C` | Série verde dos bar/donut charts |
| info blues | `#92BFFF` / `#7DBBFF` / `#AEC7ED` / `#A0BCE8` | Séries azul/periwinkle (barras, donut) |
| purple/teal | `#9F9FF8` / `#B899EB` / `#96E2D6` / `#6BE6D3` | Séries roxo/teal |
| danger / warning | — ausentes | 0 fills vermelhos/amarelos nos 892 nós |

Texto sobre cor: `%` do donut em `#FFFFFF`; `%` da legenda lateral em preto primário.

## 2. Tipografia

Família única no frame: **Inter**. Combos reais (style): 12/400/lh16 (labels, deltas, eixos, legendas), 14/400/lh20 (títulos KPI, itens sidebar, tabs), 14/600/lh20 (tab ativa "Total Users", títulos "Traffic by…", "Total Users"), 24/600/lh36 (valores KPI — dígitos em rollers). `styles` do arquivo: 17 TEXT (14/12 Regular, 24/14/16/18 Semibold, Footnote/Body, 48/64…), 10 FILL (`White/100%`, `Black/80%`, `Static Black/White`, `Gradient/Primary|Black`…), 3 EFFECT (`Background blur 40`, `Drop shadow 1`, `Material Blur`).

## 3. Raios de canto

12 (124×: botões, inputs, pills), 8 (77×: brand, toggles), 80 (49×: avatares), 20 (9×: 4 KPI + 5 Blocks), 24 (page), 16 (1×: mini-card 184×116), 4/6/3 (detalhes).

## 4. Medidas do layout (px, `absoluteBoundingBox`)

- Page: (954,0) 1440×1024. Sidebar (954,0) **212×1024**, pad 16/16/16/16, gap 8, vertical. RightSidebar (2114,0) **280×1024**, pad 16, gap 16. Header (1166,0) **948×68**, pad L/R 28 T/B 20, gap 312; filhos: Icon-Breadcrumb 235×24, bloco busca/ações 300×28. Conteúdo (1194,140) 892 larg, gaps 28.
- Sidebar: brand ByeWind 180×40 (pad 8, cr 8); tabs Favorites 77×24 / Recently 74×24 (pad 12/4/4, cr 12, gap 4); 2 IconText 180×36; seção Dashboards (label 180×28 + 3 itens 180×36, ativo #000 @0.04, pad 8, gap 4, cr 12); seção Pages (label + 10 itens 180×36); Logo footer 180×36.
- KPI: 4× 202×112 em x=1194/1424/1654/1884 y=140, pad 24, gap 8, cr 20 (Views +11.01%, Visits −0.03%, New Users +15.03%, Active Users +6.08%).
- Blocks `#F9F9FA` cr 20: (1194,280) 662×330 Total Users (tabs + legenda This/Last year + ChartMotion 614×246, Jan–Jul, 10K–30K); (1884,280) 202×330 Traffic by Website (6 linhas); (1194,638) 432×280 Traffic by Device (ChartMotion 384×196 + legenda Linux/Mac/iOS/Windows/Android/Other); (1654,638) 432×280 Traffic by Location (DonutChart 120×120 + US 52.1 / CA 22.8 / MX 13.9 / Other 11.2); (1194,946) 892×280 Revenue (ChartMotion 844×196).
- RightSidebar: 3 frames 248 larg: Notifications 260h, Activities 316h, Contacts 300h.

## 5. Componentes da tela Overview

Sidebar (ByeWind, Line, Group[tabs], IconText×2, section Dashboards, section Pages[User Profile, Overview, Projects, Campaigns, Documents, Followers, Account, Corporate, Blog, Social], Logo), Header (Icon-Breadcrumb, search, 4 icon-buttons), Button (pad 12/4 cr 12; header-actions 8/4 cr 8), Card KPI ×4, Block ×5, ChartMotion ×3, DonutChart/DonutGraph, barras 28×21/19 (séries por cor), tabela/legenda Traffic by Website/Device/Location, RightSidebar (Notifications, Activities, Contacts + avatares cr 80), badges de delta como texto 12 Regular (sem pill próprio).

## 6. Animação / prototype

**151 interações**, todas `ON_HOVER → CHANGE_TO + SMART_ANIMATE / EASE_OUT`: 0.3 s (buttons, frames, avatares) e 0.6 s (textos). Sem autoplay, sem `AFTER_TIMEOUT`, sem easing custom além de EASE_OUT.

## 7. Notas de fidelidade

- Valores de variável (nomes/modos dark) exigem token com `file_variables:read`; doc acima usa fallback do JSON — suficiente para replicar o light.
- Barras/donut usam hex literal por série (ex. `#A0BCE8`, `#6BE6D3`), não alias — replicar como constantes de série.
- Spacings também têm alias (ex. pad 16 → `…/14747:99`, gap 8 → `…/14747:106`): 16/8/4/12/20/24/28 são o sistema.

## 8. Derivação dark + aplicação no dashboard (complemento)

- Variante dark: só há o texto `Light & Dark Mode` (`I24155:28872;387056:745183`); nenhum frame/canvas com "dark" no nome. Dark derivado elevando o light (tokens em `cstudio/dashboard.py: PALETTE`): bg `#0F1117`, sidebar `#151A24`, card `#1A2030`, elevated `#232B3E`, border `#2A3348`, text `#E8EAF0`, muted `#9AA3B2`, accent `#5B8CFF` (o accent light do JSON é `#4C98FD`; success/danger/warning dark `#34D399`/`#FF6B6B`/`#FBBF24` — o Overview não tem vermelho/amarelo, mas o arquivo tem `#FF453A`/`#FF3B30` 63× cada em outros nós).
- Transição: `transition .3s ease-out` (hovers do JSON: `SMART_ANIMATE` 850× + `EASE_OUT`, durações `0.3000000119` 369× e `0.6000000238` 510× — contagem direta no JSON; o "151 interações" da seção 6 refere-se a fluxos de protótipo).
- Medidas aplicadas: sidebar 248px (JSON 212px; 248 = teto do intervalo 212–248 p/ 9 itens + lista), topbar `min-height: 68px` (JSON 68, pad L/R 28 T/B 20), stat cards `min-height: 112px` (KPI 202×112 pad 24 gap 8 cr 20), cards/blocks `radius: 20px pad: 24px`, botões/inputs/pills `radius: 12px`, raio 8px em detalhes, tabelas `th 12px uppercase` / linhas ~44px (`td` pad 12px) com hover, tipografia Inter 12/14/24 + `tabular-nums`.
- Ícones: `GET /v1/images?format=svg` funciona p/ frames — 5 SVGs salvos em `%TEMP%/figma-icons/` (sidebar 212×1024, header 948×68, card 202×112, blocks 662×330 e 432×280); componentes de ícone retornam `null` (remotos SnowUI, `remote: True`) e vetores do doc são todos sub-IDs de instância (`I…;…`), sem ID simples exportável — nav usa 9 SVGs stroke 16px desenhados à mão (`_icon()`), conforme fallback previsto.

## 9. Validacao pixel a pixel (Images API, PNG 1440x1024, 2026-09-09)

Amostras diretas do render: sidebar #FFFFFF, page bg #FFFFFF, KPI A/C #EDEEFC, KPI B/D #E6F1FD, blocks #F9F9FA - identicos aos fallbacks da secao 1. Histograma confirma series #70B0F0/#60E0D0 (charts). Base light validada; dark da secao 8 mantido.
