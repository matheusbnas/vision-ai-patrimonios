import { useState, useRef, useEffect } from 'react'
import {
  Upload,
  Loader2,
  X,
  Brain,
  FileVideo,
  BarChart3,
  UserX,
  CheckCircle2,
  AlertTriangle,
  Info,
  ChevronDown,
} from 'lucide-react'
import { api } from '../api/client'

type Verdict = 'cena' | 'grafico' | 'sem_pessoas'

interface HFResponse {
  success: boolean
  media_type: 'image' | 'video'
  classified: boolean
  predictions: Record<string, number> | null
  reliability: 'baixa' | 'media' | null
  interpretation: string
  top_class?: string
  motion?: number | null
  processing_time_ms: number
  domain: {
    verdict: Verdict
    reason: string
    people: number
    objects: Record<string, number>
    graphic: { top_color: number; top_color_tol: number; top8: number; flat: number; is_graphic: boolean }
  }
}

const CLASS_LABEL: Record<string, string> = {
  normal: 'Normal',
  burglary: 'Roubo / furto',
  vandalism: 'Vandalismo',
}
const CLASS_BAR: Record<string, string> = {
  normal: 'bg-emerald-500',
  burglary: 'bg-orange-500',
  vandalism: 'bg-red-500',
}

const VERDICT_UI: Record<Verdict, { title: string; icon: React.ReactNode; box: string }> = {
  cena: {
    title: 'Cena de câmera com pessoas',
    icon: <CheckCircle2 size={18} className="text-emerald-600" />,
    box: 'bg-emerald-50 ring-emerald-200 text-emerald-800',
  },
  grafico: {
    title: 'Não é uma cena de câmera',
    icon: <BarChart3 size={18} className="text-slate-500" />,
    box: 'bg-slate-50 ring-slate-200 text-slate-700',
  },
  sem_pessoas: {
    title: 'Nenhuma pessoa na cena',
    icon: <UserX size={18} className="text-amber-600" />,
    box: 'bg-amber-50 ring-amber-200 text-amber-800',
  },
}

