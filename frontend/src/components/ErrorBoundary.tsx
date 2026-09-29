import { Component, type ReactNode } from 'react'
import { AlertTriangle, RotateCcw } from 'lucide-react'

interface Props {
  children: ReactNode
  /** Quando muda (ex.: página atual), limpa o erro e tenta renderizar de novo */
  resetKey?: unknown
}

interface State {
  error: Error | null
}

/**
 * Erro de renderização numa página não pode derrubar o app inteiro
 * (tela em branco): mostra o erro no lugar da página e mantém
 * header/sidebar funcionando.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    console.error('Erro ao renderizar a página:', error, info.componentStack)
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="max-w-xl mx-auto mt-12 bg-white rounded-xl ring-1 ring-red-200 p-6 text-center">
        <AlertTriangle size={36} className="mx-auto mb-3 text-red-500" />
        <p className="font-semibold text-slate-800">Esta tela encontrou um erro</p>
        <p className="mt-1 text-sm text-slate-500">
          O restante do sistema continua funcionando. Tente de novo ou volte para outra página.
        </p>
        <p className="mt-3 text-xs font-mono text-red-600 bg-red-50 rounded p-2 break-words">
          {this.state.error.message}
        </p>
        <button
          onClick={() => this.setState({ error: null })}
          className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-cor-blue text-white text-sm hover:bg-cor-blue-light"
        >
          <RotateCcw size={14} /> Tentar de novo
        </button>
      </div>
    )
  }
}
