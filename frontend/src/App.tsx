import { useState } from 'react'
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
  const [sidebarOpen, setSidebarOpen] = useState(true)

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
    <div className="flex h-screen bg-gray-50">
      <Sidebar
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
      />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header
          currentPage={currentPage}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        />
        <main className="flex-1 overflow-y-auto p-6">
          {renderPage()}
        </main>
      </div>
    </div>
  )
}
