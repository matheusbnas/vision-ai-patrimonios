"""
Simulação de dano na estátua — pra TESTAR a detecção sem mexer no
monumento. Aplica o dano escolhido sobre a imagem real da câmera, dentro
da silhueta da estátua, e devolve a imagem "danificada".

Cenários (a parte de cima/do meio é calculada pela caixa da silhueta):
  pichacao        rabiscos e letras de spray sobre o corpo
  tinta           mancha de tinta jogada na cabeça/ombro
  quebra_cabeca   cabeça arrancada (preenchida com o fundo em volta)
  quebra_braco    pedaço do braço/mão arrancado
  remocao_peca    peça pequena removida (óculos/área sensível, se calibrada)
  cobertura       estátua coberta com pano/saco
  derrubada       estátua inteira removida (tombada/levada)
"""

import cv2
import numpy as np

SCENARIOS = {
    "pichacao": "Pichação (spray)",
    "tinta": "Tinta jogada",
    "quebra_cabeca": "Cabeça quebrada",
    "quebra_braco": "Braço/mão quebrado",
    "remocao_peca": "Peça removida (óculos)",
    "cobertura": "Estátua coberta",
    "derrubada": "Estátua derrubada/levada",
}


def _bbox(mask: np.ndarray) -> tuple:
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _remove(img: np.ndarray, region: np.ndarray) -> np.ndarray:
    """Apaga a região preenchendo com o fundo em volta (inpainting)."""
    k = np.ones((7, 7), np.uint8)
    m = cv2.dilate(region.astype(np.uint8) * 255, k)
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    out = cv2.inpaint(bgr, m, 9, cv2.INPAINT_TELEA)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


def apply(img: np.ndarray, silhouette: np.ndarray, scenario: str,
          sensitive_box: tuple | None = None, seed: int = 7) -> np.ndarray:
    """img RGB (mesmo enquadramento da silhueta); silhouette bool do tamanho do img."""
    rng = np.random.default_rng(seed)
    out = img.copy()
    x1, y1, x2, y2 = _bbox(silhouette)
    w, h = x2 - x1, y2 - y1
    band = np.zeros_like(silhouette)

    if scenario == "pichacao":
        layer = out.copy()
        color = (255, 40, 180)
        for _ in range(9):  # rabiscos
            pts = np.stack([rng.integers(x1 + w * .1, x2 - w * .1, 6), rng.integers(y1 + h * .15, y1 + h * .6, 6)], 1)
            cv2.polylines(layer, [pts.astype(np.int32)], False, color, max(int(w * .025), 3), cv2.LINE_AA)
        cv2.putText(layer, "XYZ", (int(x1 + w * .15), int(y1 + h * .45)), cv2.FONT_HERSHEY_SIMPLEX,
                    w / 140, (30, 30, 30), max(int(w * .035), 4), cv2.LINE_AA)
        blur = cv2.GaussianBlur(layer, (3, 3), 0)  # borda de spray
        out[silhouette] = blur[silhouette]

    elif scenario == "tinta":
        mask = np.zeros(silhouette.shape, np.uint8)
        cx, cy = int(x1 + w * .5), int(y1 + h * .14)
        cv2.ellipse(mask, (cx, cy), (int(w * .22), int(h * .09)), 15, 0, 360, 1, -1)
        for _ in range(12):  # respingos
            cv2.circle(mask, (int(cx + rng.normal(0, w * .2)), int(cy + abs(rng.normal(0, h * .12)))),
                       int(rng.integers(3, max(int(w * .03), 4))), 1, -1)
        m = mask.astype(bool) & silhouette
        out[m] = (0.15 * out[m] + 0.85 * np.array([230, 30, 40])).astype(np.uint8)

    elif scenario == "quebra_cabeca":
        band[y1:int(y1 + h * .2), :] = True
        out = _remove(out, band & silhouette)

    elif scenario == "quebra_braco":
        band[int(y1 + h * .3):int(y1 + h * .5), int(x1 + w * .45):x2] = True
        out = _remove(out, band & silhouette)

    elif scenario == "remocao_peca":
        if sensitive_box:
            sx1, sy1, sx2, sy2 = sensitive_box
        else:  # sem área sensível calibrada: faixa dos olhos/óculos
            sx1, sy1, sx2, sy2 = int(x1 + w * .3), int(y1 + h * .07), int(x1 + w * .8), int(y1 + h * .13)
        band[sy1:sy2, sx1:sx2] = True
        out = _remove(out, band & silhouette)

    elif scenario == "cobertura":
        cloth = np.full_like(out, (70, 75, 85))
        noise = rng.normal(0, 12, out.shape[:2])[..., None]
        cloth = np.clip(cloth + noise, 0, 255).astype(np.uint8)
        band[y1:int(y1 + h * .55), :] = True
        m = cv2.dilate((band & silhouette).astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        out[m] = cloth[m]

    elif scenario == "derrubada":
        out = _remove(out, silhouette)

    else:
        raise ValueError(f"Cenário inválido: {scenario}")
    return out
