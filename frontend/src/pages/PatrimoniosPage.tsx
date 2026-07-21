import { useState, useEffect, useCallback } from 'react'
import { Search, MapPin, Shield, Camera, Maximize2, Minimize2, AlertCircle, Wifi, WifiOff } from 'lucide-react'
import { api } from '../api/client'
import type { Patrimonio, Camera as CameraType } from '../types'

function CameraPlayer({ camera, patrimonioNome }: { camera: CameraType; patrimonioNome: string }) {
  const [live, setLive] = useState(false)
  const [error, setError] = useState(false)

  const streamUrl = camera.stream_url

  return (
    <div className="bg-black rounded-xl overflow-hidden border border-gray-700 flex flex-col">
      {/* Header do player */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 text-white text-sm">
        <div className="flex items-center gap-2">
          <span className="status-dot online animate-pulse" />
          <span className="font-medium">{camera.name || `Câmera ${camera.code}`}</span>
          {camera.code && (
            <span className="text-gray-400 text-xs">cód. {camera.code}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {live && <span className="text-xs text-red-400 font-medium">🔴 AO VIVO</span>}
        </div>
      </div>

      {/* Player - ocupa o máximo de espaço */}
      <div className="relative bg-black flex-1" style={{ minHeight: '480px' }}>
        {streamUrl ? (
          <>
            <iframe
              src={streamUrl}
              className="absolute inset-0 w-full h-full border-none"
              allow="accelerometer;autoplay;encrypted-media;gyroscope"
              allowFullScreen
              onLoad={() => setLive(true)}
              onError={() => setError(true)}
            />
            <div className="absolute bottom-3 left-3 flex items-center gap-2 z-10">
              <span className="bg-red-600 text-white text-xs px-3 py-1 rounded font-bold animate-pulse shadow-lg">
                {live ? '🔴 AO VIVO' : '⏳ CONECTANDO...'}
              </span>
              <span className="bg-black/70 text-white text-xs px-3 py-1 rounded shadow-lg">
                {patrimonioNome}
              </span>
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full min-h-[480px] text-gray-500">
            <div className="text-center">
              <AlertCircle size={48} className="mx-auto mb-3 opacity-50" />
              <p className="text-lg">Stream indisponível</p>
              <p className="text-sm text-gray-600 mt-2">
                Câmera {camera.code} sem URL de transmissão
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function PatrimoniosPage() {
  const [patrimonios, setPatrimonios] = useState<Patrimonio[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Patrimonio | null>(null)
  const [cameras, setCameras] = useState<CameraType[]>([])
  const [loadingCameras, setLoadingCameras] = useState(false)
  const [activeCameraIndex, setActiveCameraIndex] = useState(0)

  useEffect(() => {
    api.getPatrimonios().then((data) => {
      setPatrimonios(data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  // Quando seleciona um patrimônio, busca as câmeras associadas
  useEffect(() => {
    if (!selected || selected.camera_codes.length === 0) {
      setCameras([])
      return
    }

    setLoadingCameras(true)
    setActiveCameraIndex(0)
    api.getCamerasByCodes(selected.camera_codes)
      .then(setCameras)
      .catch(() => setCameras([]))
      .finally(() => setLoadingCameras(false))
  }, [selected])

  const filtered = patrimonios.filter(
    (p) =>
      p.nome.toLowerCase().includes(search.toLowerCase()) ||
      p.bairro.toLowerCase().includes(search.toLowerCase()) ||
      p.categoria.toLowerCase().includes(search.toLowerCase())
  )

  const activeCamera = cameras[activeCameraIndex]

  return (
    <div className="flex gap-6 h-full">
      {/* Lista de Patrimônios */}
      <div className="w-80 flex-shrink-0 space-y-4">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Buscar patrimônio..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cor-blue/20 focus:border-cor-blue"
          />
        </div>

        <div className="space-y-2 overflow-y-auto max-h-[calc(100vh-220px)]">
          {filtered.map((p) => (
            <button
              key={p.id}
              onClick={() => setSelected(p)}
              className={`w-full text-left p-3 rounded-xl border transition-all ${
                selected?.id === p.id
                  ? 'border-cor-blue bg-blue-50 shadow-sm ring-1 ring-cor-blue/20'
                  : 'border-gray-100 bg-white hover:border-gray-200 hover:shadow-sm'
              }`}
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">{p.emoji}</span>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-800 truncate text-sm">{p.nome}</p>
                  <p className="text-xs text-gray-500 truncate">{p.bairro}</p>
                </div>
              </div>
              <div className="mt-1.5 flex items-center gap-3 text-xs text-gray-400">
                <span className="flex items-center gap-1">
                  <MapPin size={11} />
                  {p.latitude.toFixed(4)}, {p.longitude.toFixed(4)}
                </span>
                <span className="flex items-center gap-1">
                  <Camera size={11} />
                  {p.camera_codes.length}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Detalhes + Câmera ao Vivo */}
      <div className="flex-1 flex flex-col space-y-3 overflow-y-auto">
        {selected ? (
          <>
            {/* Cabeçalho compacto + Seletor de câmeras */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex items-center gap-4">
              <span className="text-3xl">{selected.emoji}</span>
              <div className="flex-1 min-w-0">
                <h2 className="text-lg font-bold text-gray-800 truncate">{selected.nome}</h2>
                <p className="text-xs text-gray-500 truncate">{selected.descricao}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="status-dot online" />
                <span className="text-xs text-green-600 font-medium">Monitorado</span>
              </div>
            </div>

            {/* Câmera ao Vivo - ocupa a maior parte da tela */}
            {selected.camera_codes.length > 0 ? (
              <div className="flex flex-col space-y-2 flex-1">
                {/* Seletor de câmeras */}
                {cameras.length > 1 && (
                  <div className="flex gap-2 flex-wrap">
                    {cameras.map((cam, idx) => (
                      <button
                        key={idx}
                        onClick={() => setActiveCameraIndex(idx)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all border ${
                          idx === activeCameraIndex
                            ? 'bg-red-50 border-red-200 text-red-700'
                            : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300'
                        }`}
                      >
                        <span className="status-dot online mr-1.5 inline-block" />
                        {cam.name || `Câmera ${cam.code || idx + 1}`}
                      </button>
                    ))}
                  </div>
                )}

                {/* Player - ocupa o máximo */}
                {loadingCameras ? (
                  <div className="bg-gray-900 rounded-xl flex items-center justify-center flex-1 min-h-[480px]">
                    <div className="text-center text-gray-400">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white mx-auto mb-3" />
                      <p className="text-sm">Conectando à câmera...</p>
                    </div>
                  </div>
                ) : activeCamera ? (
                  <div className="flex-1 min-h-[480px]">
                    <CameraPlayer
                      camera={activeCamera}
                      patrimonioNome={selected.nome}
                    />
                  </div>
                ) : (
                  <div className="bg-gray-100 rounded-xl flex items-center justify-center flex-1 min-h-[200px]">
                    <div className="text-center text-gray-400">
                      <AlertCircle size={32} className="mx-auto mb-2 opacity-50" />
                      <p className="text-sm">Nenhuma câmera encontrada para este patrimônio</p>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-gray-100 rounded-xl flex items-center justify-center flex-1 min-h-[300px]">
                <div className="text-center text-gray-400">
                  <Camera size={48} className="mx-auto mb-3 opacity-50" />
                  <p className="text-lg font-medium">Sem câmeras associadas</p>
                  <p className="text-sm">Este patrimônio não possui câmeras de monitoramento</p>
                </div>
              </div>
            )}

            {/* Info Cards - barra compacta no final */}
            <div className="grid grid-cols-4 gap-2">
              <div className="bg-white rounded-lg border border-gray-100 p-2.5">
                <p className="text-[10px] text-gray-500 mb-0.5">Bairro</p>
                <p className="font-medium text-gray-800 text-xs truncate">{selected.bairro}</p>
              </div>
              <div className="bg-white rounded-lg border border-gray-100 p-2.5">
                <p className="text-[10px] text-gray-500 mb-0.5">Coordenadas</p>
                <p className="font-medium text-gray-800 text-[10px] truncate">
                  {selected.latitude.toFixed(4)}, {selected.longitude.toFixed(4)}
                </p>
              </div>
              <div className="bg-white rounded-lg border border-gray-100 p-2.5">
                <p className="text-[10px] text-gray-500 mb-0.5">Câmeras</p>
                <p className="font-medium text-gray-800 text-xs truncate">
                  {cameras.length > 0
                    ? cameras.map(c => c.code).join(', ')
                    : (selected.camera_codes.length > 0 ? 'Carregando...' : 'Nenhuma')}
                </p>
              </div>
              <div className="bg-white rounded-lg border border-gray-100 p-2.5">
                <p className="text-[10px] text-gray-500 mb-0.5">Categoria</p>
                <p className="font-medium text-gray-800 text-[10px] truncate">{selected.categoria}</p>
              </div>
            </div>
          </>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 flex items-center justify-center h-full">
            <div className="text-center text-gray-400">
              <Shield size={48} className="mx-auto mb-3 opacity-50" />
              <p className="text-lg font-medium">Selecione um patrimônio</p>
              <p className="text-sm">Para ver a câmera ao vivo e informações de monitoramento</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
