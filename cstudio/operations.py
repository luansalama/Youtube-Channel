"""Stage-aware dashboard operations.

This module is intentionally small: the browser never gets arbitrary shell access.
It translates the current harness stage into a concise set of semantic actions that
can be rendered by the dashboard and validated again by the backend.
"""
from __future__ import annotations

from . import core as C


STAGE_UX = {
    "config": {
        "headline": "Defina o trabalho antes de começar",
        "description": "Feche objetivo, fontes e restrições mínimas para o harness saber o que deve produzir.",
        "agent": True,
        "prompt": "Prepare a configuração desta produção com objetivo editorial, fontes e restrições necessárias. Seja específico e não invente fatos que não estejam no contexto.",
        "primary": ("agent.propose", "Preparar configuração"),
    },
    "ingest": {
        "headline": "Prepare as fontes da edição",
        "description": "Capture os VODs, associe os melhores mirrors e baixe apenas os masters que realmente entrarão na produção.",
        "agent": False,
        "primary": ("sources.open", "Abrir fontes"),
    },
    "analysis": {
        "headline": "Entenda o material",
        "description": "Peça ao agente para identificar momentos relevantes a partir das evidências já disponíveis.",
        "agent": True,
        "prompt": "Analise o material disponível e produza os momentos mais relevantes para esta produção, com rationale objetivo e sem inventar trechos não observados.",
        "primary": ("agent.propose", "Analisar material"),
    },
    "sync": {
        "headline": "Alinhe as fontes",
        "description": "Consolide offsets e confiança de sincronização antes de usar masters de múltiplas origens.",
        "agent": True,
        "prompt": "Prepare o relatório de sincronização usando apenas as evidências existentes. Explique método, offset e confiança; sinalize qualquer incerteza.",
        "primary": ("agent.propose", "Preparar sincronização"),
    },
    "highlights": {
        "headline": "Escolha o que merece virar vídeo",
        "description": "Transforme a análise em uma priorização editorial curta e justificável.",
        "agent": True,
        "prompt": "Ranqueie os melhores momentos para o objetivo desta produção. Priorize clareza, payoff e continuidade; mantenha rastreabilidade para os momentos analisados.",
        "primary": ("agent.propose", "Ranquear melhores momentos"),
    },
    "cutlist": {
        "headline": "Monte o corte antes do Premiere",
        "description": "Gere uma cutlist revisável. O lock continua sendo uma decisão humana antes de qualquer mutação editorial ao vivo.",
        "agent": True,
        "prompt": "Monte uma cutlist coesa a partir dos highlights/candidate moments aprováveis. Use candidate-word-timestamps.json quando existir para decisões finas de entrada/saída, mas trate esses pontos como editoriais, não frame-perfect. Preserve source/timecodes e direitos; o sync e ajuste final continuam pelo waveform/readback no Premiere.",
        "primary": ("agent.propose", "Gerar cutlist"),
    },
    "assembly": {
        "headline": "Leve o corte para o Premiere",
        "description": "Prepare o handoff determinístico e verifique a integração antes de montar a timeline.",
        "agent": False,
        "primary": ("premiere.open", "Abrir Premiere"),
    },
    "graphics": {
        "headline": "Planeje só os gráficos necessários",
        "description": "Defina overlays e motion graphics que realmente ajudam a leitura do vídeo antes do graphics_lock.",
        "agent": True,
        "prompt": "Proponha apenas os overlays e gráficos necessários para este corte. Dê timecodes, tipo e texto; evite decoração sem função editorial.",
        "primary": ("agent.propose", "Planejar gráficos"),
    },
    "composition": {
        "headline": "Feche e verifique o master",
        "description": "Confirme timeline, exporte o master no Premiere e registre a evidência no harness.",
        "agent": False,
        "primary": ("premiere.open", "Abrir Premiere"),
    },
    "metadata": {
        "headline": "Prepare o pacote de publicação",
        "description": "Gere título, descrição e metadados com base no conteúdo real e nas restrições de direitos.",
        "agent": True,
        "prompt": "Prepare título, descrição, tags e notas editoriais de metadata com base apenas no vídeo produzido. Não invente claims, patrocinadores ou direitos.",
        "primary": ("agent.propose", "Gerar metadata"),
    },
    "publish": {
        "headline": "Revise antes de publicar",
        "description": "Faça package/dry-run e mantenha publicação fail-closed até uma autorização humana explícita.",
        "agent": True,
        "prompt": "Prepare o documento de publicação e checklist final. Não publique, não envie nada e destaque qualquer bloqueio restante.",
        "primary": ("reviews.open", "Revisar release"),
    },
    "learn": {
        "headline": "Registre o que vale repetir",
        "description": "Converta problemas e acertos desta produção em aprendizados concretos para o próximo ciclo.",
        "agent": True,
        "prompt": "Registre aprendizados concretos desta produção: o que funcionou, o que falhou e qual ajuste operacional deve ser repetido na próxima.",
        "primary": ("agent.propose", "Registrar aprendizados"),
    },
}

MACROS = [
    ("Preparar", ("config", "ingest")),
    ("Entender", ("analysis", "sync", "highlights")),
    ("Editar", ("cutlist", "assembly")),
    ("Refinar", ("graphics", "composition")),
    ("Finalizar", ("metadata", "publish")),
    ("Aprender", ("learn",)),
]


def experience(root: str, slug: str, status: dict | None = None) -> dict:
    st = status or C.workflow_status(root, slug)
    stage = str(st.get("stage") or "config")
    ux = dict(STAGE_UX.get(stage) or STAGE_UX["config"])
    ux.update({"stage": stage, "stage_label": stage})
    for label, ids in MACROS:
        if stage in ids:
            ux["macro"] = label
            break
    return ux


def macro_progress(current_stage: str) -> list[dict]:
    flat = [sid for _, ids in MACROS for sid in ids]
    try:
        current_index = flat.index(current_stage)
    except ValueError:
        current_index = 0
    rows = []
    cursor = 0
    for label, ids in MACROS:
        end = cursor + len(ids) - 1
        if end < current_index:
            state = "done"
        elif cursor <= current_index <= end:
            state = "current"
        else:
            state = "upcoming"
        rows.append({"label": label, "stages": list(ids), "state": state})
        cursor = end + 1
    return rows


def action_href(operation_id: str, slug: str) -> str:
    from urllib.parse import quote
    s = quote(slug, safe="")
    mapping = {
        "sources.open": f"/?page=sources&slug={s}",
        "reviews.open": f"/?page=reviews&slug={s}",
        "premiere.open": f"/?page=premiere&slug={s}",
    }
    return mapping.get(operation_id, f"/?page=production&slug={s}")
