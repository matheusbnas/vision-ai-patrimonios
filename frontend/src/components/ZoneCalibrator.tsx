import { useEffect, useRef, useState, useCallback } from 'react'
import { X, Target, RotateCcw, Save } from 'lucide-react'
import { api } from '../api/client'

interface Zone {
  x_start: number
  x_end: number
  y_start: number
  y_end: number
}

const MIN_SIZE = 0.05

type DragMode = 'move' | 'nw' | 'ne' | 'sw' | 'se'

interface DragState {
  mode: DragMode
  startFracX: number
  startFracY: number
  startZone: Zone
}

function clamp(v: number, min: number, max: number) {
  return Math.min(Math.max(v, min), max)
}

export default function ZoneCalibrator({
  cameraCode,
  onClose,
}: {
  cameraCode: string
  onClose: () => void
}) {
  const [imageBase64, setImageBase64] = useState<string | null>(null)
  const [zone, setZone] = useState<Zone | null>(null)
  const [isCustom, setIsCustom] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const containerRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<DragState | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [frameData, zoneData] = await Promise.all([
        api.getZoneFrame(cameraCode),
        api.getZone(cameraCode),
      ])
      if (frameData.success) setImageBase64(frameData.image_base64)
      setZone(zoneData.zone)
      setIsCustom(zoneData.is_custom)
    } catch (err) {
      console.error(err)
      setError('Não foi possível carregar o frame da câmera.')
    } finally {
      setLoading(false)
    }
  }, [cameraCode])

  useEffect(() => {
    load()
  }, [load])

  const fracFromEvent = useCallback((e: MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    return {
      x: clamp((e.clientX - rect.left) / rect.width, 0, 1),
      y: clamp((e.clientY - rect.top) / rect.height, 0, 1),
    }
  }, [])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const drag = dragRef.current
      if (!drag) return
      const { x, y } = fracFromEvent(e)
      const dx = x - drag.startFracX
      const dy = y - drag.startFracY
      const s = drag.startZone

      setZone(() => {
        if (drag.mode === 'move') {
          const w = s.x_end - s.x_start
          const h = s.y_end - s.y_start
          let x_start = s.x_start + dx
          let x_end = s.x_end + dx
          let y_start = s.y_start + dy
          let y_end = s.y_end + dy
          if (x_start < 0) { x_start = 0; x_end = w }
          if (x_end > 1) { x_end = 1; x_start = 1 - w }
          if (y_start < 0) { y_start = 0; y_end = h }
          if (y_end > 1) { y_end = 1; y_start = 1 - h }
          return { x_start, x_end, y_start, y_end }
        }

        let { x_start, x_end, y_start, y_end } = s
        if (drag.mode === 'nw' || drag.mode === 'sw') {
          x_start = clamp(s.x_start + dx, 0, s.x_end - MIN_SIZE)
        }
        if (drag.mode === 'ne' || drag.mode === 'se') {
          x_end = clamp(s.x_end + dx, s.x_start + MIN_SIZE, 1)
        }
        if (drag.mode === 'nw' || drag.mode === 'ne') {
          y_start = clamp(s.y_start + dy, 0, s.y_end - MIN_SIZE)
        }
        if (drag.mode === 'sw' || drag.mode === 'se') {
          y_end = clamp(s.y_end + dy, s.y_start + MIN_SIZE, 1)
        }
        return { x_start, x_end, y_start, y_end }
      })
    }

    const onUp = () => {
      dragRef.current = null
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [fracFromEvent])

  const startDrag = (mode: DragMode) => (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!zone) return
    const { x, y } = fracFromEvent(e.nativeEvent)
    dragRef.current = { mode, startFracX: x, startFracY: y, startZone: zone }
  }

  const handleSave = async () => {
    if (!zone) return
    setSaving(true)
    setError(null)
    try {
      await api.setZone(cameraCode, zone)
      onClose()
    } catch (err) {
      console.error(err)
      setError('Não foi possível salvar a zona.')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    setSaving(true)
    try {
      const data = await api.resetZone(cameraCode)
      setZone(data.zone)
      setIsCustom(false)
    } catch (err) {
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  const handles: { mode: DragMode; className: string }[] = [
    { mode: 'nw', className: '-top-1.5 -left-1.5 cursor-nwse-resize' },
    { mode: 'ne', className: '-top-1.5 -right-1.5 cursor-nesw-resize' },
    { mode: 'sw', className: '-bottom-1.5 -left-1.5 cursor-nesw-resize' },
    { mode: 'se', className: '-bottom-1.5 -right-1.5 cursor-nwse-resize' },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-white rounded-xl shadow-xl border border-gray-200 max-w-2xl w-full overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <Target size={16} className="text-cor-blue" />
            <h3 className="text-sm font-semibold text-gray-800">
              Calibrar zona — câmera {cameraCode}
            </h3>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={18} />
          </button>
        </div>

        <div className="p-4 space-y-3">
          <p className="text-xs text-gray-500">
            Arraste o retângulo ou as alças dos cantos para ajustar o quadrante ao redor do monumento.
          </p>

          {loading ? (
            <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
              Carregando frame da câmera...
            </div>
          ) : error && !imageBase64 ? (
            <div className="h-64 flex items-center justify-center text-red-500 text-sm">{error}</div>
          ) : (
            <div ref={containerRef} className="relative select-none bg-black rounded-lg overflow-hidden">
              {imageBase64 && (
                <img
                  src={`data:image/jpeg;base64,${imageBase64}`}
                  alt={`Frame câmera ${cameraCode}`}
                  className="w-full h-auto block pointer-events-none"
                  draggable={false}
                />
              )}
              {zone && (
                <div
                  onMouseDown={startDrag('move')}
                  className="absolute border-2 border-yellow-400 bg-yellow-400/10 cursor-move"
                  style={{
                    left: `${zone.x_start * 100}%`,
                    top: `${zone.y_start * 100}%`,
                    width: `${(zone.x_end - zone.x_start) * 100}%`,
                    height: `${(zone.y_end - zone.y_start) * 100}%`,
                  }}
                >
                  {handles.map((h) => (
                    <div
                      key={h.mode}
                      onMouseDown={startDrag(h.mode)}
                      className={`absolute w-3 h-3 bg-yellow-400 border border-white rounded-sm ${h.className}`}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {error && imageBase64 && <p className="text-xs text-red-500">{error}</p>}

          <div className="flex items-center justify-between pt-1">
            <button
              onClick={handleReset}
              disabled={saving || loading || !isCustom}
              className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 flex items-center gap-1.5 disabled:opacity-40"
            >
              <RotateCcw size={12} />
              Resetar para padrão
            </button>
            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="text-xs px-3 py-1.5 rounded-lg text-gray-500 hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                onClick={handleSave}
                disabled={saving || loading || !zone}
                className="text-xs px-3 py-1.5 rounded-lg bg-cor-blue text-white hover:bg-cor-blue-light flex items-center gap-1.5 disabled:opacity-50"
              >
                <Save size={12} />
                {saving ? 'Salvando...' : 'Salvar'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
