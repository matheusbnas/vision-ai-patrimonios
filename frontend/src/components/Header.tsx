import { useState, useEffect } from 'react'
import { Menu, Wifi, WifiOff, Activity } from 'lucide-react'
import { api } from '../api/client'
import type { Page } from '../types'

const pageTitles: Record<Page, string> = {
  dashboard: 'Dashboard',
  patrimonios: 'Patrimônios Monitorados',
  mapa: 'Mapa de Câmeras',
  monitoramento: 'Monitoramento ao Vivo',
  analise: 'Análise por Região',
  sobre: 'Sobre o Sistema',
}

interface Props {
  currentPage: Page
  onToggleSidebar: () => void
}

export default function Header({ currentPage, onToggleSidebar }: Props) {
  const [online, setOnline] = useState(false)
  const [modelsStatus, setModelsStatus] = useState<Record<string, boolean>>({})
  const [showModels, setShowModels] = useState(false)

  useEffect(() => {
    const check = async () => {
      try {
        const health = await api.health()
        setOnline(health.status === 'online')
        if (health.models) {
          setModelsStatus(health.models)
        }
      } catch {
        setOnline(false)
      }
    }
    check()
    const interval = setInterval(check, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <button
          onClick={onToggleSidebar}
          className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
        >
          <Menu size={20} className="text-gray-600" />
        </button>
        <h1 className="text-lg font-semibold text-gray-800">
          {pageTitles[currentPage]}
        </h1>
      </div>

      <div className="flex items-center gap-4">
        {/* Status dos Modelos */}
        <div className="relative">
          <button
            onClick={() => setShowModels(!showModels)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors text-sm"
          >
            <Activity size={16} className="text-cor-blue" />
            <span className="text-gray-600">Modelos</span>
          </button>

          {showModels && (
            <div className="absolute right-0 top-full mt-2 w-64 bg-white rounded-lg shadow-lg border border-gray-200 p-3 z-50">
              <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">
                Modelos de IA
              </h3>
              {Object.entries(modelsStatus).map(([name, loaded]) => (
                <div key={name} className="flex items-center justify-between py-1">
                  <span className="text-sm text-gray-700">{name}</span>
                  <span
                    className={`status-dot ${loaded ? 'online' : 'offline'}`}
                    title={loaded ? 'Carregado' : 'Não carregado'}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Status da API */}
        <div className="flex items-center gap-1.5">
          {online ? (
            <>
              <Wifi size={16} className="text-green-500" />
              <span className="text-xs text-green-600 font-medium">Online</span>
            </>
          ) : (
            <>
              <WifiOff size={16} className="text-red-500" />
              <span className="text-xs text-red-600 font-medium">Offline</span>
            </>
          )}
        </div>

        {/* Logo CO-RIO */}
        <div className="text-right">
          <p className="text-xs font-semibold text-cor-blue">CO-RIO</p>
          <p className="text-[10px] text-gray-400">Patrimônios</p>
        </div>
      </div>
    </header>
  )
}
