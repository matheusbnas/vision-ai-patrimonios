import { useState, useEffect, useCallback } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import DashboardPage from './pages/DashboardPage'
import PatrimoniosPage from './pages/PatrimoniosPage'
import MapaPage from './pages/MapaPage'
import MonitoramentoPage from './pages/MonitoramentoPage'
import VandalismoPage from './pages/VandalismoPage'
import SobrePage from './pages/SobrePage'
import type { Page } from './types'

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>('dashboard')
  const isMobile = useIsMobile()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => readPref('sidebar:collapsed', false))
  const [sidebarHidden, setSidebarHidden] = useState(() => readPref('sidebar:hidden', false))
  // No mobile a sidebar é uma gaveta sobreposta, sempre começa fechada
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => writePref('sidebar:collapsed', sidebarCollapsed), [sidebarCollapsed])
  useEffect(() => writePref('sidebar:hidden', sidebarHidden), [sidebarHidden])
  useEffect(() => {
    if (!isMobile) setMobileOpen(false)
  }, [isMobile])

  const toggleSidebar = useCallback(() => {
    if (isMobile) setMobileOpen((v) => !v)
    else setSidebarHidden((v) => !v)
  }, [isMobile])

  // Atalho Ctrl/Cmd + B para abrir/ocultar
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        toggleSidebar()
      }
      if (e.key === 'Escape') setMobileOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggleSidebar])

  const handleNavigate = (page: Page) => {
    setCurrentPage(page)
    if (isMobile) setMobileOpen(false)
  }

  const sidebarVisible = isMobile ? mobileOpen : !sidebarHidden

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <DashboardPage />
      case 'patrimonios':
        return <PatrimoniosPage />
      case 'mapa':
        return <MapaPage />
      case 'vandalismo':
        return <VandalismoPage />
      case 'monitoramento':
        return <MonitoramentoPage />
      case 'sobre':
        return <SobrePage />
      default:
        return <DashboardPage />
    }
  }

  return (
    <div className="flex h-screen bg-slate-100">
      <Sidebar
        currentPage={currentPage}
        onNavigate={handleNavigate}
        visible={sidebarVisible}
        collapsed={!isMobile && sidebarCollapsed}
        isMobile={isMobile}
        onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
        onClose={() => (isMobile ? setMobileOpen(false) : setSidebarHidden(true))}
      />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Header
          currentPage={currentPage}
          sidebarVisible={sidebarVisible}
          onToggleSidebar={toggleSidebar}
          onOpenMonitoramento={() => setCurrentPage('monitoramento')}
        />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6">
          {renderPage()}
        </main>
      </div>
    </div>
  )
}

function useIsMobile(query = '(max-width: 1023px)') {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mql = window.matchMedia(query)
    const onChange = () => setMatches(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])
  return matches
}

function readPref(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    return v === null ? fallback : v === '1'
  } catch {
    return fallback
  }
}

function writePref(key: string, value: boolean) {
  try {
    localStorage.setItem(key, value ? '1' : '0')
  } catch {
    // ignora (modo privado / storage bloqueado)
  }
}
