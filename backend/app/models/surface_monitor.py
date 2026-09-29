"""
Mudança na SUPERFÍCIE protegida, frame a frame (análise contínua).

Diferente do change_detector (SSIM de um print contra uma referência
salva à mão), aqui a referência é um fundo que se atualiza sozinho com
o vídeo ao vivo:

  - a superfície é o contorno calibrado da estátua (zone_service.get_statue);
  - pixels cobertos por pessoas/veículos (caixas do YOLO) não entram na
    comparação nem na atualização do fundo — quem está na frente da
    estátua não é "mudança";
  - o fundo absorve devagar o que muda devagar (sol, nuvem, fim de tarde);
  - um pixel só conta como alterado depois de ficar diferente por
    PERSIST_FRAMES análises seguidas (sombra de quem passa some antes);
  - pixel alterado de forma persistente NÃO é absorvido pelo fundo até o
    alerta ser registrado — tinta nova continua aparecendo como mudança.

Trabalha em Lab (distância de cor), com o L pesando menos: pichação muda
cor; sombra e variação de luz mudam principalmente o brilho.
"""

from typing import Optional

import cv2
import numpy as np

# Largura do recorte da superfície usada na comparação (px)
WORK_WIDTH = 160
# Distância de cor (Lab ponderado) acima da qual o pixel está diferente
DIFF_THRESHOLD = 22.0
# Peso do canal L (brilho) na distância — menor = menos sensível a sombra/luz
L_WEIGHT = 0.5
# Análises seguidas com o pixel diferente pra ele contar como alterado
PERSIST_FRAMES = 3
# Velocidade com que o fundo absorve mudanças lentas (por análise)
BG_ALPHA = 0.03
# Abaixo desta fração visível (resto coberto por gente) não compara
MIN_VISIBLE_FRAC = 0.3
# Margem (px no frame) em volta das caixas de pessoas: cabelo/braço fora da caixa
OCCLUDER_MARGIN = 6
# Halo em volta de quem está na frente, em fração da altura da caixa: a
# mudança dentro dele pode ser sombra, mochila, perna fora da caixa ou o
# próprio corpo mal recortado — não confirma alerta. Para baixo é maior
# (sombra no banco/pedestal). Tinta de verdade continua lá quando a pessoa
# se afasta, e aí conta.
HALO_SIDE = 0.25
HALO_TOP = 0.1
HALO_BOTTOM = 0.35


