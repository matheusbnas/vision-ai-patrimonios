import { useState, useEffect, useRef } from 'react'
import { PanelLeftClose, PanelLeftOpen, Cpu, ChevronDown } from 'lucide-react'
import { api } from '../api/client'
import type { Page } from '../types'
import AlertNotifier from './AlertNotifier'
import LiveClock from './LiveClock'
import logoCor from '../assets/logo-cor-branco.png'

const pageTitles: Record<Page, string> = {
  dashboard: 'Dashboard',
  patrimonios: 'Patrimônios Monitorados',
  mapa: 'Mapa de Câmeras',
  detector: 'Detector de Objetos',
  vandalismo: 'Antivandalismo',
  monitoramento: 'Monitoramento ao Vivo',
  analise: 'Análise por Região',
  sobre: 'Sobre o Sistema',
}

interface Props {
  currentPage: Page
  sidebarVisible: boolean
  onToggleSidebar: () => void
  onOpenMonitoramento: () => void
}

export default function Header({ currentPage, sidebarVisible, onToggleSidebar, onOpenMonitoramento }: Props) {
  const [online, setOnline] = useState(false)
  const [modelsStatus, setModelsStatus] = useState<Record<string, boolean>>({})
  const [showModels, setShowModels] = useState(false)
  const modelsRef = useRef<HTMLDivElement>(null)

  // Fecha o popover de modelos ao clicar fora
  useEffect(() => {
    if (!showModels) return
    const onDown = (e: MouseEvent) => {
      if (!modelsRef.current?.contains(e.target as Node)) setShowModels(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [showModels])

  const modelEntries = Object.entries(modelsStatus)
  const modelsLoaded = modelEntries.filter(([, loaded]) => loaded).length

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
    <header className="h-16 flex-shrink-0 bg-white/80 backdrop-blur border-b border-slate-200 px-4 sm:px-6 flex items-center justify-between gap-4 relative z-30">
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onToggleSidebar}
          className="p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
          title={`${sidebarVisible ? 'Ocultar' : 'Mostrar'} menu (Ctrl+B)`}
          aria-label={sidebarVisible ? 'Ocultar menu' : 'Mostrar menu'}
          aria-expanded={sidebarVisible}
        >
          {sidebarVisible ? <PanelLeftClose size={20} /> : <PanelLeftOpen size={20} />}
        </button>
        <span className="hidden sm:block h-6 w-px bg-slate-200" />
        <div className="min-w-0 leading-tight">
          <p className="hidden sm:block text-[11px] font-medium uppercase tracking-wider text-slate-400">
            Visão Patrimônios
          </p>
          <h1 className="text-base sm:text-lg font-semibold text-slate-800 truncate">
            {pageTitles[currentPage]}
          </h1>
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
        {/* Data e hora oficial (Brasília) — referência para os horários das câmeras */}
        <LiveClock />

        {/* Status da API */}
        <div
          className={`hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ring-1 ${
            online
              ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
              : 'bg-red-50 text-red-700 ring-red-200'
          }`}
          title={online ? 'API online' : 'API offline'}
        >
          <span className="relative flex h-2 w-2">
            {online && (
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
            )}
            <span
              className={`relative inline-flex h-2 w-2 rounded-full ${online ? 'bg-emerald-500' : 'bg-red-500'}`}
            />
          </span>
          {online ? 'Online' : 'Offline'}
        </div>

        {/* Status dos Modelos */}
        <div className="relative" ref={modelsRef}>
          <button
            onClick={() => setShowModels(!showModels)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50 transition-colors"
            aria-expanded={showModels}
          >
            <Cpu size={14} className="text-cor-blue" />
            <span className="hidden md:inline">Modelos</span>
            {modelEntries.length > 0 && (
              <span className="text-slate-400">
                {modelsLoaded}/{modelEntries.length}
              </span>
            )}
            <ChevronDown size={14} className={`transition-transform ${showModels ? 'rotate-180' : ''}`} />
          </button>

          {showModels && (
            <div className="absolute right-0 top-full mt-2 w-64 bg-white rounded-xl shadow-xl ring-1 ring-slate-200 p-2 z-50">
              <h3 className="px-2 pt-1 pb-2 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Modelos de IA
              </h3>
              {modelEntries.length === 0 && (
                <p className="px-2 pb-2 text-sm text-slate-500">Sem informações da API.</p>
              )}
              {modelEntries.map(([name, loaded]) => (
                <div
                  key={name}
                  className="flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-slate-50"
                >
                  <span className="text-sm text-slate-700">{name}</span>
                  <span
                    className={`text-[11px] font-medium ${loaded ? 'text-emerald-600' : 'text-slate-400'}`}
                  >
                    {loaded ? 'Carregado' : 'Não carregado'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Sino de alertas (som + contador; lista ao clicar) */}
        <AlertNotifier onOpenMonitoramento={onOpenMonitoramento} />

        {/* Logo COR (versão monocromática branca sobre fundo escuro) */}
        <div className="hidden lg:flex items-center h-10 px-3 rounded-lg bg-gradient-to-r from-cor-dark to-cor-blue shadow-sm">
          <img
            src={logoCor}
            alt="Prefeitura Rio - Centro de Operações e Resiliência"
            className="h-7 w-auto select-none"
            draggable={false}
          />
        </div>
      </div>
    </header>
  )
}
