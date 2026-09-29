import { useState, useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Circle, Polyline, Tooltip, useMap } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import L from 'leaflet'
import {
  Radar,
  Camera as CameraIcon,
  AlertTriangle,
  Play,
  Eye,
  EyeOff,
  Crosshair,
  MapPin,
  ChevronRight,
} from 'lucide-react'
import { api } from '../api/client'
import type { Camera, Patrimonio } from '../types'

// Máximo de câmeras abertas de uma vez pelo "Monitorar perímetro" (mais que
// isso deixa o navegador e a captura no servidor pesados demais)
const MAX_MONITOR_CAMERAS = 10
// Janela em que um alerta ainda "acende" o perímetro no mapa
const ALERT_WINDOW_S = 30 * 60
const RIO_CENTER: [number, number] = [-22.9068, -43.1729]

interface Alert {
  id: number
  timestamp: number
  camera_code: string
  camera_name: string
  level: string
  message: string
}

interface GeoCamera {
  code: string
  name: string
  lat: number
  lng: number
  raw: Camera
}

interface PerimeterCamera extends GeoCamera {
  distance: number
  dedicated: boolean
}

interface Perimeter {
  patrimonio: Patrimonio
  cameras: PerimeterCamera[]
  /** Câmeras fixas do patrimônio sem coordenada na base (não aparecem no mapa) */
  dedicatedWithoutCoords: string[]
  alerts: Alert[]
}

// Distância em metros entre dois pontos (haversine)
function distanceM(lat1: number, lng1: number, lat2: number, lng2: number) {
  const R = 6371000
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLng = toRad(lng2 - lng1)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

function formatDistance(m: number) {
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`
}

function cameraCode(c: Camera & { codigo?: string; camera_code?: string }) {
  return String(c.code ?? c.codigo ?? c.camera_code ?? c.id ?? '')
}

// ─── Ícones ─────────────────────────────────────────────────────

function patrimonyIcon(emoji: string, state: 'normal' | 'selected' | 'alert') {
  const ring = state === 'alert' ? '#dc2626' : state === 'selected' ? '#c9a84c' : '#ffffff'
  const pulse = state === 'alert' ? '<span class="map-pulse"></span>' : ''
  return L.divIcon({
    className: 'map-icon',
    html: `<div class="map-patrimony" style="border-color:${ring}">${pulse}<span>${emoji || '🏛️'}</span></div>`,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
    popupAnchor: [0, -20],
  })
}

const svgCam =
  '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m16 13 5.2 3.5a.5.5 0 0 0 .8-.4V7.9a.5.5 0 0 0-.8-.4L16 11"/><rect x="2" y="6" width="14" height="12" rx="2"/></svg>'

const perimeterIcons = {
  dedicated: L.divIcon({
    className: 'map-icon',
    html: `<div class="map-cam map-cam--dedicated">${svgCam}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  }),
  nearby: L.divIcon({
    className: 'map-icon',
    html: `<div class="map-cam map-cam--nearby">${svgCam}</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  }),
  alert: L.divIcon({
    className: 'map-icon',
    html: `<div class="map-cam map-cam--alert"><span class="map-pulse"></span>${svgCam}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  }),
}

const idleCameraIcon = L.divIcon({
  className: 'map-icon',
  html: '<div class="map-cam map-cam--idle"></div>',
  iconSize: [10, 10],
  iconAnchor: [5, 5],
})

// ─── Controle de câmera do mapa (foco no perímetro selecionado) ─

function MapFocus({ target, radius, all }: { target: Patrimonio | null; radius: number; all: Patrimonio[] }) {
  const map = useMap()
  useEffect(() => {
    if (target) {
      const bounds = L.latLng(target.latitude, target.longitude).toBounds(radius * 2.4)
      map.flyToBounds(bounds, { duration: 0.8 })
    } else if (all.length > 0) {
      const bounds = L.latLngBounds(all.map((p) => [p.latitude, p.longitude] as [number, number]))
      map.fitBounds(bounds.pad(0.3), { maxZoom: 14 })
    }
  }, [target, radius, all, map])
  return null
}

// ─── Página ─────────────────────────────────────────────────────

