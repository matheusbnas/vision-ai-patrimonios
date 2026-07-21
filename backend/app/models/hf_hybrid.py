"""
Arquitetura CNN-Transformer Híbrida para detecção de vandalismo.
Baseada no modelo KzRyan/Burglary_and_Vandalism.

Usa ResNet18 como backbone CNN + Transformer encoder para
classificação de sequências de frames (vídeo).
"""

import math
import warnings

import torch
import torch.nn as nn
import torch.utils.checkpoint as cp
import torchvision.models as tvm

warnings.filterwarnings("ignore", message="enable_nested_tensor")


class SpatialCNN(nn.Module):
    """Backbone CNN espacial para extração de features por frame"""

    BACKBONES = {
        "resnet18": (tvm.resnet18, tvm.ResNet18_Weights.DEFAULT, 512),
        "resnet34": (tvm.resnet34, tvm.ResNet34_Weights.DEFAULT, 512),
        "resnet50": (tvm.resnet50, tvm.ResNet50_Weights.DEFAULT, 2048),
        "efficientnet_b0": (tvm.efficientnet_b0, tvm.EfficientNet_B0_Weights.DEFAULT, 1280),
    }

    def __init__(self, backbone="resnet18", pretrained=True, in_channels=3):
        super().__init__()
        factory, weights, self.out_dim = self.BACKBONES[backbone]
        model = factory(weights=weights if pretrained else None)

        if in_channels != 3:
            old = model.conv1
            model.conv1 = nn.Conv2d(
                in_channels, old.out_channels,
                old.kernel_size, old.stride,
                old.padding, bias=False,
            )
            with torch.no_grad():
                model.conv1.weight[:, :3] = old.weight

        self.layer0 = nn.Sequential(
            model.conv1, model.bn1, model.relu, model.maxpool
        )
        self.layer1 = model.layer1
        self.layer2 = model.layer2
        self.layer3 = model.layer3
        self.layer4 = model.layer4
        self.pool = nn.AdaptiveAvgPool2d(1)

    def _fwd(self, x):
        return self.layer4(
            self.layer3(
                self.layer2(
                    self.layer1(
                        self.layer0(x)
                    )
                )
            )
        )

    def forward(self, x):
        x = self._fwd(x)
        return self.pool(x).flatten(1)


class TemporalPE(nn.Module):
    """Positional Encoding temporal para o Transformer"""

    def __init__(self, d_model, max_len=64, dropout=0.1):
        super().__init__()
        self.drop = nn.Dropout(dropout)
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len).float().unsqueeze(1)
        div = torch.exp(
            torch.arange(0, d_model, 2).float()
            * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe)

    def forward(self, x):
        return self.drop(x + self.pe[:x.size(1)].unsqueeze(0))


class TransformerBlock(nn.Module):
    """Transformer Encoder para modelagem temporal"""

    def __init__(self, d_model=128, num_heads=4, num_layers=2,
                 dim_ff=256, dropout=0.1):
        super().__init__()
        self.cls = nn.Parameter(torch.zeros(1, 1, d_model))
        nn.init.trunc_normal_(self.cls, std=0.02)
        layer = nn.TransformerEncoderLayer(
            d_model, num_heads, dim_ff, dropout,
            batch_first=True, norm_first=False,
        )
        self.enc = nn.TransformerEncoder(
            layer, num_layers,
            norm=nn.LayerNorm(d_model),
        )

    def forward(self, x):
        B = x.size(0)
        x = torch.cat([self.cls.expand(B, -1, -1), x], dim=1)
        return self.enc(x)[:, 0]


class HybridCNNTransformer(nn.Module):
    """
    Modelo Híbrido CNN + Transformer para classificação de vídeo.

    Arquitetura:
        - SpatialCNN (ResNet18) para features espaciais por frame
        - Projeção para d_model
        - Positional Encoding temporal
        - Transformer Encoder para modelagem temporal
        - MLP Head para classificação final
    """

    def __init__(self, num_classes=3, backbone="resnet18", pretrained=False,
                 d_model=128, num_heads=4, num_layers=2, dim_ff=256,
                 dropout=0.1, in_channels=3):
        super().__init__()

        self.cnn = SpatialCNN(backbone, pretrained, in_channels)
        self.proj = nn.Sequential(
            nn.Linear(self.cnn.out_dim, d_model),
            nn.LayerNorm(d_model),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.pe = TemporalPE(d_model, dropout=dropout)
        self.tfm = TransformerBlock(d_model, num_heads, num_layers, dim_ff, dropout)
        self.head = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 2, num_classes),
        )

        for m in [self.proj, self.head]:
            for layer in m:
                if isinstance(layer, nn.Linear):
                    nn.init.trunc_normal_(layer.weight, std=0.02)
                    if layer.bias is not None:
                        nn.init.zeros_(layer.bias)

    def forward(self, x):
        """
        Args:
            x: Tensor de shape (B, C, T, H, W)
                B: batch, C: canais, T: frames temporal, H: altura, W: largura

        Returns:
            Tensor: (B, num_classes) logits
        """
        B, C, T, H, W = x.shape
        # Rearranja para (B*T, C, H, W)
        x = x.permute(0, 2, 1, 3, 4).reshape(B * T, C, H, W)
        # Extrai features por frame
        feat = self.cnn(x).reshape(B, T, -1)
        # Projeta e adiciona pos encoding
        feat = self.pe(self.proj(feat))
        # Transformer + head de classificação
        return self.head(self.tfm(feat))


def build_model(cfg: dict) -> HybridCNNTransformer:
    """
    Constrói o modelo a partir de um dicionário de configuração.

    Args:
        cfg: Dicionário com chaves:
            - num_classes: int (default: 3)
            - backbone: str (default: "resnet18")
            - pretrained: bool (default: False)
            - d_model: int (default: 128)
            - num_heads: int (default: 4)
            - num_layers: int (default: 2)
            - dim_ff: int (default: 256)
            - dropout: float (default: 0.1)
            - in_channels: int (default: 3)

    Returns:
        HybridCNNTransformer: Modelo instanciado
    """
    return HybridCNNTransformer(
        num_classes=cfg.get("num_classes", 3),
        backbone=cfg.get("backbone", "resnet18"),
        pretrained=cfg.get("pretrained", False),
        d_model=cfg.get("d_model", 128),
        num_heads=cfg.get("num_heads", 4),
        num_layers=cfg.get("num_layers", 2),
        dim_ff=cfg.get("dim_ff", 256),
        dropout=cfg.get("dropout", 0.1),
        in_channels=cfg.get("in_channels", 3),
    )
