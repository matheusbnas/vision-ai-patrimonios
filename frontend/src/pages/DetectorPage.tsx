import { useState, useRef } from 'react'
import { Upload, Image as ImageIcon, X, Search, Loader2 } from 'lucide-react'
import { api } from '../api/client'
import type { DetectionResult, DetectedObject } from '../types'

export default function DetectorPage() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [result, setResult] = useState<DetectionResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File) => {
    if (!f.type.startsWith('image/')) return
    setFile(f)
    setResult(null)
    setError(null)
    const reader = new FileReader()
    reader.onload = (e) => setPreview(e.target?.result as string)
    reader.readAsDataURL(f)
  }

  const handleDetect = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const r = await api.detectObjects(file)
      setResult(r)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Erro ao processar imagem')
    } finally {
      setLoading(false)
    }
  }

  const getColorByConfidence = (conf: number) => {
    if (conf >= 0.7) return 'text-green-600'
    if (conf >= 0.5) return 'text-yellow-600'
    return 'text-red-600'
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Upload / Preview */}
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
                className="max-h-96 mx-auto rounded-lg"
              />
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setFile(null)
                  setPreview(null)
                  setResult(null)
                }}
                className="absolute top-2 right-2 p-1 bg-red-500 text-white rounded-full hover:bg-red-600"
              >
                <X size={16} />
              </button>
            </div>
          ) : (
            <div className="py-12">
              <Upload size={48} className="mx-auto mb-4 text-gray-300" />
              <p className="text-gray-500">
                Clique para selecionar uma imagem
              </p>
              <p className="text-xs text-gray-400 mt-1">
                JPG, PNG ou WEBP
              </p>
            </div>
          )}
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
        </div>

        {file && (
          <button
            onClick={handleDetect}
            disabled={loading}
            className="w-full py-3 bg-cor-blue text-white rounded-lg font-medium hover:bg-cor-blue-light transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <Loader2 size={20} className="animate-spin" />
            ) : (
              <Search size={20} />
            )}
            {loading ? 'Processando...' : 'Detectar Objetos'}
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
        {result ? (
          <>
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
              <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <Search size={18} className="text-cor-blue" />
                Resultados da Detecção
              </h3>
              <div className="flex items-center gap-4 mb-4">
                <div className="bg-blue-50 text-cor-blue px-3 py-1 rounded-full text-sm font-medium">
                  {result.total_objects} objeto(s)
                </div>
                <div className="bg-gray-50 text-gray-600 px-3 py-1 rounded-full text-sm">
                  {result.processing_time_ms}ms
                </div>
              </div>

              {/* Counts */}
              <div className="space-y-1 mb-4">
                {Object.entries(result.counts).map(([name, count]) => (
                  <div key={name} className="flex items-center justify-between text-sm">
                    <span className="text-gray-700 capitalize">{name.replace(/_/g, ' ')}</span>
                    <span className="font-medium text-gray-900">{count}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Lista de objetos */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
              <h4 className="text-sm font-semibold text-gray-500 uppercase mb-3">
                Objetos Detectados
              </h4>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {result.objects.map((obj, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between p-2 bg-gray-50 rounded-lg text-sm"
                  >
                    <div>
                      <span className="font-medium text-gray-800 capitalize">
                        {obj.class_name.replace(/_/g, ' ')}
                      </span>
                      <span className="text-gray-400 ml-2 text-xs">
                        {obj.patrimony_type}
                      </span>
                    </div>
                    <span className={`font-medium ${getColorByConfidence(obj.confidence)}`}>
                      {(obj.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 flex items-center justify-center">
            <div className="text-center text-gray-400">
              <ImageIcon size={48} className="mx-auto mb-3 opacity-50" />
              <p className="text-lg font-medium">Nenhuma detecção</p>
              <p className="text-sm">Envie uma imagem para começar</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