interface Props {
  onMonitor: (codes: string[]) => void
}

export default function MapaPage({ onMonitor }: Props) {
  const [patrimonios, setPatrimonios] = useState<Patrimonio[]>([])
  const [cameras, setCameras] = useState<Camera[]>([])
  const [liveCodes, setLiveCodes] = useState<Set<string>>(new Set())
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [radius, setRadius] = useState<number>(() => {
    try {
      const v = Number(localStorage.getItem('mapa.raio'))
      return v >= 100 && v <= 1500 ? v : 300
    } catch {
      return 300
    }
  })
  const [showAllCameras, setShowAllCameras] = useState(true)

  useEffect(() => {
    try { localStorage.setItem('mapa.raio', String(radius)) } catch {}
  }, [radius])

  useEffect(() => {
    Promise.all([api.getPatrimonios(), api.getCameras().catch(() => [])])
      .then(([p, c]) => {
        setPatrimonios(p)
        setCameras(c)
      })
      .finally(() => setLoading(false))
  }, [])

  // Status ao vivo + alertas recentes, atualizados periodicamente
  useEffect(() => {
    const load = async () => {
      try {
        const data = await api.getLiveStatus()
        const live = new Set<string>()
        for (const c of data.cameras ?? []) if (c.state === 'ao vivo') live.add(c.camera_code)
        setLiveCodes(live)
      } catch {
        setLiveCodes(new Set())
      }
      try {
        const data = await api.getAlerts({ limit: 100 })
        setAlerts(data.alerts ?? [])
      } catch {
        // mantém os últimos alertas conhecidos
      }
    }
    load()
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [])

  const geoCameras = useMemo<GeoCamera[]>(
    () =>
      cameras
        .map((c) => ({
          code: cameraCode(c),
          name: c.name || c.localizacao || `Câmera ${cameraCode(c)}`,
          lat: Number(c.latitude),
          lng: Number(c.longitude),
          raw: c,
        }))
        .filter((c) => c.code && Number.isFinite(c.lat) && Number.isFinite(c.lng) && c.lat !== 0 && c.lng !== 0),
    [cameras]
  )

  // Câmeras dentro do raio de cada patrimônio (fixas sempre entram)
  const perimeters = useMemo<Perimeter[]>(() => {
    const now = Date.now() / 1000
    const recentAlerts = alerts.filter((a) => now - a.timestamp <= ALERT_WINDOW_S)
    return patrimonios.map((p) => {
      const dedicatedSet = new Set(p.camera_codes)
      const inRange: PerimeterCamera[] = []
      for (const c of geoCameras) {
        const d = distanceM(p.latitude, p.longitude, c.lat, c.lng)
        const dedicated = dedicatedSet.has(c.code)
        if (dedicated || d <= radius) inRange.push({ ...c, distance: d, dedicated })
      }
      inRange.sort((a, b) => Number(b.dedicated) - Number(a.dedicated) || a.distance - b.distance)
      const onMap = new Set(inRange.map((c) => c.code))
      const codes = new Set([...p.camera_codes, ...onMap])
      return {
        patrimonio: p,
        cameras: inRange,
        dedicatedWithoutCoords: p.camera_codes.filter((c) => !onMap.has(c)),
        alerts: recentAlerts.filter((a) => codes.has(a.camera_code)),
      }
    })
  }, [patrimonios, geoCameras, radius, alerts])

  const perimeterCodes = useMemo(() => {
    const s = new Set<string>()
    for (const p of perimeters) for (const c of p.cameras) s.add(c.code)
    return s
  }, [perimeters])

  const alertCodes = useMemo(() => {
    const s = new Set<string>()
    for (const p of perimeters) for (const a of p.alerts) s.add(a.camera_code)
    return s
  }, [perimeters])

  const selected = perimeters.find((p) => p.patrimonio.id === selectedId) ?? null
  const otherCameras = useMemo(
    () => geoCameras.filter((c) => !perimeterCodes.has(c.code)),
    [geoCameras, perimeterCodes]
  )
  // Câmeras do perímetro sem repetição (dois patrimônios próximos podem compartilhar)
  const perimeterCamerasUnique = useMemo(() => {
    const m = new Map<string, PerimeterCamera>()
    for (const p of perimeters) {
      for (const c of p.cameras) {
        const prev = m.get(c.code)
        if (!prev || (c.dedicated && !prev.dedicated)) m.set(c.code, c)
      }
    }
    return [...m.values()]
  }, [perimeters])

  const totals = {
    patrimonios: perimeters.filter((p) => p.patrimonio.camera_codes.length > 0).length,
    perimeterCams: perimeterCodes.size,
    alerts: perimeters.filter((p) => p.alerts.length > 0).length,
  }

  const monitorCodesFor = (p: Perimeter) => {
    const codes = [...p.cameras.map((c) => c.code), ...p.dedicatedWithoutCoords]
    // fixas primeiro (ordem já garantida), depois as mais próximas
    const unique = [...new Set([...p.patrimonio.camera_codes, ...codes])]
    return unique.slice(0, MAX_MONITOR_CAMERAS)
  }

  const patrimoniosForBounds = useMemo(() => patrimonios, [patrimonios])

  return (
    <div className="flex flex-col lg:flex-row gap-4 h-[calc(100vh-6rem)] sm:h-[calc(100vh-7rem)] min-h-[560px]">
      {/* ── Painel lateral ─────────────────────────────── */}
      <aside className="lg:w-96 flex-shrink-0 flex flex-col bg-white rounded-xl shadow-sm ring-1 ring-slate-200 overflow-hidden max-h-[45%] lg:max-h-none">
        <div className="p-4 border-b border-slate-100 space-y-4">
          <div className="grid grid-cols-3 gap-2 text-center">
            <Stat label="Patrimônios" value={totals.patrimonios} />
            <Stat label="Câm. no raio" value={totals.perimeterCams} />
            <Stat label="Em alerta" value={totals.alerts} tone={totals.alerts > 0 ? 'red' : 'default'} />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label htmlFor="raio" className="flex items-center gap-1.5 text-xs font-semibold text-slate-600">
                <Radar size={14} className="text-cor-blue" />
                Raio de vigilância
              </label>
              <span className="text-xs font-semibold text-cor-blue tabular-nums">{formatDistance(radius)}</span>
            </div>
            <input
              id="raio"
              type="range"
              min={100}
              max={1500}
              step={50}
              value={radius}
              onChange={(e) => setRadius(Number(e.target.value))}
              className="w-full accent-cor-blue"
            />
            <p className="mt-1 text-[11px] text-slate-400">
              Câmeras dentro do raio entram no perímetro para acompanhar a rota de um suspeito.
            </p>
          </div>

          <button
            onClick={() => setShowAllCameras((v) => !v)}
            className="w-full flex items-center justify-between text-xs text-slate-600 hover:text-slate-900"
          >
            <span className="flex items-center gap-1.5">
              {showAllCameras ? <Eye size={14} /> : <EyeOff size={14} />}
              Demais câmeras da cidade
            </span>
            <span className="text-slate-400">
              {showAllCameras ? 'visíveis' : 'ocultas'} · {otherCameras.length.toLocaleString('pt-BR')}
            </span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {loading && <p className="p-4 text-sm text-slate-500 text-center">Carregando…</p>}

          {!selected &&
            perimeters.map((p) => (
              <button
                key={p.patrimonio.id}
                onClick={() => setSelectedId(p.patrimonio.id)}
                className={`w-full text-left p-3 rounded-lg ring-1 transition-colors flex items-center gap-3 ${
                  p.alerts.length > 0
                    ? 'ring-red-200 bg-red-50 hover:bg-red-100'
                    : 'ring-slate-200 hover:bg-slate-50'
                }`}
              >
                <span className="text-2xl flex-shrink-0">{p.patrimonio.emoji}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-slate-800 truncate">{p.patrimonio.nome}</p>
                  <p className="text-xs text-slate-500 truncate">{p.patrimonio.bairro}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <Badge tone="gold">{p.patrimonio.camera_codes.length} fixa(s)</Badge>
                    <Badge tone="green">{p.cameras.filter((c) => !c.dedicated).length} no raio</Badge>
                    {p.alerts.length > 0 && (
                      <Badge tone="red">
                        {p.alerts.length} alerta(s)
                      </Badge>
                    )}
                  </div>
                </div>
                <ChevronRight size={16} className="text-slate-300 flex-shrink-0" />
              </button>
            ))}

          {selected && (
            <PerimeterDetail
              perimeter={selected}
              radius={radius}
              liveCodes={liveCodes}
              alertCodes={alertCodes}
              monitorCount={monitorCodesFor(selected).length}
              onBack={() => setSelectedId(null)}
              onMonitor={() => onMonitor(monitorCodesFor(selected))}
            />
          )}
        </div>
      </aside>

      {/* ── Mapa ───────────────────────────────────────── */}
      <div className="relative flex-1 min-h-[320px] rounded-xl overflow-hidden shadow-sm ring-1 ring-slate-200">
        <MapContainer center={RIO_CENTER} zoom={12} className="h-full w-full" scrollWheelZoom>
          <TileLayer
            // OpenStreetMap padrão: não exige chave (a CARTO passou a pedir API key)
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
          />
          <MapFocus target={selected?.patrimonio ?? null} radius={radius} all={patrimoniosForBounds} />

          {/* Demais câmeras (agrupadas — são milhares) */}
          {showAllCameras && (
            <MarkerClusterGroup
              chunkedLoading
              maxClusterRadius={50}
              spiderfyOnMaxZoom
              showCoverageOnHover={false}
              iconCreateFunction={(cluster: { getChildCount: () => number }) =>
                L.divIcon({
                  className: 'map-icon',
                  html: `<div class="map-cluster">${cluster.getChildCount()}</div>`,
                  iconSize: [32, 32],
                })
              }
            >
              {otherCameras.map((c) => (
                <Marker key={`cam-${c.code}`} position={[c.lat, c.lng]} icon={idleCameraIcon}>
                  <Popup>
                    <CameraPopup cam={c} />
                  </Popup>
                </Marker>
              ))}
            </MarkerClusterGroup>
          )}

          {/* Raios de vigilância */}
          {perimeters.map((p) => {
            const isSel = p.patrimonio.id === selectedId
            const inAlert = p.alerts.length > 0
            const color = inAlert ? '#dc2626' : isSel ? '#c9a84c' : '#1e3a5f'
            return (
              <Circle
                key={`raio-${p.patrimonio.id}-${radius}`}
                center={[p.patrimonio.latitude, p.patrimonio.longitude]}
                radius={radius}
                pathOptions={{
                  color,
                  weight: isSel || inAlert ? 2.5 : 1.5,
                  dashArray: isSel || inAlert ? undefined : '6 6',
                  fillColor: color,
                  fillOpacity: inAlert ? 0.14 : isSel ? 0.12 : 0.06,
                }}
                eventHandlers={{ click: () => setSelectedId(p.patrimonio.id) }}
              />
            )
          })}

          {/* Linhas do patrimônio selecionado até cada câmera do perímetro */}
          {selected &&
            selected.cameras.map((c) => (
              <Polyline
                key={`linha-${c.code}`}
                positions={[
                  [selected.patrimonio.latitude, selected.patrimonio.longitude],
                  [c.lat, c.lng],
                ]}
                pathOptions={{
                  color: c.dedicated ? '#c9a84c' : '#16a34a',
                  weight: 1.5,
                  opacity: 0.7,
                  dashArray: '4 4',
                }}
              />
            ))}

          {/* Câmeras do perímetro */}
          {perimeterCamerasUnique.map((c) => (
            <Marker
              key={`per-${c.code}`}
              position={[c.lat, c.lng]}
              icon={
                alertCodes.has(c.code)
                  ? perimeterIcons.alert
                  : c.dedicated
                    ? perimeterIcons.dedicated
                    : perimeterIcons.nearby
              }
              zIndexOffset={c.dedicated ? 500 : 300}
            >
              <Tooltip direction="top" offset={[0, -12]}>
                {c.code} · {c.name}
              </Tooltip>
              <Popup>
                <CameraPopup cam={c} live={liveCodes.has(c.code)} dedicated={c.dedicated} />
              </Popup>
            </Marker>
          ))}

          {/* Patrimônios */}
          {perimeters.map((p) => (
            <Marker
              key={`pat-${p.patrimonio.id}`}
              position={[p.patrimonio.latitude, p.patrimonio.longitude]}
              icon={patrimonyIcon(
                p.patrimonio.emoji,
                p.alerts.length > 0 ? 'alert' : p.patrimonio.id === selectedId ? 'selected' : 'normal'
              )}
              zIndexOffset={1000}
              eventHandlers={{ click: () => setSelectedId(p.patrimonio.id) }}
            >
              <Tooltip direction="top" offset={[0, -20]}>
                <strong>{p.patrimonio.nome}</strong> · {p.cameras.length} câmera(s) no perímetro
              </Tooltip>
            </Marker>
          ))}
        </MapContainer>

        {selected && (
          <button
            onClick={() => setSelectedId(null)}
            className="absolute top-3 right-3 z-[500] flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/95 shadow ring-1 ring-slate-200 text-xs font-medium text-slate-700 hover:bg-white"
          >
            <Crosshair size={14} /> Ver todos
          </button>
        )}

        <Legend />
      </div>
    </div>
  )
}

// ─── Componentes auxiliares ─────────────────────────────────────

function PerimeterDetail({
  perimeter,
  radius,
  liveCodes,
  alertCodes,
  monitorCount,
  onBack,
  onMonitor,
}: {
  perimeter: Perimeter
  radius: number
  liveCodes: Set<string>
  alertCodes: Set<string>
  monitorCount: number
  onBack: () => void
  onMonitor: () => void
}) {
  const { patrimonio: p, cameras, dedicatedWithoutCoords, alerts } = perimeter
  const nearbyCount = cameras.filter((c) => !c.dedicated).length

  return (
    <div className="space-y-3">
      <button onClick={onBack} className="text-xs text-slate-500 hover:text-slate-800">
        ← Todos os patrimônios
      </button>

      <div className="flex items-start gap-3">
        <span className="text-3xl">{p.emoji}</span>
        <div className="min-w-0">
          <p className="font-semibold text-slate-800 leading-tight">{p.nome}</p>
          <p className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
            <MapPin size={12} /> {p.bairro}
          </p>
          <p className="text-xs text-slate-400 mt-1">{p.descricao}</p>
        </div>
      </div>

      {alerts.length > 0 && (
        <div className="rounded-lg bg-red-50 ring-1 ring-red-200 p-3 space-y-1.5">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-red-700">
            <AlertTriangle size={14} /> Alertas nos últimos 30 min
          </p>
          {alerts.slice(0, 4).map((a) => (
            <p key={a.id} className="text-xs text-red-700/90">
              <span className="font-mono">{a.camera_code}</span> · {a.level} ·{' '}
              {new Date(a.timestamp * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
              <span className="block text-red-600/80 truncate">{a.message}</span>
            </p>
          ))}
        </div>
      )}

      <button
        onClick={onMonitor}
        disabled={monitorCount === 0}
        className="w-full py-2.5 rounded-lg bg-cor-blue text-white text-sm font-medium flex items-center justify-center gap-2 hover:bg-cor-blue-light disabled:opacity-40 transition-colors"
      >
        <Play size={16} />
        Monitorar perímetro ({monitorCount} câmera{monitorCount === 1 ? '' : 's'})
      </button>
      {cameras.length + dedicatedWithoutCoords.length > MAX_MONITOR_CAMERAS && (
        <p className="text-[11px] text-slate-400 -mt-1">
          Abre no máximo {MAX_MONITOR_CAMERAS} câmeras: entram as fixas e as mais próximas.
        </p>
      )}

      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
          Perímetro de {formatDistance(radius)} · {p.camera_codes.length} fixa(s), {nearbyCount} próxima(s)
        </p>
        <ul className="divide-y divide-slate-100 rounded-lg ring-1 ring-slate-200">
          {cameras.map((c) => (
            <li key={c.code} className="flex items-center gap-2.5 px-3 py-2">
              <span
                className={`grid place-items-center w-6 h-6 rounded-full flex-shrink-0 ${
                  alertCodes.has(c.code)
                    ? 'bg-red-100 text-red-600'
                    : c.dedicated
                      ? 'bg-amber-100 text-amber-700'
                      : 'bg-emerald-100 text-emerald-700'
                }`}
              >
                <CameraIcon size={12} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-slate-700 truncate">{c.name}</p>
                <p className="text-[11px] text-slate-400 font-mono">{c.code}</p>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-[11px] text-slate-500 tabular-nums">{formatDistance(c.distance)}</p>
                <div className="flex gap-1 justify-end">
                  {c.dedicated && <Badge tone="gold">fixa</Badge>}
                  {liveCodes.has(c.code) && <Badge tone="blue">ao vivo</Badge>}
                </div>
              </div>
            </li>
          ))}
          {dedicatedWithoutCoords.map((code) => (
            <li key={code} className="flex items-center gap-2.5 px-3 py-2">
              <span className="grid place-items-center w-6 h-6 rounded-full bg-amber-100 text-amber-700 flex-shrink-0">
                <CameraIcon size={12} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-slate-700">Câmera {code}</p>
                <p className="text-[11px] text-slate-400">sem coordenada na base</p>
              </div>
              <Badge tone="gold">fixa</Badge>
            </li>
          ))}
          {cameras.length === 0 && dedicatedWithoutCoords.length === 0 && (
            <li className="px-3 py-4 text-xs text-slate-500 text-center">
              Nenhuma câmera neste raio. Aumente o raio de vigilância.
            </li>
          )}
        </ul>
      </div>
    </div>
  )
}

function CameraPopup({ cam, live, dedicated }: { cam: GeoCamera; live?: boolean; dedicated?: boolean }) {
  return (
    <div className="min-w-[170px]">
      <p className="font-semibold text-slate-800">{cam.name}</p>
      <p className="text-xs text-slate-500 font-mono">{cam.code}</p>
      {cam.raw.endereco && <p className="text-xs text-slate-500 mt-1">{cam.raw.endereco}</p>}
      <div className="flex gap-1 mt-1.5">
        {dedicated && <Badge tone="gold">fixa do patrimônio</Badge>}
        {live && <Badge tone="blue">ao vivo</Badge>}
      </div>
    </div>
  )
}

function Stat({ label, value, tone = 'default' }: { label: string; value: number; tone?: 'default' | 'red' }) {
  return (
    <div className={`rounded-lg py-2 ${tone === 'red' ? 'bg-red-50' : 'bg-slate-50'}`}>
      <p className={`text-lg font-bold tabular-nums ${tone === 'red' ? 'text-red-600' : 'text-slate-800'}`}>
        {value}
      </p>
      <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
    </div>
  )
}

const badgeTones = {
  gold: 'bg-amber-100 text-amber-800',
  green: 'bg-emerald-100 text-emerald-800',
  red: 'bg-red-100 text-red-700',
  blue: 'bg-sky-100 text-sky-800',
}

function Badge({ tone, children }: { tone: keyof typeof badgeTones; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${badgeTones[tone]}`}>
      {children}
    </span>
  )
}

function Legend() {
  return (
    <div className="absolute bottom-3 left-3 z-[500] bg-white/95 backdrop-blur rounded-lg shadow ring-1 ring-slate-200 px-3 py-2 space-y-1 text-[11px] text-slate-600">
      <LegendRow swatch={<span className="map-legend-dot" style={{ background: '#1e3a5f', borderColor: '#fff' }} />}>
        Patrimônio monitorado
      </LegendRow>
      <LegendRow swatch={<span className="map-legend-dot" style={{ background: '#c9a84c' }} />}>Câmera fixa</LegendRow>
      <LegendRow swatch={<span className="map-legend-dot" style={{ background: '#16a34a' }} />}>
        Câmera no raio
      </LegendRow>
      <LegendRow swatch={<span className="map-legend-dot" style={{ background: '#dc2626' }} />}>Em alerta</LegendRow>
      <LegendRow swatch={<span className="map-legend-dot" style={{ background: '#94a3b8', width: 8, height: 8 }} />}>
        Outras câmeras
      </LegendRow>
    </div>
  )
}

function LegendRow({ swatch, children }: { swatch: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-3 flex justify-center">{swatch}</span>
      {children}
    </div>
  )
}
