import {
  LayoutDashboard,
  Landmark,
  Map,
  ShieldAlert,
  Info,
  Camera,
  ChevronsLeft,
  ChevronsRight,
  X,
} from 'lucide-react'
import type { Page } from '../types'
import corTexto from '../assets/cor-texto-branco.png'
import corBrasao from '../assets/cor-brasao-branco.png'

interface NavItem {
  id: Page
  label: string
  icon: React.ReactNode
}

const navSections: { title: string; items: NavItem[] }[] = [
  {
    title: 'Visão geral',
    items: [
      { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={19} /> },
      { id: 'patrimonios', label: 'Patrimônios', icon: <Landmark size={19} /> },
      { id: 'mapa', label: 'Mapa', icon: <Map size={19} /> },
    ],
  },
  {
    title: 'Operação',
    items: [
      { id: 'monitoramento', label: 'Monitoramento', icon: <Camera size={19} /> },
      { id: 'vandalismo', label: 'Antivandalismo', icon: <ShieldAlert size={19} /> },
    ],
  },
  {
    title: 'Sistema',
    items: [{ id: 'sobre', label: 'Sobre', icon: <Info size={19} /> }],
  },
]

interface Props {
  currentPage: Page
  onNavigate: (page: Page) => void
  /** Sidebar visível (desktop: não oculta; mobile: gaveta aberta) */
  visible: boolean
  /** Modo compacto, só ícones (apenas desktop) */
  collapsed: boolean
  isMobile: boolean
  onToggleCollapse: () => void
  onClose: () => void
}

export default function Sidebar({
  currentPage,
  onNavigate,
  visible,
  collapsed,
  isMobile,
  onToggleCollapse,
  onClose,
}: Props) {
  const expanded = !collapsed
  const width = collapsed ? 'w-[4.5rem]' : 'w-64'

  // Desktop: a largura anima até 0 ao ocultar. Mobile: gaveta deslizante sobre o conteúdo.
  const containerClass = isMobile
    ? `fixed inset-y-0 left-0 z-50 w-64 shadow-2xl transform transition-transform duration-300 ${
        visible ? 'translate-x-0' : '-translate-x-full'
      }`
    : `relative flex-shrink-0 overflow-hidden transition-[width] duration-300 ${visible ? width : 'w-0'}`

  return (
    <>
      {isMobile && (
        <div
          className={`fixed inset-0 z-40 bg-slate-900/60 backdrop-blur-sm transition-opacity duration-300 ${
            visible ? 'opacity-100' : 'opacity-0 pointer-events-none'
          }`}
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside className={containerClass} aria-hidden={!visible}>
        <div
          className={`h-full flex flex-col text-white bg-gradient-to-b from-cor-dark via-[#101c33] to-cor-blue/90 ${
            isMobile ? 'w-64' : width
          }`}
        >
          {/* Marca da aplicação */}
          <div
            className={`flex items-center h-16 px-4 border-b border-white/10 ${
              expanded ? 'justify-between' : 'justify-center'
            }`}
          >
            {expanded && (
              <div className="flex items-center gap-3 min-w-0">
                <div className="grid place-items-center w-9 h-9 rounded-lg bg-cor-gold/15 ring-1 ring-cor-gold/40 text-cor-gold flex-shrink-0">
                  <Landmark size={18} />
                </div>
                <div className="min-w-0 leading-tight">
                  <p className="text-sm font-semibold tracking-tight">Visão Patrimônios</p>
                  <p className="text-[11px] text-slate-400">Monitoramento inteligente</p>
                </div>
              </div>
            )}
            {isMobile ? (
              <button
                onClick={onClose}
                className="p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                title="Fechar menu"
                aria-label="Fechar menu"
              >
                <X size={18} />
              </button>
            ) : (
              <button
                onClick={onToggleCollapse}
                className="p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                title={collapsed ? 'Expandir' : 'Recolher'}
                aria-label={collapsed ? 'Expandir menu' : 'Recolher menu'}
              >
                {collapsed ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}
              </button>
            )}
          </div>

          {/* Navegação */}
          <nav className="flex-1 py-4 px-3 overflow-y-auto sidebar-scroll space-y-5">
            {navSections.map((section) => (
              <div key={section.title}>
                {expanded ? (
                  <p className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                    {section.title}
                  </p>
                ) : (
                  <div className="mx-auto mb-2 h-px w-6 bg-white/10" />
                )}
                <div className="space-y-1">
                  {section.items.map((item) => {
                    const active = currentPage === item.id
                    return (
                      <button
                        key={item.id}
                        onClick={() => onNavigate(item.id)}
                        className={`group relative w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
                          ${expanded ? '' : 'justify-center'}
                          ${
                            active
                              ? 'bg-white/10 text-white'
                              : 'text-slate-400 hover:bg-white/5 hover:text-white'
                          }
                        `}
                        title={item.label}
                        aria-current={active ? 'page' : undefined}
                      >
                        {active && (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r-full bg-cor-gold" />
                        )}
                        <span
                          className={`flex-shrink-0 transition-colors ${
                            active ? 'text-cor-gold' : 'group-hover:text-white'
                          }`}
                        >
                          {item.icon}
                        </span>
                        {expanded && <span className="truncate">{item.label}</span>}
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </nav>

          {/* Rodapé: identidade do COR com a tipografia oficial da logo */}
          <div className="border-t border-white/10 p-4">
            {expanded ? (
              <div className="flex items-center gap-3">
                <img
                  src={corBrasao}
                  alt=""
                  className="h-11 w-auto flex-shrink-0 opacity-90 select-none"
                  draggable={false}
                />
                <span className="h-10 w-px bg-white/25 flex-shrink-0" />
                <img
                  src={corTexto}
                  alt="Centro de Operações e Resiliência"
                  className="h-11 w-auto select-none"
                  draggable={false}
                />
              </div>
            ) : (
              <img
                src={corBrasao}
                alt="Centro de Operações e Resiliência"
                title="Centro de Operações e Resiliência"
                className="mx-auto h-9 w-auto opacity-90 select-none"
                draggable={false}
              />
            )}
          </div>
        </div>
      </aside>
    </>
  )
}
