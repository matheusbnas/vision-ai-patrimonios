import { useEffect, useRef, useState, useCallback } from 'react'
import { X, Target, RotateCcw, Save, Trash2 } from 'lucide-react'
import { api, type ZoneRect } from '../api/client'

type Zone = ZoneRect

const MIN_SIZE = 0.02

type DragMode = 'move' | 'nw' | 'ne' | 'sw' | 'se'

// Três camadas por câmera:
//   zona      — quadrante amplo ao redor do monumento (comportamento antigo)
//   estátua   — contorno JUSTO da estátua (objetos de risco precisam
//               encostar nele; pose; comparação SSIM)
//   sensível  — parte que costuma ser alvo de furto (óculos, cabeça, violão)
type Layer = 'zone' | 'statue' | 'sensitive'

const LAYERS: { id: Layer; label: string; color: string; handle: string; hint: string }[] = [
  {
    id: 'zone',
    label: 'Zona',
    color: 'border-yellow-400 bg-yellow-400/10',
    handle: 'bg-yellow-400',
    hint: 'Quadrante amplo ao redor do monumento.',
  },
  {
    id: 'statue',
    label: 'Estátua',
    color: 'border-cyan-400 bg-cyan-400/10',
    handle: 'bg-cyan-400',
    hint: 'Contorno JUSTO da figura da estátua (inclua o pedestal só se for baixo). Objetos só alertam se encostarem aqui; pessoas em cima da estátua são detectadas por este contorno.',
  },
  {
    id: 'sensitive',
    label: 'Área sensível',
    color: 'border-fuchsia-500 bg-fuchsia-500/10',
    handle: 'bg-fuchsia-500',
    hint: 'Parte que costuma ser alvo de furto (óculos/cabeça do Drummond, violão do Tom Jobim...). Mão de alguém aqui gera alerta.',
  },
]

interface DragState {
  layer: Layer
  mode: DragMode
  startFracX: number
  startFracY: number
  startZone: Zone
}

function clamp(v: number, min: number, max: number) {
  return Math.min(Math.max(v, min), max)
}

// Retângulo inicial quando a camada ainda não existe: dentro da zona/estátua
function defaultRect(parent: Zone | null, shrink: number): Zone {
  const p = parent ?? { x_start: 0.3, x_end: 0.7, y_start: 0.2, y_end: 0.8 }
  const w = p.x_end - p.x_start
  const h = p.y_end - p.y_start
  return {
    x_start: p.x_start + w * shrink,
    x_end: p.x_end - w * shrink,
    y_start: p.y_start + h * shrink,
    y_end: shrink >= 0.3 ? p.y_start + h * 0.35 : p.y_end - h * shrink,
  }
}

