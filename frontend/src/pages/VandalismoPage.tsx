import { useState, useRef } from 'react'
import {
  Upload,
  ShieldAlert,
  AlertTriangle,
  Loader2,
  X,
  Brain,
  FileVideo,
} from 'lucide-react'
import { api } from '../api/client'
import type { VandalismAnalysis } from '../types'

export default function VandalismoPage() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<VandalismAnalysis | null>(null)
  const [hfResult, setHfResult] = useState<Record<string, number> | null>(null)
  const [loading, setLoading] = useState<'analyze' | 'hf' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'heuristic' | 'hf'>('heuristic')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File) => {
    const isImage = f.type.startsWith('image/')
    const isVideo = f.type.startsWith('video/')
    if (!isImage && !isVideo) return
    setFile(f)
    setAnalysis(null)
    setHfResult(null)
    setError(null)
    if (isImage) {
      const reader = new FileReader()
      reader.onload = (e) => setPreview(e.target?.result as string)
      reader.readAsDataURL(f)
    } else {
      setPreview(null)
    }
  }

  const handleAnalyze = async () => {
    if (!file) return
    setLoading('analyze')
    setError(null)
    try {
      const r = await api.analyzeVandalism(file)
      setAnalysis(r)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Erro na análise')
    } finally {
      setLoading(null)
    }
  }

  const handleHFPredict = async () => {
    if (!file) return
    setLoading('hf')
    setError(null)
    try {
      const modelType = file.type.startsWith('video/') ? 'vandalism' : 'vandalism'
      const r = await api.hfPredict(file, modelType)
      if (r.success && r.predictions) {
        setHfResult(r.predictions)
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Erro na predição HF')
    } finally {
      setLoading(null)
    }
  }

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'CRÍTICO': return 'bg-red-600 text-white'
      case 'ALTO': return 'bg-orange-500 text-white'
      case 'MODERADO': return 'bg-yellow-500 text-white'
      default: return 'bg-green-500 text-white'
    }
  }

  const getScoreColor = (score: number) => {
    if (score >= 0.7) return 'text-red-600'
    if (score >= 0.5) return 'text-orange-500'
    if (score >= 0.3) return 'text-yellow-600'
    return 'text-green-600'
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Upload */}
      <div className="space-y-4">
        <div
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center cursor-pointer hover:border-cor-blue transition-colors bg-white"
        >
          {preview ? (
            <div className="relative">
              <img
                src={preview}
                alt="Preview"
                className="max-h-72 mx-auto rounded-lg"
              />
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setFile(null)
                  setPreview(null)
                  setAnalysis(null)
                  setHfResult(null)
                }}
                className="absolute top-2 right-2 p-1 bg-red-500 text-white rounded-full hover:bg-red-600"
              >
                <X size={16} />
              </button>
            </div>
          ) : (
            <div className="py-12">
              {file?.type.startsWith('video/') ? (
                <FileVideo size={48} className="mx-auto mb-4 text-gray-300" />
              ) : (
                <Upload size={48} className="mx-auto mb-4 text-gray-300" />
              )}
              <p className="text-gray-500">Clique para selecionar imagem ou vídeo</p>
              <p className="text-xs text-gray-400 mt-1">
                Imagens (JPG, PNG) ou Vídeos (MP4, AVI)
              </p>
              {file && (
                <p className="text-sm text-cor-blue mt-2 font-medium">{file.name}</p>
              )}
            </div>
          )}
          <input
            ref={inputRef}
            type="file"
            accept="image/*,video/*"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
        </div>

        {file && (
          <div className="flex gap-2">
            <button
              onClick={handleAnalyze}
              disabled={loading === 'analyze'}
              className="flex-1 py-3 bg-cor-blue text-white rounded-lg font-medium hover:bg-cor-blue-light transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading === 'analyze' ? (
                <Loader2 size={20} className="animate-spin" />
              ) : (
                <ShieldAlert size={20} />
              )}
              {loading === 'analyze' ? 'Analisando...' : 'Analisar Vandalismo'}
            </button>
            <button
              onClick={handleHFPredict}
              disabled={loading === 'hf'}
              className="flex-1 py-3 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading === 'hf' ? (
                <Loader2 size={20} className="animate-spin" />
              ) : (
                <Brain size={20} />
              )}
              {loading === 'hf' ? 'Processando...' : 'HF Prediction'}
            </button>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
            {error}
          </div>
        )}
      </div>

      {/* Resultados */}
      <div className="space-y-4">
        {/* Tabs */}
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
          <button
            onClick={() => setActiveTab('heuristic')}
            className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'heuristic'
                ? 'bg-white text-gray-800 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Análise Heurística
          </button>
          <button
            onClick={() => setActiveTab('hf')}
            className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'hf'
                ? 'bg-white text-gray-800 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Hugging Face (SLM)
          </button>
        </div>

        {activeTab === 'heuristic' && analysis && (
          <div className="space-y-4">
            {/* Risk Score */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-gray-800">Score de Risco</h3>
                <span className={`px-3 py-1 rounded-full text-xs font-bold ${getRiskColor(analysis.risk_level)}`}>
                  {analysis.risk_level}
                </span>
              </div>
              <div className="text-center mb-4">
                <span className={`text-4xl font-bold ${getScoreColor(analysis.risk_score)}`}>
                  {(analysis.risk_score * 100).toFixed(0)}
                </span>
                <span className="text-gray-400 text-sm ml-1">/ 100</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${
                    analysis.risk_score >= 0.7
                      ? 'bg-red-500'
                      : analysis.risk_score >= 0.5
                      ? 'bg-orange-500'
                      : analysis.risk_score >= 0.3
                      ? 'bg-yellow-500'
                      : 'bg-green-500'
                  }`}
                  style={{ width: `${analysis.risk_score * 100}%` }}
                />
              </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-white rounded-lg border border-gray-100 p-3 text-center">
                <p className="text-2xl font-bold text-gray-800">{analysis.person_count}</p>
                <p className="text-xs text-gray-500">Pessoas</p>
              </div>
              <div className="bg-white rounded-lg border border-gray-100 p-3 text-center">
                <p className="text-2xl font-bold text-gray-800">{analysis.vehicle_count}</p>
                <p className="text-xs text-gray-500">Veículos</p>
              </div>
              <div className="bg-white rounded-lg border border-gray-100 p-3 text-center">
                <p className="text-2xl font-bold text-gray-800">{analysis.total_objects}</p>
                <p className="text-xs text-gray-500">Objetos</p>
              </div>
            </div>

            {/* Risk Factors */}
            {analysis.risk_factors.length > 0 && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
                <h4 className="text-sm font-semibold text-gray-500 uppercase mb-3">
                  Fatores de Risco
                </h4>
                <div className="space-y-2">
                  {analysis.risk_factors.map((rf, i) => (
                    <div key={i} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg text-sm">
                      <span className="text-gray-700">{rf.label}</span>
                      <span className={`font-medium ${getScoreColor(rf.risk)}`}>
                        {(rf.risk * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Alerts */}
            {analysis.alerts.length > 0 && (
              <div className="space-y-2">
                {analysis.alerts.map((alert, i) => (
                  <div
                    key={i}
                    className={`flex items-center gap-3 p-3 rounded-lg text-sm font-medium ${
                      alert.level === 'ALTO'
                        ? 'bg-red-50 text-red-700 border border-red-200'
                        : 'bg-yellow-50 text-yellow-700 border border-yellow-200'
                    }`}
                  >
                    <AlertTriangle size={18} />
                    {alert.message}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'hf' && hfResult && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Brain size={18} className="text-purple-600" />
              Predição do Modelo Hugging Face
            </h3>
            <p className="text-xs text-gray-400 mb-4">
              Modelo: KzRyan/Burglary_and_Vandalism (CNN-Transformer)
            </p>
            <div className="space-y-3">
              {Object.entries(hfResult).map(([className, prob]) => (
                <div key={className}>
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="capitalize font-medium text-gray-700">
                      {className}
                    </span>
                    <span className={`font-bold ${
                      className === 'vandalism' ? 'text-red-600' :
                      className === 'burglary' ? 'text-orange-600' :
                      'text-green-600'
                    }`}>
                      {(prob * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all ${
                        className === 'vandalism' ? 'bg-red-500' :
                        className === 'burglary' ? 'bg-orange-500' :
                        'bg-green-500'
                      }`}
                      style={{ width: `${prob * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 p-3 bg-purple-50 rounded-lg text-xs text-purple-700">
              <strong>💡 SLM:</strong> Este modelo leve (CNN-Transformer) pode ser usado 
              como Small Language Model para inferência rápida, ou fine-tuned com 
              Transfer Learning para o domínio específico de patrimônios cariocas.
            </div>
          </div>
        )}

        {!analysis && !hfResult && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 flex items-center justify-center">
            <div className="text-center text-gray-400">
              <ShieldAlert size={48} className="mx-auto mb-3 opacity-50" />
              <p className="text-lg font-medium">Nenhuma análise</p>
              <p className="text-sm">Envie uma imagem ou vídeo para analisar</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
