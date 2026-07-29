/**
 * Cliente HTTP para comunicação com o backend FastAPI
 */
import axios, { AxiosInstance } from 'axios'
import type {
  Camera,
  DashboardStats,
  Patrimonio,
  HFModelInfo,
} from '../types'

const API_BASE = import.meta.env.VITE_API_BASE || ''

class ApiClient {
  private http: AxiosInstance

  constructor() {
    this.http = axios.create({
      baseURL: API_BASE,
      timeout: 60000,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  // ─── Saúde ────────────────────────────────────────────────────

  async health() {
    const { data } = await this.http.get('/health')
    return data
  }

  // ─── Autenticação ─────────────────────────────────────────────

  async login() {
    const { data } = await this.http.post('/api/auth/login')
    return data
  }

  async authStatus() {
    const { data } = await this.http.get('/api/auth/status')
    return data
  }

  // ─── Câmeras ──────────────────────────────────────────────────

  async getCameras(): Promise<Camera[]> {
    const { data } = await this.http.get('/api/cameras')
    return data.cameras
  }

  async getCamera(code: string) {
    const { data } = await this.http.get(`/api/cameras/${code}`)
    return data
  }

  async getCamerasByCodes(codes: string[]): Promise<Camera[]> {
    const { data } = await this.http.post('/api/cameras/by-codes', codes)
    return data.cameras
  }

  async getCameraStream(code: string) {
    const { data } = await this.http.get(`/api/cameras/${code}/stream`)
    return data
  }

  // ─── Monitoramento ao Vivo ────────────────────────────────────

  async monitorLive(code: string, confidence?: number, includeImage = true) {
    const params: any = { include_image: includeImage }
    if (confidence) params.confidence = confidence
    const { data } = await this.http.get(`/api/monitor/live/${code}`, { params })
    return data
  }

  async monitorMulti(codes: string[], confidence?: number) {
    const params: any = { codes: codes.join(',') }
    if (confidence) params.confidence = confidence
    const { data } = await this.http.get('/api/monitor/multi', {
      params,
      timeout: 45000,  // 45s máx para processar todas as câmeras
    })
    return data
  }

  async getStreams(codes: string[]) {
    const { data } = await this.http.get('/api/monitor/streams', {
      params: { codes: codes.join(',') },
      timeout: 15000,
    })
    return data
  }

  // Demonstração: gera cena sintética e executa pipeline completo
  async monitorDemo(cenario = 'depredacao', cameraCode = '001175') {
    const { data } = await this.http.get('/api/monitor/demo', {
      params: { cenario, camera_code: cameraCode },
      timeout: 30000,
    })
    return data
  }

  // ─── Detecção de Mudanças (Antes vs Depois) ───────────────────

  async detectChanges(cameraCode: string, usarDemo = true) {
    const { data } = await this.http.get(`/api/monitor/change/${cameraCode}`, {
      params: { usar_demo: usarDemo },
      timeout: 30000,
    })
    return data
  }

  async setReference(cameraCode: string, usarDemo = true) {
    const { data } = await this.http.post(`/api/monitor/change/${cameraCode}/reference`, null, {
      params: { usar_demo: usarDemo },
      timeout: 15000,
    })
    return data
  }

  // ─── Zona/Quadrante calibrável por câmera ─────────────────────

  async getZone(cameraCode: string) {
    const { data } = await this.http.get(`/api/monitor/zone/${cameraCode}`)
    return data
  }

  async setZone(cameraCode: string, zone: { x_start: number; x_end: number; y_start: number; y_end: number }) {
    const { data } = await this.http.put(`/api/monitor/zone/${cameraCode}`, zone)
    return data
  }

  async resetZone(cameraCode: string) {
    const { data } = await this.http.delete(`/api/monitor/zone/${cameraCode}`)
    return data
  }

  async getZoneFrame(cameraCode: string) {
    const { data } = await this.http.get(`/api/monitor/zone/${cameraCode}/frame`, {
      timeout: 20000,
    })
    return data
  }

  async getModelsStatus() {
    const { data } = await this.http.get('/api/detect/models')
    return data.models
  }

  // ─── Vandalismo (HF Model) ────────────────────────────────────

  async hfPredict(file: File, modelType = 'vandalism') {
    const form = new FormData()
    form.append('file', file)
    form.append('model_type', modelType)

    const { data } = await this.http.post('/api/vandalism/hf-predict', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  }

  async getHFModelsInfo() {
    const { data } = await this.http.get('/api/vandalism/hf-models')
    return data.models
  }

  // ─── Dashboard ────────────────────────────────────────────────

  async getDashboardStats() {
    const { data } = await this.http.get('/api/dashboard/stats')
    return data
  }

  async getPatrimonios(): Promise<Patrimonio[]> {
    const { data } = await this.http.get('/api/dashboard/patrimonios')
    return data.patrimonios
  }

  async getPatrimonio(id: number): Promise<Patrimonio> {
    const { data } = await this.http.get(`/api/dashboard/patrimonios/${id}`)
    return data.patrimonio
  }
}

export const api = new ApiClient()
