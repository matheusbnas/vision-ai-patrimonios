import { useState, useEffect, useCallback, useRef } from 'react'
import {
  ShieldAlert,
  Camera,
  Play,
  Pause,
  AlertTriangle,
  Brain,
  RefreshCw,
  WifiOff,
} from 'lucide-react'
import { api } from '../api/client'
import type { Patrimonio } from '../types'

interface DetectionFrame {
  camera_code: string
  camera_name: string
  stream_url?: string
  image_base64?: string
  frame_captured?: boolean
  processing_time_ms: number
  timestamp: number
  yolo_detection?: {
    objects: { class_name: string; confidence: number; patrimony_type: string; bbox: number[] }[]
    counts: Record<string, number>
    total_objects: number
  }
  // Novos campos do change detection (SSIM + HF)
  similarity_score?: number
  change_percentage?: number
  change_regions?: number
  significant_changes?: { bbox: number[]; area_percent: number }[]
  highlight_image_base64?: string
  hf_prediction?: Record<string, number>
  alert?: {
    level: string
    message: string
    source?: string
  }
  alert_level?: string
  ssim_alert_level?: string
}

function CameraQuadrant({
  patrimony,
  onSelect,
  isSelected,
}: {
  patrimony: Patrimonio
  onSelect: () => void
  isSelected: boolean
}) {
  return (
    <button
      onClick={onSelect}
      className={`p-2 rounded-lg border text-left transition-all ${
        isSelected
          ? 'border-red-400 bg-red-50 ring-1 ring-red-300'
          : 'border-gray-200 bg-white hover:border-gray-300'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="text-lg">{patrimony.emoji}</span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-gray-800 truncate">{patrimony.nome}</p>
          <p className="text-[10px] text-gray-400 truncate">
            {patrimony.camera_codes.length > 0
              ? patrimony.camera_codes.join(', ')
              : 'Sem câmera'}
          </p>
        </div>
        {patrimony.camera_codes.length > 0 && (
          <span className="status-dot online shrink-0" />
        )}
      </div>
    </button>
  )
}

export default function MonitoramentoPage() {
  const [patrimonios, setPatrimonios] = useState<Patrimonio[]>([])
  const [selectedCodes, setSelectedCodes] = useState<string[]>([])
  const [streamUrls, setStreamUrls] = useState<Record<string, string>>({})
  const [cameraNames, setCameraNames] = useState<Record<string, string>>({})
  const [frames, setFrames] = useState<Record<string, DetectionFrame>>({})
  const [running, setRunning] = useState(false)
  const [loading, setLoading] = useState(false)
  const [streamErrors, setStreamErrors] = useState<Record<string, boolean>>({})
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    api.getPatrimonios().then(setPatrimonios).catch(() => {})
  }, [])

  // Busca URLs reais dos streams (com JWT válido) sempre que selecionar câmeras
  const fetchStreamUrls = useCallback(async (codes: string[]) => {
    if (codes.length === 0) return
    try {
      const data = await api.getStreams(codes)
      if (data.success) {
        const urls: Record<string, string> = {}
        const names: Record<string, string> = {}
        for (const cam of data.cameras) {
          if (cam.stream_url) urls[cam.camera_code] = cam.stream_url
          names[cam.camera_code] = cam.camera_name
        }
        setStreamUrls(urls)
        setCameraNames(names)
      }
    } catch (err) {
      console.error('Erro ao buscar URLs dos streams:', err)
    }
  }, [])

  const toggleCamera = (codes: string[]) => {
    if (codes.length === 0) return
    const newSelected = [...selectedCodes]
    const alreadySelected = codes.every((c) => selectedCodes.includes(c))
    
    if (alreadySelected) {
      setSelectedCodes(selectedCodes.filter((c) => !codes.includes(c)))
    } else {
      codes.forEach((c) => {
        if (!newSelected.includes(c)) newSelected.push(c)
      })
      setSelectedCodes(newSelected.slice(0, 4))
    }
    setStreamErrors({})
  }

  // Quando selectedCodes muda, busca URLs reais dos streams
  useEffect(() => {
    if (selectedCodes.length > 0) {
      fetchStreamUrls(selectedCodes)
    } else {
      setStreamUrls({})
      setCameraNames({})
    }
  }, [selectedCodes, fetchStreamUrls])

  // Escaneia detecções (stream já roda separado no iframe)
  const scan = useCallback(async () => {
    if (selectedCodes.length === 0) return
    setLoading(true)
    try {
      const data = await api.monitorMulti(selectedCodes, 0.35)
      if (data.success) {
        const newFrames: Record<string, DetectionFrame> = {}
        for (const cam of data.cameras) {
          if (cam.success) {
            newFrames[cam.camera_code] = cam
          }
        }
        setFrames(newFrames)
      }
    } catch (err) {
      console.error('Erro no monitoramento:', err)
    } finally {
      setLoading(false)
    }
  }, [selectedCodes])

  const scanAndCompare = useCallback(async () => {
    await scan()
    // Se tiver referência, faz comparação automática
    for (const code of selectedCodes) {
      try {
        const data = await api.detectChanges(code, true)
        if (data.success && data.highlight_image_base64) {
          setFrames(prev => {
            const existing = prev[code]
            if (!existing) return prev
            return {
              ...prev,
              [code]: {
                ...existing,
                highlight_image_base64: data.highlight_image_base64,
                similarity_score: data.similarity_score,
                change_percentage: data.change_percentage,
                change_regions: data.change_regions,
                ssim_alert_level: data.ssim_alert_level,
                alert: data.alert || undefined,
                alert_level: data.alert_level || existing.alert_level || 'NORMAL',
                timestamp: Date.now() / 1000,
              }
            }
          })
        }
      } catch {}
    }
  }, [scan, selectedCodes])

  const toggleAutoScan = () => {
    if (running) {
      if (intervalRef.current) clearInterval(intervalRef.current)
      setRunning(false)
    } else {
      scanAndCompare()
      intervalRef.current = setInterval(scanAndCompare, 10000)
      setRunning(true)
    }
  }

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  const getAlertColor = (level?: string) => {
    switch (level) {
      case 'CRÍTICO': return 'bg-red-600 text-white'
      case 'ALTO': return 'bg-orange-500 text-white'
      case 'MODERADO': return 'bg-yellow-500 text-white'
      default: return 'bg-green-500 text-white'
    }
  }

  return (
    <div className="flex gap-4 h-full">
      {/* Sidebar - Lista de patrimônios */}
      <div className="w-56 flex-shrink-0 space-y-2 overflow-y-auto">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide px-1">
          Câmeras disponíveis
        </h3>
        <div className="space-y-1.5">
          {patrimonios
            .filter((p) => p.camera_codes.length > 0)
            .map((p) => {
              const anySelected = p.camera_codes.some((c) => selectedCodes.includes(c))
              return (
                <CameraQuadrant
                  key={p.id}
                  patrimony={p}
                  isSelected={anySelected}
                  onSelect={() => toggleCamera(p.camera_codes)}
                />
              )
            })}
        </div>

        <div className="pt-3 space-y-2">
          <button
            onClick={toggleAutoScan}
            disabled={selectedCodes.length === 0}
            className={`w-full py-2 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-all ${
              running
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-cor-blue text-white hover:bg-cor-blue-light disabled:opacity-40'
            }`}
          >
            {running ? <Pause size={16} /> : <Play size={16} />}
            {running ? 'Parar' : 'Iniciar Monitoramento'}
          </button>

          {running && (
            <div className="flex items-center gap-2 text-xs text-green-600 justify-center">
              <span className="status-dot online animate-pulse" />
              Monitorando {selectedCodes.length} câmera(s) a cada 10s
            </div>
          )}

          {selectedCodes.length > 0 && !running && (
            <button
              onClick={scan}
              disabled={loading}
              className="w-full py-2 rounded-lg text-sm font-medium bg-gray-100 text-gray-600 hover:bg-gray-200 flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              Escanear agora
            </button>
          )}
        </div>

        {/* ─── Referência vs Comparação ──────────────────── */}
        <div className="pt-4 border-t border-gray-200">
          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide px-1 mb-2">
            <Camera size={12} className="inline mr-1" />
            Referência do Monumento
          </h4>
          <p className="text-[10px] text-gray-400 px-1 mb-2 leading-relaxed">
            Salva o frame atual como base. Depois compara para detectar mudanças (pichação, danos, furto)
          </p>
          <div className="space-y-1.5">
            <button
              onClick={async () => {
                const code = selectedCodes[0] || '001175'
                setLoading(true)
                try {
                  const data = await api.setReference(code, true)
                  if (data.success) alert('✅ Referência salva! O sistema vai comparar os próximos frames.')
                } catch (err) { console.error(err) }
                finally { setLoading(false) }
              }}
              disabled={loading}
              className="w-full py-1.5 px-3 rounded-lg text-xs font-medium bg-green-50 text-green-700 hover:bg-green-100 border border-green-200 flex items-center gap-2 disabled:opacity-50"
            >
              <Camera size={12} />
              📸 Salvar como Referência
            </button>
            <button
              onClick={async () => {
                const code = selectedCodes[0] || '001175'
                setLoading(true)
                try {
                  const data = await api.detectChanges(code, true)
                  if (data.success) {
                    setFrames(prev => ({
                      ...prev,
                      [code]: {
                        ...prev[code],
                        camera_code: code,
                        highlight_image_base64: data.highlight_image_base64,
                        similarity_score: data.similarity_score,
                        change_percentage: data.change_percentage,
                        change_regions: data.change_regions,
                        significant_changes: data.significant_changes,
                        ssim_alert_level: data.ssim_alert_level,
                        hf_prediction: data.hf_prediction,
                        alert: data.alert || undefined,
                        alert_level: data.alert_level || 'NORMAL',
                        timestamp: Date.now() / 1000,
                      } as DetectionFrame
                    }))
                  }
                } catch (err) { console.error(err) }
                finally { setLoading(false) }
              }}
              disabled={loading}
              className="w-full py-1.5 px-3 rounded-lg text-xs font-medium bg-red-50 text-red-700 hover:bg-red-100 border border-red-200 flex items-center gap-2 disabled:opacity-50"
            >
              <RefreshCw size={12} />
              🔍 Comparar com Referência
            </button>
          </div>
        </div>
      </div>

      {/* Grid de câmeras */}
      <div className="flex-1 flex flex-col space-y-3">
        {selectedCodes.length > 0 ? (
          <>
            {/* Grid de quadrantes — ocupa toda a altura disponível */}
            <div className={`grid gap-3 flex-1 ${selectedCodes.length <= 1 ? 'grid-cols-1' : selectedCodes.length === 2 ? 'grid-cols-2' : 'grid-cols-2'}`}
                 style={{ gridTemplateRows: '1fr' }}>
              {selectedCodes.map((code) => {
                const frame = frames[code]
                const hasAlert = frame?.alert != null

                return (
                  <div key={code} className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden flex flex-col">
                    {/* Header da câmera */}
                    <div className={`flex items-center justify-between px-3 py-2 text-white text-xs font-medium ${
                      hasAlert ? 'bg-red-600 animate-pulse' : 'bg-gray-800'
                    }`}>
                      <div className="flex items-center gap-2">
                        <Camera size={14} />
                        <span>{cameraNames[code] || frame?.camera_name || `Câmera ${code}`}</span>
                        <span className="opacity-60">cód. {code}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {running && <span className="status-dot online" />}
                        {frame?.processing_time_ms != null && (
                          <span className="opacity-60 text-[10px]">
                            {frame.processing_time_ms.toFixed(0)}ms
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Stream ao vivo + overlay — ocupa a maior parte da tela */}
                    <div className="relative bg-black flex-1" style={{ minHeight: '420px' }}>
                      {/* Iframe do stream Tixxi com JWT real vindo da API */}
                      <iframe
                        key={code}
                        src={streamUrls[code]}
                        className="absolute inset-0 w-full h-full border-none"
                        allow="accelerometer;autoplay;encrypted-media;gyroscope"
                        allowFullScreen
                        onLoad={() => setStreamErrors((s) => ({ ...s, [code]: false }))}
                        onError={() => setStreamErrors((s) => ({ ...s, [code]: true }))}
                      />
                      {/* Overlay com imagem anotada do YOLO (quando disponível) */}
                      {frame?.image_base64 && (
                        <img
                          src={`data:image/jpeg;base64,${frame.image_base64}`}
                          alt={`Detecção ${code}`}
                          className="absolute inset-0 w-full h-full object-cover opacity-60 pointer-events-none"
                        />
                      )}
                      {/* Fallback se iframe falhar */}
                      {streamErrors[code] && (
                        <div className="absolute inset-0 flex items-center justify-center text-gray-400 text-sm bg-gray-900/90">
                          <div className="text-center">
                            <WifiOff size={28} className="mx-auto mb-2" />
                            <p>Stream indisponível</p>
                          </div>
                        </div>
                      )}

                      {/* Badge de alerta */}
                      {frame?.alert && (
                        <div className="absolute top-2 left-2 z-10">
                          <span className={`text-[10px] px-2 py-0.5 rounded font-bold shadow-lg ${
                            frame.alert.level === 'CRÍTICO' || frame.alert.level === 'ALTO'
                              ? 'bg-red-600 text-white animate-pulse'
                              : 'bg-yellow-500 text-black'
                          }`}>
                            🚨 {frame.alert.level}: {frame.alert.types?.join('/').toUpperCase()}
                          </span>
                        </div>
                      )}

                      {/* Badge AO VIVO */}
                      <div className="absolute top-2 right-2 z-10">
                        <span className="bg-red-600 text-white text-[10px] px-2 py-0.5 rounded font-bold animate-pulse shadow-lg">
                          🔴 AO VIVO
                        </span>
                      </div>
                    </div>

                    {/* Painel de análise - SSIM + HF */}
                    <div className="p-3 space-y-2 text-xs">
                      {/* Alerta (se houver) */}
                      {frame?.alert && (
                        <div className={`rounded-lg p-2 flex items-center gap-2 ${
                          frame.alert.level === 'CRÍTICO' ? 'bg-red-100 text-red-800 animate-pulse' :
                          frame.alert.level === 'ALTO' ? 'bg-orange-100 text-orange-800' :
                          'bg-yellow-100 text-yellow-800'
                        }`}>
                          <AlertTriangle size={16} className="shrink-0" />
                          <div>
                            <p className="font-bold text-[10px]">{frame.alert.message}</p>
                          </div>
                        </div>
                      )}

                      {/* SSIM: Similaridade / Mudança */}
                      {frame?.similarity_score != null && (
                        <div className="bg-blue-50 rounded-lg p-2">
                          <div className="grid grid-cols-3 gap-2 text-center">
                            <div>
                              <p className="text-lg font-bold text-blue-700">
                                {(frame.similarity_score * 100).toFixed(1)}%
                              </p>
                              <p className="text-[8px] text-gray-500">Similaridade</p>
                            </div>
                            <div>
                              <p className={`text-lg font-bold ${
                                (frame.change_percentage || 0) > 3 ? 'text-red-600' :
                                (frame.change_percentage || 0) > 0.5 ? 'text-yellow-600' :
                                'text-green-600'
                              }`}>
                                {frame.change_percentage?.toFixed(1)}%
                              </p>
                              <p className="text-[8px] text-gray-500">Alterado</p>
                            </div>
                            <div>
                              <p className="text-lg font-bold text-gray-700">{frame.change_regions || 0}</p>
                              <p className="text-[8px] text-gray-500">Regiões</p>
                            </div>
                          </div>
                          {frame.significant_changes && frame.significant_changes.length > 0 && (
                            <div className="mt-1 border-t border-blue-100 pt-1 space-y-0.5">
                              {frame.significant_changes.slice(0, 3).map((ch, i) => (
                                <p key={i} className="text-[9px] text-gray-500">
                                  • Região {i+1}: {ch.area_percent}% do monumento
                                </p>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Highlight image (diferenças em vermelho) */}
                      {frame?.highlight_image_base64 && (
                        <div className="rounded-lg overflow-hidden border border-gray-200">
                          <p className="text-[9px] font-semibold text-gray-500 uppercase px-2 pt-1.5 pb-0.5">
                            🔴 Diferenças detectadas (ROI do monumento)
                          </p>
                          <img
                            src={`data:image/jpeg;base64,${frame.highlight_image_base64}`}
                            alt="Comparativo do monumento"
                            className="w-full h-auto"
                          />
                        </div>
                      )}

                      {/* Predição HF */}
                      {frame?.hf_prediction && (
                        <div className="bg-purple-50 rounded-lg p-2">
                          <div className="flex items-center gap-1 mb-1.5">
                            <Brain size={12} className="text-purple-600" />
                            <span className="text-[10px] font-semibold text-purple-700">
                              KzRyan/Burglary_and_Vandalism
                            </span>
                          </div>
                          <div className="grid grid-cols-3 gap-2">
                            {Object.entries(frame.hf_prediction).map(([cls, prob]) => {
                              const pct = (prob as number * 100).toFixed(0)
                              const color = cls === 'vandalism' ? 'text-red-600' :
                                           cls === 'burglary' ? 'text-orange-500' :
                                           'text-green-600'
                              const bgColor = cls === 'vandalism' ? 'bg-red-50' :
                                             cls === 'burglary' ? 'bg-orange-50' :
                                             'bg-green-50'
                              return (
                                <div key={cls} className={`${bgColor} rounded p-1.5 text-center`}>
                                  <div className={`text-sm font-bold ${color}`}>
                                    {pct}%
                                  </div>
                                  <div className="text-[9px] text-gray-500 capitalize leading-tight">
                                    {cls === 'burglary' ? '💰 Roubo/Furto' :
                                     cls === 'vandalism' ? '🔨 Vandalismo' :
                                     '✅ Normal'}
                                  </div>
                                  <div className="w-full bg-gray-200 rounded-full h-1 mt-1">
                                    <div className={`h-1 rounded-full ${
                                      cls === 'vandalism' ? 'bg-red-500' :
                                      cls === 'burglary' ? 'bg-orange-500' :
                                      'bg-green-500'
                                    }`} style={{ width: `${pct}%` }} />
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )}

                      {/* Objetos detectados pelo YOLO */}
                      {frame?.yolo_detection?.total_objects > 0 && (
                        <div>
                          <p className="text-[9px] font-semibold text-gray-500 uppercase mb-1">
                            <ShieldAlert size={10} className="inline mr-0.5" />
                            Objetos detectados
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {Object.entries(frame.yolo_detection.counts).map(([name, count]) => (
                              <span key={name} className="bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded text-[9px]">
                                {name.replace(/_/g, ' ')}: {count}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Mensagem vazia */}
                      {!frame?.alert && frame?.similarity_score == null && !frame?.hf_prediction && (
                        <div className="text-center text-gray-400 text-[10px] py-1">
                          {frame ? 'Aguardando verificação...' : 'Aguardando primeiro scan...'}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Alerta geral */}
            {Object.values(frames).some((f) => f.alert != null) && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-3 flex items-center gap-3">
                <AlertTriangle size={20} className="text-red-500 shrink-0" />
                <div>
                  <p className="text-sm font-bold text-red-700">🚨 ALERTA DE VANDALISMO DETECTADO</p>
                  <p className="text-xs text-red-600">
                    {Object.values(frames)
                      .filter((f) => f.alert != null)
                      .map((f) => `${f.camera_name} (cód. ${f.camera_code})`)
                      .join(', ')}
                  </p>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 flex items-center justify-center h-full">
            <div className="text-center text-gray-400">
              <Camera size={48} className="mx-auto mb-3 opacity-50" />
              <p className="text-lg font-medium">Selecione as câmeras</p>
              <p className="text-sm">Escolha os patrimônios ao lado para monitorar em tempo real</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