export default function VandalismoPage() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [result, setResult] = useState<HFResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [showDetails, setShowDetails] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Libera a URL do preview ao trocar de arquivo
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  const isVideo = !!file && (file.type.startsWith('video/') || /\.(mp4|avi|mov|mkv|webm|3gp|m4v)$/i.test(file.name))

  const handleFile = (f: File) => {
    setResult(null)
    setError(null)
    setFile(f)
    const media = f.type.startsWith('image/') || f.type.startsWith('video/')
      || /\.(jpe?g|png|webp|bmp|gif|tiff?|mp4|avi|mov|mkv|webm|3gp|m4v)$/i.test(f.name)
    setPreview(media ? URL.createObjectURL(f) : null)
    if (!media) setError('Formato não reconhecido como imagem ou vídeo — o servidor vai tentar ler mesmo assim.')
  }

  const clear = () => {
    setFile(null)
    setPreview(null)
    setResult(null)
    setError(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const analyze = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const r = await api.hfPredict(file, 'vandalism')
      // Backend antigo (sem a verificação de cena) responde só `predictions`:
      // não exibe esse resultado, que classificaria até gráfico como vandalismo
      if (!r?.domain?.verdict) {
        setError(
          'O servidor está com uma versão antiga da análise (sem a verificação de cena). ' +
          'Reinicie o backend para aplicar a atualização e tente de novo.'
        )
        return
      }
      setResult(r as HFResponse)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Erro ao analisar o arquivo')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* ── Envio ─────────────────────────────────────── */}
      <div className="space-y-4">
        <div
          onClick={() => !file && inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            const f = e.dataTransfer.files?.[0]
            if (f) handleFile(f)
          }}
          className={`relative rounded-xl border-2 border-dashed bg-white p-6 text-center transition-colors ${
            dragging ? 'border-cor-blue bg-sky-50' : 'border-slate-300'
          } ${file ? '' : 'cursor-pointer hover:border-cor-blue'}`}
        >
          {file ? (
            <div className="relative">
              {preview && isVideo ? (
                <video src={preview} controls muted className="max-h-80 mx-auto rounded-lg bg-black" />
              ) : preview ? (
                <img src={preview} alt="Pré-visualização" className="max-h-80 mx-auto rounded-lg" />
              ) : (
                <div className="py-10 text-slate-400">
                  <FileVideo size={40} className="mx-auto mb-2" />
                </div>
              )}
              <p className="mt-3 text-sm font-medium text-slate-700 truncate">{file.name}</p>
              <p className="text-xs text-slate-400">
                {isVideo ? 'Vídeo' : 'Imagem'} · {(file.size / 1024 / 1024).toFixed(2)} MB
              </p>
              <button
                onClick={(e) => { e.stopPropagation(); clear() }}
                className="absolute top-0 right-0 p-1.5 bg-red-500 text-white rounded-full hover:bg-red-600 shadow"
                title="Remover arquivo"
              >
                <X size={16} />
              </button>
            </div>
          ) : (
            <div className="py-12">
              <Upload size={44} className="mx-auto mb-4 text-slate-300" />
              <p className="text-slate-600 font-medium">Arraste ou clique para enviar uma imagem ou vídeo</p>
              <p className="text-xs text-slate-400 mt-1">
                Qualquer imagem (JPG, PNG, WEBP…) ou vídeo (MP4, MOV, AVI…). Vídeo dá resultado mais confiável.
              </p>
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
            onClick={analyze}
            disabled={loading}
            className="w-full py-3 bg-cor-blue text-white rounded-lg font-medium hover:bg-cor-blue-light transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={20} className="animate-spin" /> : <Brain size={20} />}
            {loading ? 'Analisando…' : 'Analisar roubo / vandalismo'}
          </button>
        )}

        {error && (
          <div className="bg-red-50 ring-1 ring-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>
        )}

        <div className="rounded-xl bg-white ring-1 ring-slate-200 p-4 text-xs text-slate-600 space-y-1.5">
          <p className="flex items-center gap-1.5 font-semibold text-slate-700">
            <Info size={14} className="text-cor-blue" /> Como funciona
          </p>
          <p>
            1. <strong>Verificação da cena:</strong> gráficos, documentos, prints de tela, desenhos e
            cenas sem pessoas não são classificados.
          </p>
          <p>
            2. <strong>Classificação</strong> com o modelo KzRyan/Burglary_and_Vandalism (Hugging Face),
            treinado com vídeos de câmeras de segurança: normal, roubo ou vandalismo.
          </p>
          <p>
            O resultado é sempre um <strong>indício para validação humana</strong>. Em imagem parada a
            confiabilidade é baixa, porque o modelo aprendeu com o movimento entre os frames.
          </p>
        </div>
      </div>

      {/* ── Resultado ─────────────────────────────────── */}
      <div className="space-y-4">
        {!result && (
          <div className="bg-white rounded-xl shadow-sm ring-1 ring-slate-200 p-12 flex items-center justify-center">
            <div className="text-center text-slate-400">
              <Brain size={48} className="mx-auto mb-3 opacity-50" />
              <p className="text-lg font-medium">Nenhuma análise</p>
              <p className="text-sm">Envie uma imagem ou vídeo para analisar</p>
            </div>
          </div>
        )}

        {result && (
          <>
            {/* 1. Verificação da cena */}
            <div className={`rounded-xl ring-1 p-4 ${VERDICT_UI[result.domain.verdict].box}`}>
              <p className="flex items-center gap-2 font-semibold">
                {VERDICT_UI[result.domain.verdict].icon}
                {VERDICT_UI[result.domain.verdict].title}
              </p>
              <p className="mt-1.5 text-sm opacity-90">{result.domain.reason}</p>
              {Object.keys(result.domain.objects).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(result.domain.objects).map(([name, n]) => (
                    <span key={name} className="text-[11px] px-2 py-0.5 rounded bg-white/70 ring-1 ring-black/5">
                      {name}: {n}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* 2. Classificação */}
            {result.classified && result.predictions && (
              <div className="bg-white rounded-xl shadow-sm ring-1 ring-slate-200 p-5">
                <div className="flex items-start justify-between gap-3 mb-4">
                  <div>
                    <h3 className="font-semibold text-slate-800 flex items-center gap-2">
                      <Brain size={18} className="text-cor-blue" />
                      Classificação do modelo
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">KzRyan/Burglary_and_Vandalism · CNN-Transformer</p>
                  </div>
                  <span
                    className={`flex-shrink-0 text-[11px] font-semibold px-2 py-1 rounded-full ${
                      result.reliability === 'media'
                        ? 'bg-sky-100 text-sky-800'
                        : 'bg-amber-100 text-amber-800'
                    }`}
                    title={result.reliability === 'media' ? 'Vídeo com movimento' : 'Imagem parada ou vídeo sem movimento'}
                  >
                    Confiabilidade {result.reliability === 'media' ? 'média' : 'baixa'}
                  </span>
                </div>

                <div className={`space-y-3 ${result.reliability === 'baixa' ? 'opacity-70' : ''}`}>
                  {['normal', 'burglary', 'vandalism'].map((cls) => {
                    const prob = result.predictions![cls] ?? 0
                    const top = result.top_class === cls
                    return (
                      <div key={cls}>
                        <div className="flex items-center justify-between text-sm mb-1">
                          <span className={`text-slate-700 ${top ? 'font-semibold' : ''}`}>{CLASS_LABEL[cls]}</span>
                          <span className="font-semibold tabular-nums text-slate-700">{(prob * 100).toFixed(1)}%</span>
                        </div>
                        <div className="w-full bg-slate-100 rounded-full h-2">
                          <div
                            className={`h-2 rounded-full transition-all ${CLASS_BAR[cls]}`}
                            style={{ width: `${prob * 100}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>

                <div
                  className={`mt-4 p-3 rounded-lg text-xs flex gap-2 ${
                    result.reliability === 'baixa'
                      ? 'bg-amber-50 text-amber-800'
                      : result.top_class && result.top_class !== 'normal'
                        ? 'bg-red-50 text-red-800'
                        : 'bg-emerald-50 text-emerald-800'
                  }`}
                >
                  <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                  <span>{result.interpretation}</span>
                </div>
              </div>
            )}

            {/* Detalhes técnicos */}
            <div className="bg-white rounded-xl ring-1 ring-slate-200">
              <button
                onClick={() => setShowDetails((v) => !v)}
                className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-medium text-slate-500 hover:text-slate-800"
              >
                Detalhes técnicos
                <ChevronDown size={14} className={`transition-transform ${showDetails ? 'rotate-180' : ''}`} />
              </button>
              {showDetails && (
                <dl className="px-4 pb-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-slate-600">
                  <dt>Tipo</dt><dd>{result.media_type === 'video' ? 'vídeo' : 'imagem'}</dd>
                  <dt>Pessoas detectadas</dt><dd>{result.domain.people}</dd>
                  <dt>Cor exata mais frequente</dt><dd>{(result.domain.graphic.top_color * 100).toFixed(1)}% (arte ≥ 20%)</dd>
                  <dt>Área lisa</dt><dd>{(result.domain.graphic.flat * 100).toFixed(1)}%</dd>
                  {result.motion != null && (<><dt>Movimento no vídeo</dt><dd>{result.motion}</dd></>)}
                  <dt>Tempo</dt><dd>{(result.processing_time_ms / 1000).toFixed(1)} s</dd>
                </dl>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
