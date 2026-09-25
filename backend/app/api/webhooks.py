"""
Receptor de webhooks do OctaVision (app.octavision.com.br → Settings → Webhooks).

O OctaVision faz um HTTP POST para a URL cadastrada quando ocorrem os eventos
selecionados (Event Opened/Closed, Positive/Negative Inference). O formulário
deles não tem campo de secret/assinatura, então a autenticação é feita por um
token na própria URL:  .../api/webhooks/octavision?token=<OCTAVISION_WEBHOOK_TOKEN>

Como o formato do payload ainda não está documentado, cada requisição é
gravada crua em data/octavision_webhooks.jsonl para inspeção.
"""

import json
import logging
import secrets
import time
from collections import deque

from fastapi import APIRouter, HTTPException, Query, Request

from app.config import DATA_DIR, OCTAVISION_WEBHOOK_TOKEN

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

_LOG_FILE = DATA_DIR / "octavision_webhooks.jsonl"
_recent: deque = deque(maxlen=200)


def _check_token(token: str | None):
    # Sem token configurado o endpoint fica aberto — aceitável só em dev local.
    if not OCTAVISION_WEBHOOK_TOKEN:
        return
    if not token or not secrets.compare_digest(token, OCTAVISION_WEBHOOK_TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido")


@router.post("/octavision")
async def receive_octavision(request: Request, token: str | None = Query(None)):
    """Recebe eventos do OctaVision. Responde 200 rápido; processamento vem depois."""
    _check_token(token)

    raw = await request.body()
    try:
        payload = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        payload = raw.decode("utf-8", errors="replace")

    entry = {
        "received_at": time.time(),
        "client": request.client.host if request.client else None,
        "headers": {k: v for k, v in request.headers.items() if k.lower() != "authorization"},
        "payload": payload,
    }
    _recent.appendleft(entry)
    with _LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info(f"📨 Webhook OctaVision recebido: {str(payload)[:300]}")
    return {"success": True}


@router.get("/octavision")
async def list_octavision(
    token: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Últimos webhooks recebidos (desde o último restart) — útil para depurar."""
    _check_token(token)
    return {"success": True, "total": len(_recent), "events": list(_recent)[:limit]}
