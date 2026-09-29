import { useEffect, useState } from 'react'
import { Clock } from 'lucide-react'

// Operação do COR: sempre no horário de Brasília, independente do PC do operador
const TZ = 'America/Sao_Paulo'

const dateFmt = new Intl.DateTimeFormat('pt-BR', {
  timeZone: TZ,
  weekday: 'short',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})
const shortDateFmt = new Intl.DateTimeFormat('pt-BR', {
  timeZone: TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})
const timeFmt = new Intl.DateTimeFormat('pt-BR', {
  timeZone: TZ,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

/** Data curta (dd/mm/aaaa) no horário de Brasília; recebe ms */
export const formatDate = (ms: number) => shortDateFmt.format(ms)
/** Hora (hh:mm:ss) no horário de Brasília; recebe ms */
export const formatTime = (ms: number) => timeFmt.format(ms)

/** Data/hora atual (ms), atualizada a cada `intervalMs` */
export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

/** Relógio do header: dia da semana, data e hora oficial de Brasília */
export default function LiveClock() {
  const now = useNow()
  const date = dateFmt.format(now).replace('.', '')

  return (
    <div
      className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full ring-1 ring-slate-200 bg-white text-xs text-slate-600"
      title="Horário de Brasília"
    >
      <Clock size={14} className="text-cor-blue" />
      <span className="hidden xl:inline capitalize">{date}</span>
      <span className="xl:hidden">{formatDate(now)}</span>
      <span className="h-3 w-px bg-slate-200" />
      <span className="font-semibold text-slate-800 tabular-nums">{formatTime(now)}</span>
    </div>
  )
}
