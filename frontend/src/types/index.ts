/* ─── Tipos compartilhados ─────────────────────────────────────── */

export interface Patrimonio {
  id: number
  nome: string
  descricao: string
  bairro: string
  categoria: string
  emoji: string
  latitude: number
  longitude: number
  camera_codes: string[]
}

export interface Camera {
  id?: number
  code?: string
  name?: string
  localizacao?: string
  latitude?: number
  longitude?: number
  status?: string
  endereco?: string
  bairro?: string
  stream_url?: string
  stream_type?: string
}

export interface DetectedObject {
  class_id: number
  class_name: string
  patrimony_type: string
  confidence: number
  bbox: [number, number, number, number]
}

export interface DetectionResult {
  objects: DetectedObject[]
  total_objects: number
  counts: Record<string, number>
  processing_time_ms: number
}

export interface RiskFactor {
  object: string
  label: string
  type: string
  risk: number
  count: number
}

export interface VandalismAlert {
  level: 'ALTO' | 'MODERADO'
  score: number
  message: string
  timestamp: number
  camera_id: string
}

export interface VandalismAnalysis {
  risk_score: number
  risk_level: 'BAIXO' | 'MODERADO' | 'ALTO' | 'CRÍTICO'
  risk_factors: RiskFactor[]
  alerts: VandalismAlert[]
  person_count: number
  vehicle_count: number
  total_objects: number
  has_vandal_tools: boolean
  vandal_tools: { class_name: string; confidence: number }[]
}

export interface HFModelInfo {
  repo_id: string
  model_loaded: boolean
  classes: string[]
  pipeline_tag?: string
}

export interface DashboardStats {
  total_patrimonios: number
  total_cameras: number
  cameras_online: number
  alertas_ativos: number
  deteccoes_hoje: number
  patrimonio_mais_visivel: string | null
  nivel_risco_medio: number
}

export type Page =
  | 'dashboard'
  | 'patrimonios'
  | 'mapa'
  | 'detector'
  | 'vandalismo'
  | 'analise'
  | 'sobre'