class SurfaceMonitor:
    def __init__(self):
        self.bg: Optional[np.ndarray] = None          # fundo Lab float32
        self.seen: Optional[np.ndarray] = None        # pixel já observado sem oclusão
        self.count: Optional[np.ndarray] = None       # análises seguidas diferente
        self.box: Optional[tuple] = None              # contorno usado (reinicia se mudar)
        self._absorb_next = False
        self.last: dict = {"change_frac": 0.0, "clear_change_frac": 0.0, "visible_frac": 0.0,
                           "mask": None, "bbox": None}

    def reset(self):
        self.bg = self.seen = self.count = None

    def absorb(self):
        """Incorpora o estado atual ao fundo (após o alerta ser registrado)."""
        if self.count is not None:
            self.count[:] = 0
            self._absorb_next = True

    def update(self, frame: np.ndarray, surface_px: tuple, occluders: list[list[int]]) -> dict:
        """
        frame: RGB; surface_px: (x1, y1, x2, y2) em px; occluders: bboxes a ignorar.
        Devolve {"change_frac", "clear_change_frac" (só a mudança fora do halo
        de quem está na frente — é a que confirma alerta), "visible_frac",
        "mask" (bool no tamanho da superfície em px do frame, ou None),
        "bbox" (da mudança, px do frame)}.
        """
        x1, y1, x2, y2 = surface_px
        if x2 - x1 < 8 or y2 - y1 < 8:
            return self.last
        if surface_px != self.box:
            self.reset()
            self.box = surface_px

        crop = frame[y1:y2, x1:x2]
        scale = WORK_WIDTH / crop.shape[1]
        size = (WORK_WIDTH, max(int(crop.shape[0] * scale), 8))
        small = cv2.GaussianBlur(cv2.resize(crop, size, interpolation=cv2.INTER_AREA), (5, 5), 0)
        lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32)

        # Área visível = superfície menos as caixas de quem está na frente;
        # halo = entorno dessas caixas (sombra/objeto carregado)
        visible = np.ones(lab.shape[:2], bool)
        halo = np.zeros(lab.shape[:2], bool)
        for bx1, by1, bx2, by2 in occluders:
            ox1 = int((bx1 - OCCLUDER_MARGIN - x1) * scale)
            oy1 = int((by1 - OCCLUDER_MARGIN - y1) * scale)
            ox2 = int((bx2 + OCCLUDER_MARGIN - x1) * scale)
            oy2 = int((by2 + OCCLUDER_MARGIN - y1) * scale)
            visible[max(oy1, 0):max(oy2, 0), max(ox1, 0):max(ox2, 0)] = False
            bh = by2 - by1
            hx1 = int((bx1 - HALO_SIDE * bh - x1) * scale)
            hx2 = int((bx2 + HALO_SIDE * bh - x1) * scale)
            hy1 = int((by1 - HALO_TOP * bh - y1) * scale)
            hy2 = int((by2 + HALO_BOTTOM * bh - y1) * scale)
            halo[max(hy1, 0):max(hy2, 0), max(hx1, 0):max(hx2, 0)] = True
        visible_frac = float(visible.mean())

        if self.bg is None:
            self.bg = lab.copy()
            self.seen = visible.copy()
            self.count = np.zeros(lab.shape[:2], np.uint8)
            self.last = {"change_frac": 0.0, "clear_change_frac": 0.0, "visible_frac": visible_frac,
                         "mask": None, "bbox": None}
            return self.last

        if self._absorb_next:
            self.bg[visible] = lab[visible]
            self._absorb_next = False

        # Pixel ainda nunca visto sem oclusão: vira fundo na primeira vez que aparecer
        new = visible & ~self.seen
        self.bg[new] = lab[new]
        self.seen |= visible
        valid = visible & self.seen

        if visible_frac < MIN_VISIBLE_FRAC or not valid.any():
            # Estátua quase toda encoberta: mantém o estado, sem conclusão nova
            self.last = {**self.last, "visible_frac": visible_frac}
            return self.last

        diff = lab - self.bg
        # Compensa variação global de luz (nuvem/sol) pelo deslocamento mediano do L
        diff[..., 0] -= float(np.median(diff[..., 0][valid]))
        dist = np.sqrt((L_WEIGHT * diff[..., 0]) ** 2 + diff[..., 1] ** 2 + diff[..., 2] ** 2)
        differs = (dist > DIFF_THRESHOLD) & valid

        # Contador por pixel: sobe enquanto difere; oculto mantém; volta a igual zera
        self.count[differs] = np.minimum(self.count[differs] + 1, 255)
        self.count[valid & ~differs] = 0
        changed = self.count >= PERSIST_FRAMES
        # Limpa ruído de pixel solto
        changed = cv2.morphologyEx(changed.astype(np.uint8), cv2.MORPH_OPEN,
                                   np.ones((3, 3), np.uint8)).astype(bool)

        # Fundo absorve devagar só onde está visível e sem mudança persistente
        upd = valid & (self.count == 0)
        self.bg[upd] += BG_ALPHA * (lab[upd] - self.bg[upd])

        change_frac = float(changed[valid].mean()) if valid.any() else 0.0
        clear_change_frac = float((changed & ~halo)[valid].mean()) if valid.any() else 0.0
        mask = bbox = None
        if changed.any():
            mask = cv2.resize(changed.astype(np.uint8), (x2 - x1, y2 - y1),
                              interpolation=cv2.INTER_NEAREST).astype(bool)
            ys, xs = np.nonzero(mask)
            bbox = [int(x1 + xs.min()), int(y1 + ys.min()), int(x1 + xs.max()), int(y1 + ys.max())]
        self.last = {"change_frac": round(change_frac, 4), "clear_change_frac": round(clear_change_frac, 4),
                     "visible_frac": round(visible_frac, 3), "mask": mask, "bbox": bbox}
        return self.last
