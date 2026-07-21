"""Esquemas Pydantic para validação e serialização"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ─── Autenticação ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    api_key: str
    email: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    access_token: Optional[str] = None
    expires_in: Optional[int] = None
    message: Optional[str] = None


# ─── Câmeras ─────────────────────────────────────────────────────

class Camera(BaseModel):
    id: Optional[int] = None
    codigo: Optional[str] = Field(None, alias="code")
    nome: Optional[str] = Field(None, alias="name")
    localizacao: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: Optional[str] = None
    endereco: Optional[str] = None
    bairro: Optional[str] = None
    camera_code: Optional[str] = Field(None, alias="code")
    stream_url: Optional[str] = Field(None, alias="stream_url")
    stream_type: Optional[str] = Field(None, alias="stream_type")

    class Config:
        from_attributes = True
        populate_by_name = True


class CameraListResponse(BaseModel):
    success: bool
    cameras: list[Camera] = []
    total: int = 0


# ─── Detecção YOLO ───────────────────────────────────────────────

class DetectedObject(BaseModel):
    class_id: int
    class_name: str
    patrimony_type: str
    confidence: float
    bbox: list[int]


class DetectionResult(BaseModel):
    objects: list[DetectedObject] = []
    total_objects: int = 0
    counts: dict = {}
    processing_time_ms: float = 0


class DetectionResponse(BaseModel):
    success: bool
    result: Optional[DetectionResult] = None
    error: Optional[str] = None


# ─── Vandalismo ──────────────────────────────────────────────────

class RiskFactor(BaseModel):
    object: str
    label: str
    type: str
    risk: float
    count: int


class VandalismAlert(BaseModel):
    level: str  # ALTO, MODERADO
    score: float
    message: str
    timestamp: float
    camera_id: str


class VandalismAnalysis(BaseModel):
    risk_score: float
    risk_level: str  # BAIXO, MODERADO, ALTO, CRÍTICO
    risk_factors: list[RiskFactor] = []
    alerts: list[VandalismAlert] = []
    person_count: int = 0
    vehicle_count: int = 0
    total_objects: int = 0
    has_vandal_tools: bool = False
    vandal_tools: list[dict] = []


class VandalismResponse(BaseModel):
    success: bool
    analysis: Optional[VandalismAnalysis] = None
    error: Optional[str] = None


# ─── Hugging Face ────────────────────────────────────────────────

class HFModelInfo(BaseModel):
    repo_id: str
    model_loaded: bool
    classes: list[str] = []
    pipeline_tag: Optional[str] = None


class HFInferenceRequest(BaseModel):
    image_base64: Optional[str] = None
    video_path: Optional[str] = None
    model: str = "vandalism"  # "vandalism" | "damage"


class HFInferenceResult(BaseModel):
    success: bool
    predictions: Optional[dict] = None
    model_used: str
    processing_time_ms: float = 0
    error: Optional[str] = None


# ─── Dashboard ───────────────────────────────────────────────────

class PatrimonySummary(BaseModel):
    id: int
    nome: str
    emoji: str
    bairro: str
    categoria: str
    status: str = "monitorado"  # monitorado, alerta, critico
    ultima_deteccao: Optional[datetime] = None
    nivel_risco: float = 0.0


class DashboardStats(BaseModel):
    total_patrimonios: int
    total_cameras: int
    cameras_online: int
    alertas_ativos: int
    deteccoes_hoje: int
    patrimonio_mais_visivel: Optional[str] = None
    nivel_risco_medio: float = 0.0


class DashboardResponse(BaseModel):
    success: bool
    stats: Optional[DashboardStats] = None
    patrimonios: list[PatrimonySummary] = []
    alertas_recentes: list[VandalismAlert] = []


# ─── Upload ──────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    success: bool
    filename: str
    path: str
    size_bytes: int
    content_type: str
