import { formatDate, formatTime, useNow } from './LiveClock'

export type CameraClockMode = 'live-analysis' | 'player' | 'snapshot'
export type CameraClockTone = 'green' | 'amber' | 'red' | 'gray'

export interface CameraClockStatus {
  /** Instante da imagem exibida (ms) — null quando não se sabe */
  ts: number | null
  label: string
  tone: CameraClockTone
  /** Explicação curta para o title (hover) */
  hint: string
}

interface StatusInput {
  mode: CameraClockMode
  now: number
  /** Instante da imagem exibida (ms) */
  imageTs?: number | null
  /** Ciclo de monitoramento rodando (modo print) */
  running?: boolean
  /** Player / captura falhou */
  error?: boolean
  /** Último ciclo não conseguiu capturar a câmera (mantém o print anterior) */
  captureFailed?: boolean
}

// Ciclo de print é de 10s, mas com várias câmeras (Playwright captura uma por
// vez) o ciclo real passa disso — 45s ainda é "em dia".
const SNAPSHOT_FRESH_MS = 45_000
const SNAPSHOT_LATE_MS = 3 * 60_000
const LIVE_FRESH_MS = 6_000
const LIVE_LATE_MS = 30_000

function ago(ms: number) {
  const s = Math.max(0, Math.round(ms / 1000))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}`
}

export function cameraClockStatus({ mode, now, imageTs, running, error, captureFailed }: StatusInput): CameraClockStatus {
  const ts = imageTs ?? null

  if (mode === 'player') {
    if (error) return { ts: null, label: 'SEM SINAL', tone: 'red', hint: 'O player da câmera não carregou' }
    return { ts: now, label: 'TRANSMISSÃO', tone: 'green', hint: 'Vídeo direto da câmera (horário atual)' }
  }

  if (mode === 'live-analysis') {
    if (ts == null) return { ts: null, label: 'SEM SINAL', tone: 'red', hint: 'Sem análise recente do servidor' }
    const age = now - ts
    if (age <= LIVE_FRESH_MS) return { ts, label: 'AO VIVO', tone: 'green', hint: 'Análise contínua em dia' }
    if (age <= LIVE_LATE_MS) return { ts, label: `ATRASO ${ago(age)}`, tone: 'amber', hint: 'Análise contínua atrasada' }
    return { ts, label: 'SEM SINAL', tone: 'red', hint: `Última imagem há ${ago(age)}` }
  }

  // Modo print (ciclo de captura + IA)
  if (ts == null) {
    if (error || captureFailed) return { ts: null, label: 'FALHA NA CAPTURA', tone: 'red', hint: 'Não foi possível capturar a câmera' }
    return running
      ? { ts: null, label: 'CAPTURANDO…', tone: 'gray', hint: 'Aguardando o primeiro print' }
      : { ts: null, label: 'AGUARDANDO', tone: 'gray', hint: 'Monitoramento não iniciado' }
  }
  const age = now - ts
  if (captureFailed) return { ts, label: `FALHA · há ${ago(age)}`, tone: 'red', hint: 'Último ciclo falhou; exibindo o print anterior' }
  if (!running) return { ts, label: `PAUSADO · há ${ago(age)}`, tone: 'gray', hint: 'Monitoramento parado; print antigo' }
  if (age <= SNAPSHOT_FRESH_MS) return { ts, label: `MONITORANDO · há ${ago(age)}`, tone: 'green', hint: 'Print atualizado' }
  if (age <= SNAPSHOT_LATE_MS) return { ts, label: `ATRASADO · há ${ago(age)}`, tone: 'amber', hint: 'Ciclo de captura mais lento que o normal' }
  return { ts, label: `DESATUALIZADO · há ${ago(age)}`, tone: 'red', hint: 'Câmera sem print novo há muito tempo' }
}

export const toneDot: Record<CameraClockTone, string> = {
  green: 'bg-emerald-400',
  amber: 'bg-amber-400',
  red: 'bg-red-500',
  gray: 'bg-slate-400',
}

const toneChip: Record<CameraClockTone, string> = {
  green: 'bg-emerald-500/90 text-white',
  amber: 'bg-amber-400 text-black',
  red: 'bg-red-600 text-white',
  gray: 'bg-slate-500/90 text-white',
}

/** Selo de data/hora sobre a imagem da câmera (estilo OSD de CFTV) */
export default function CameraClock({ status }: { status: CameraClockStatus }) {
  return (
    <div
      className="absolute bottom-2 left-2 z-10 flex items-center gap-1.5 rounded-md bg-black/70 backdrop-blur-sm px-2 py-1 text-[11px] text-white shadow-lg pointer-events-auto"
      title={status.hint}
    >
      {status.ts != null && (
        <span className="font-mono tabular-nums tracking-tight">
          {formatDate(status.ts)} <span className="font-semibold">{formatTime(status.ts)}</span>
        </span>
      )}
      <span className={`flex items-center gap-1 rounded px-1.5 py-px text-[10px] font-bold ${toneChip[status.tone]}`}>
        {status.tone === 'green' && <span className="h-1.5 w-1.5 rounded-full bg-white animate-pulse" />}
        {status.label}
      </span>
    </div>
  )
}

type LiveInput = Omit<StatusInput, 'now'>

/** Selo com tick próprio — só ele re-renderiza a cada segundo, não a página */
export function CameraClockOverlay(props: LiveInput) {
  const now = useNow()
  return <CameraClock status={cameraClockStatus({ ...props, now })} />
}

/** Ponto de status para o cabeçalho do card da câmera */
export function CameraStatusDot(props: LiveInput) {
  const now = useNow()
  const status = cameraClockStatus({ ...props, now })
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${toneDot[status.tone]} ${status.tone === 'green' ? 'animate-pulse' : ''}`}
      title={status.hint}
    />
  )
}
