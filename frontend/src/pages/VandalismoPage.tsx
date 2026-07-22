import { useState, useRef } from 'react'
import {
  Upload,
  Loader2,
  X,
  Brain,
  FileVideo,
} from 'lucide-react'
import { api } from '../api/client'

export default function VandalismoPage() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [hfResult, setHfResult] = useState<Record<string, number> | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File) => {
    const isImage = f.type.startsWith('image/')
    const isVideo = f.type.startsWith('video/')
    if (!isImage && !isVideo) return
    setFile(f)
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

  const handleHFPredict = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const modelType = 'vandalism'
      const r = await api.hfPredict(file, modelType)
      if (r.success && r.predictions) {
        setHfResult(r.predictions)
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Erro na predição HF')
    } finally {
      setLoading(false)
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
          <button
            onClick={handleHFPredict}
            disabled={loading}
            className="w-full py-3 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <Loader2 size={20} className="animate-spin" />
            ) : (
              <Brain size={20} />
            )}
            {loading ? 'Processando...' : 'Detectar Roubo/Vandalismo'}
          </button>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
            {error}
          </div>
        )}
      </div>

      {/* Resultados */}
      <div className="space-y-4">

        {hfResult && (
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

        {!hfResult && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 flex items-center justify-center">
            <div className="text-center text-gray-400">
              <Brain size={48} className="mx-auto mb-3 opacity-50" />
              <p className="text-lg font-medium">Nenhuma análise</p>
              <p className="text-sm">Envie uma imagem ou vídeo para detectar roubo/vandalismo</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
