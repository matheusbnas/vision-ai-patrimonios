import { useState, useEffect } from 'react'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import L from 'leaflet'
import { api } from '../api/client'
import type { Patrimonio } from '../types'

// Ícone personalizado para patrimônios
const patrimonyIcon = new L.DivIcon({
  className: 'custom-marker',
  html: '<div style="background:#1e3a5f;color:white;padding:4px 8px;border-radius:20px;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,0.3);border:2px solid #c9a84c;">🏛️</div>',
  iconSize: [30, 30],
  iconAnchor: [15, 15],
})

const cameraIcon = new L.DivIcon({
  className: 'custom-marker',
  html: '<div style="background:#dc2626;color:white;padding:4px 8px;border-radius:20px;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,0.3);">📹</div>',
  iconSize: [30, 30],
  iconAnchor: [15, 15],
})

export default function MapaPage() {
  const [patrimonios, setPatrimonios] = useState<Patrimonio[]>([])
  const [cameras, setCameras] = useState<any[]>([])
  const [center] = useState<[number, number]>([-22.9068, -43.1729])

  useEffect(() => {
    Promise.all([
      api.getPatrimonios(),
      api.getCameras().catch(() => []),
    ]).then(([p, c]) => {
      setPatrimonios(p)
      setCameras(c)
    })
  }, [])

  return (
    <div className="h-[calc(100vh-130px)] rounded-xl overflow-hidden shadow-sm border border-gray-200">
      <MapContainer
        center={center}
        zoom={11}
        className="h-full w-full"
        scrollWheelZoom={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Marcadores de Patrimônios */}
        {patrimonios.map((p) => (
          <Marker
            key={`pat-${p.id}`}
            position={[p.latitude, p.longitude]}
            icon={patrimonyIcon}
          >
            <Popup>
              <div className="text-center min-w-[150px]">
                <p className="text-2xl mb-1">{p.emoji}</p>
                <p className="font-bold text-gray-800">{p.nome}</p>
                <p className="text-xs text-gray-500">{p.bairro}</p>
                <p className="text-xs text-gray-400 mt-1">{p.categoria}</p>
              </div>
            </Popup>
          </Marker>
        ))}

        {/* Marcadores de Câmeras */}
        {cameras
          .filter((c) => c.latitude && c.longitude)
          .map((c, i) => (
            <Marker
              key={`cam-${i}`}
              position={[c.latitude, c.longitude]}
              icon={cameraIcon}
            >
              <Popup>
                <div className="min-w-[150px]">
                  <p className="font-bold text-gray-800">{c.name || c.code || `Câmera #${c.id}`}</p>
                  <p className="text-xs text-gray-500">{c.localizacao || `${c.latitude?.toFixed(4)}, ${c.longitude?.toFixed(4)}`}</p>
                  {c.stream_url && (
                    <p className="text-xs text-blue-500 mt-1">📹 Link disponível</p>
                  )}
                </div>
              </Popup>
            </Marker>
          ))}
      </MapContainer>
    </div>
  )
}
