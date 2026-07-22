import { useMemo } from 'react'
import {
  LayoutDashboard,
  Landmark,
  Map,
  ShieldAlert,
  Info,
  Camera,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import type { Page } from '../types'

interface NavItem {
  id: Page
  label: string
  icon: React.ReactNode
}

const navItems: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
  { id: 'patrimonios', label: 'Patrimônios', icon: <Landmark size={20} /> },
  { id: 'mapa', label: 'Mapa', icon: <Map size={20} /> },
  { id: 'vandalismo', label: 'Antivandalismo', icon: <ShieldAlert size={20} /> },
  { id: 'monitoramento', label: 'Monitoramento', icon: <Camera size={20} /> },
  { id: 'sobre', label: 'Sobre', icon: <Info size={20} /> },
]

interface Props {
  currentPage: Page
  onNavigate: (page: Page) => void
  isOpen: boolean
  onToggle: () => void
}

export default function Sidebar({ currentPage, onNavigate, isOpen, onToggle }: Props) {
  return (
    <aside
      className={`bg-cor-dark text-white flex flex-col transition-all duration-300 ${
        isOpen ? 'w-64' : 'w-16'
      }`}
    >
      {/* Logo */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        {isOpen && (
          <div className="flex items-center gap-2">
            <span className="text-2xl">🏛️</span>
            <div>
              <h1 className="text-sm font-bold leading-tight">Visão</h1>
              <h2 className="text-xs text-cor-gold leading-tight">Patrimônios</h2>
            </div>
          </div>
        )}
        <button
          onClick={onToggle}
          className="p-1 rounded hover:bg-gray-700 transition-colors"
          title={isOpen ? 'Recolher' : 'Expandir'}
        >
          {isOpen ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}
        </button>
      </div>

      {/* Navegação */}
      <nav className="flex-1 py-4 space-y-1 px-2">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all text-sm font-medium
              ${
                currentPage === item.id
                  ? 'bg-cor-blue text-white shadow-lg'
                  : 'text-gray-300 hover:bg-gray-700 hover:text-white'
              }
            `}
            title={item.label}
          >
            <span className="flex-shrink-0">{item.icon}</span>
            {isOpen && <span>{item.label}</span>}
          </button>
        ))}
      </nav>

      {/* Footer */}
      {isOpen && (
        <div className="p-4 border-t border-gray-700 text-xs text-gray-400">
          <p>CO-RIO</p>
          <p>Coord. de Operações e Resiliência</p>
        </div>
      )}
    </aside>
  )
}
