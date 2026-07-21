import { useState, useEffect } from 'react'
import {
  Landmark,
  Camera,
  AlertTriangle,
  Eye,
  Shield,
  TrendingUp,
} from 'lucide-react'
import { api } from '../api/client'
import type { DashboardStats, Patrimonio } from '../types'

function StatCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode
  label: string
  value: string | number
  color: string
}) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex items-center gap-4">
      <div className={`p-3 rounded-lg ${color}`}>{icon}</div>
      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
        <p className="text-2xl font-bold text-gray-800">{value}</p>
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [patrimonios, setPatrimonios] = useState<Patrimonio[]>([])
  const [loading, setLoading] = useState(true)

  const [cameraCount, setCameraCount] = useState(0)

  useEffect(() => {
    const load = async () => {
      try {
        const [dashboardData, patrimoniosData, cameras] = await Promise.all([
          api.getDashboardStats(),
          api.getPatrimonios(),
          api.getCameras().catch(() => []),
        ])
        setStats(dashboardData.stats)
        setPatrimonios(patrimoniosData)
        setCameraCount(cameras.length)
      } catch (err) {
        console.error('Erro ao carregar dashboard:', err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cor-blue" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<Landmark size={22} className="text-white" />}
          label="Patrimônios"
          value={stats?.total_patrimonios ?? patrimonios.length}
          color="bg-cor-blue"
        />
        <StatCard
          icon={<Camera size={22} className="text-white" />}
          label="Câmeras"
          value={cameraCount.toLocaleString('pt-BR')}
          color="bg-cor-blue-light"
        />
        <StatCard
          icon={<AlertTriangle size={22} className="text-white" />}
          label="Alertas Ativos"
          value={stats?.alertas_ativos ?? 0}
          color="bg-red-500"
        />
        <StatCard
          icon={<Eye size={22} className="text-white" />}
          label="Detecções Hoje"
          value={stats?.deteccoes_hoje ?? 0}
          color="bg-green-500"
        />
      </div>

      {/* Patrimônios List */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100">
        <div className="p-5 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
            <Shield size={20} className="text-cor-gold" />
            Patrimônios Monitorados
          </h2>
        </div>
        <div className="divide-y divide-gray-50">
          {patrimonios.map((p) => (
            <div
              key={p.id}
              className="p-4 hover:bg-gray-50 transition-colors flex items-center justify-between"
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">{p.emoji}</span>
                <div>
                  <p className="font-medium text-gray-800">{p.nome}</p>
                  <p className="text-xs text-gray-500">{p.bairro} • {p.categoria}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="status-dot online" />
                <span className="text-xs text-green-600 font-medium">Monitorado</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-gradient-to-br from-cor-blue to-cor-blue-light rounded-xl p-5 text-white">
          <div className="flex items-center gap-2 mb-3">
            <Shield size={20} />
            <h3 className="font-semibold">IA Integrada</h3>
          </div>
          <p className="text-sm text-blue-100 leading-relaxed">
            Sistema utiliza YOLO para detecção de objetos + modelo CNN-Transformer 
            do Hugging Face (KzRyan/Burglary_and_Vandalism) para classificação 
            de vandalismo em tempo real.
          </p>
        </div>

        <div className="bg-gradient-to-br from-amber-600 to-amber-700 rounded-xl p-5 text-white">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={20} />
            <h3 className="font-semibold">Transfer Learning</h3>
          </div>
          <p className="text-sm text-amber-100 leading-relaxed">
            Modelos do Hugging Face podem ser fine-tuned com dados locais 
            de patrimônios cariocas para maior acurácia em cenários específicos.
          </p>
        </div>
      </div>
    </div>
  )
}