export default function ZoneCalibrator({
  cameraCode,
  onClose,
}: {
  cameraCode: string
  onClose: () => void
}) {
  const [imageBase64, setImageBase64] = useState<string | null>(null)
  const [rects, setRects] = useState<Record<Layer, Zone | null>>({ zone: null, statue: null, sensitive: null })
  const [active, setActive] = useState<Layer>('statue')
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
      const [frameData, zoneData, statueData] = await Promise.all([
        api.getZoneFrame(cameraCode),
        api.getZone(cameraCode),
        api.getStatue(cameraCode),
      ])
      if (frameData.success) setImageBase64(frameData.image_base64)
      setRects({ zone: zoneData.zone, statue: statueData.statue, sensitive: statueData.sensitive })
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

      let next: Zone
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
        next = { x_start, x_end, y_start, y_end }
      } else {
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
        next = { x_start, x_end, y_start, y_end }
      }
      setRects((r) => ({ ...r, [drag.layer]: next }))
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

  const startDrag = (layer: Layer, mode: DragMode) => (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const zone = rects[layer]
    if (!zone) return
    const { x, y } = fracFromEvent(e.nativeEvent)
    dragRef.current = { layer, mode, startFracX: x, startFracY: y, startZone: zone }
  }

  const selectLayer = (layer: Layer) => {
    setActive(layer)
    // Camada ainda não desenhada: cria um retângulo inicial pra arrastar
    setRects((r) => {
      if (r[layer]) return r
      if (layer === 'statue') return { ...r, statue: defaultRect(r.zone, 0.25) }
      if (layer === 'sensitive') return { ...r, sensitive: defaultRect(r.statue ?? r.zone, 0.3) }
      return r
    })
  }

  const handleSave = async () => {
    if (!rects.zone) return
    if (rects.sensitive && !rects.statue) {
      setError('Desenhe o contorno da estátua antes da área sensível.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.setZone(cameraCode, rects.zone)
      if (rects.statue) {
        await api.setStatue(cameraCode, rects.statue, rects.sensitive)
      } else {
        await api.resetStatue(cameraCode)
      }
      onClose()
    } catch (err) {
      console.error(err)
      setError('Não foi possível salvar a calibração.')
    } finally {
      setSaving(false)
    }
  }

  // Reseta a camada ativa: zona volta ao padrão; estátua/sensível são removidas
  const handleReset = async () => {
    if (active === 'zone') {
      setSaving(true)
      try {
        const data = await api.resetZone(cameraCode)
        setRects((r) => ({ ...r, zone: data.zone }))
        setIsCustom(false)
      } catch (err) {
        console.error(err)
      } finally {
        setSaving(false)
      }
    } else if (active === 'statue') {
      setRects((r) => ({ ...r, statue: null, sensitive: null }))
    } else {
      setRects((r) => ({ ...r, sensitive: null }))
    }
  }

  const handles: { mode: DragMode; className: string }[] = [
    { mode: 'nw', className: '-top-1.5 -left-1.5 cursor-nwse-resize' },
    { mode: 'ne', className: '-top-1.5 -right-1.5 cursor-nesw-resize' },
    { mode: 'sw', className: '-bottom-1.5 -left-1.5 cursor-nesw-resize' },
    { mode: 'se', className: '-bottom-1.5 -right-1.5 cursor-nwse-resize' },
  ]
  const activeLayer = LAYERS.find((l) => l.id === active)!

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-white rounded-xl shadow-xl border border-gray-200 max-w-2xl w-full overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <Target size={16} className="text-cor-blue" />
            <h3 className="text-sm font-semibold text-gray-800">
              Calibrar câmera {cameraCode}
            </h3>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={18} />
          </button>
        </div>

        <div className="p-4 space-y-3">
          <div className="flex rounded-lg bg-gray-100 p-0.5 text-xs font-medium">
            {LAYERS.map((l) => (
              <button
                key={l.id}
                onClick={() => selectLayer(l.id)}
                className={`flex-1 py-1.5 rounded-md flex items-center justify-center gap-1.5 ${
                  active === l.id ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <span className={`w-2.5 h-2.5 rounded-sm ${l.handle}`} />
                {l.label}
                {l.id !== 'zone' && !rects[l.id] && <span className="text-[10px] text-gray-400">(não definida)</span>}
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-500">{activeLayer.hint} Arraste o retângulo ou as alças dos cantos.</p>

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
              {LAYERS.map((l) => {
                const zone = rects[l.id]
                if (!zone) return null
                const isActive = l.id === active
                return (
                  <div
                    key={l.id}
                    onMouseDown={isActive ? startDrag(l.id, 'move') : undefined}
                    className={`absolute border-2 ${l.color} ${
                      isActive ? 'cursor-move z-10' : 'pointer-events-none opacity-50'
                    }`}
                    style={{
                      left: `${zone.x_start * 100}%`,
                      top: `${zone.y_start * 100}%`,
                      width: `${(zone.x_end - zone.x_start) * 100}%`,
                      height: `${(zone.y_end - zone.y_start) * 100}%`,
                    }}
                  >
                    {isActive && handles.map((h) => (
                      <div
                        key={h.mode}
                        onMouseDown={startDrag(l.id, h.mode)}
                        className={`absolute w-3 h-3 ${l.handle} border border-white rounded-sm ${h.className}`}
                      />
                    ))}
                  </div>
                )
              })}
            </div>
          )}

          {error && imageBase64 && <p className="text-xs text-red-500">{error}</p>}

          <div className="flex items-center justify-between pt-1">
            <button
              onClick={handleReset}
              disabled={saving || loading || (active === 'zone' ? !isCustom : !rects[active])}
              className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 flex items-center gap-1.5 disabled:opacity-40"
            >
              {active === 'zone' ? <RotateCcw size={12} /> : <Trash2 size={12} />}
              {active === 'zone' ? 'Resetar zona para padrão' : `Remover ${activeLayer.label.toLowerCase()}`}
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
                disabled={saving || loading || !rects.zone}
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
