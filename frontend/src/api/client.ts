/**
 * Cliente HTTP para comunicação com o backend FastAPI
 */
import axios, { AxiosInstance } from 'axios'
import type {
  Camera,
  DetectionResult,
  VandalismAnalysis,
  DashboardStats,
  Patrimonio,
  HFModelInfo,
  VandalismAlert,
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

  // ─── Detecção ─────────────────────────────────────────────────

  async detectObjects(file: File, confidence?: number): Promise<DetectionResult> {
    const form = new FormData()
    form.append('file', file)
    if (confidence) form.append('confidence', String(confidence))

    const { data } = await this.http.post('/api/detect', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data.result
  }

  async detectFull(file: File, confidence?: number, cameraId = 'upload') {
    const form = new FormData()
    form.append('file', file)
    form.append('camera_id', cameraId)
    if (confidence) form.append('confidence', String(confidence))

    const { data } = await this.http.post('/api/detect/full', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  }

  async getModelsStatus() {
    const { data } = await this.http.get('/api/detect/models')
    return data.models
  }

  // ─── Vandalismo ───────────────────────────────────────────────

  async analyzeVandalism(file: File, cameraId = 'unknown'): Promise<VandalismAnalysis> {
    const form = new FormData()
    form.append('file', file)
    form.append('camera_id', cameraId)

    const { data } = await this.http.post('/api/vandalism/analyze', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data.analysis
  }

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
