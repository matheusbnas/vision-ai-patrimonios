import {
  Shield,
  Github,
  BookOpen,
  Cpu,
  Database,
  Brain,
  Layers,
} from 'lucide-react'

const models = [
  {
    name: 'KzRyan/Burglary_and_Vandalism',
    source: 'Hugging Face',
    description:
      'CNN-Transformer Híbrido (ResNet18 + Transformer) para classificação de vandalismo. Classes: normal, burglary, vandalism.',
    icon: <Brain size={20} />,
    link: 'https://huggingface.co/KzRyan/Burglary_and_Vandalism',
  },
]

const features = [
  {
    title: 'Frontend Separado',
    desc: 'React + TypeScript + TailwindCSS com Vite, totalmente desacoplado do backend.',
    icon: <Layers size={20} />,
  },
  {
    title: 'API FastAPI',
    desc: 'Backend assíncrono em Python com documentação OpenAPI automática.',
    icon: <Cpu size={20} />,
  },
  {
    title: 'SLM + Transfer Learning',
    desc: 'Modelos do Hugging Face usados como Small Language Models ou fine-tunados com dados locais.',
    icon: <Brain size={20} />,
  },
  {
    title: 'Modelo Único Especializado',
    desc: 'KzRyan/Burglary_and_Vandalism para detecção de roubo, furto e vandalismo.',
    icon: <Brain size={20} />,
  },
]

export default function SobrePage() {
  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div className="bg-gradient-to-br from-cor-dark to-cor-blue rounded-2xl p-8 text-white">
        <div className="flex items-center gap-4 mb-4">
          <span className="text-5xl">🏛️</span>
          <div>
            <h1 className="text-2xl font-bold">Visão Patrimônios v2.0</h1>
            <p className="text-blue-200 text-sm">
              Sistema de Visão Computacional para Monitoramento de Patrimônios Públicos
            </p>
          </div>
        </div>
        <p className="text-blue-100 leading-relaxed">
          CO-RIO — Coordenadoria de Operações e Resiliência da Cidade do Rio de Janeiro.
          Sistema profissional com separação frontend/backend e integração com modelos
          de IA do Hugging Face para detecção de vandalismo e depredação.
        </p>
      </div>

      {/* Features */}
      <div>
        <h2 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Shield size={20} className="text-cor-gold" />
          Arquitetura
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {features.map((f, i) => (
            <div
              key={i}
              className="bg-white rounded-xl border border-gray-100 p-5 hover:shadow-sm transition-shadow"
            >
              <div className="flex items-center gap-3 mb-2">
                <div className="p-2 bg-cor-dark text-white rounded-lg">{f.icon}</div>
                <h3 className="font-semibold text-gray-800">{f.title}</h3>
              </div>
              <p className="text-sm text-gray-600">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Modelos de IA */}
      <div>
        <h2 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Brain size={20} className="text-purple-600" />
          Modelos de IA Integrados
        </h2>
        <div className="space-y-3">
          {models.map((m, i) => (
            <div
              key={i}
              className="bg-white rounded-xl border border-gray-100 p-5 hover:shadow-sm transition-shadow"
            >
              <div className="flex items-start gap-4">
                <div className="p-2 bg-gray-100 rounded-lg text-gray-600 mt-0.5">
                  {m.icon}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-semibold text-gray-800">{m.name}</h3>
                    <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
                      {m.source}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600">{m.description}</p>
                  {m.link && (
                    <a
                      href={m.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-cor-blue hover:underline mt-1 inline-block"
                    >
                      Ver no Hugging Face →
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Como usar Transfer Learning */}
      <div className="bg-gradient-to-br from-purple-50 to-blue-50 rounded-xl border border-purple-100 p-6">
        <h2 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
          <BookOpen size={18} className="text-purple-600" />
          Transfer Learning com os Modelos HF
        </h2>
        <div className="text-sm text-gray-600 space-y-2 leading-relaxed">
          <p>
            Os modelos do Hugging Face podem ser fine-tunados com imagens dos 
            patrimônios cariocas para aumentar a acurácia:
          </p>
          <ol className="list-decimal list-inside space-y-1 ml-2">
            <li>Colete imagens dos 10 patrimônios monitorados em diferentes condições</li>
            <li>Use o modelo <code className="bg-gray-200 px-1 rounded">KzRyan/Burglary_and_Vandalism</code> como base</li>
            <li>Fine-tune com dataset local usando PyTorch + Hugging Face</li>
            <li>Faça upload do modelo fine-tunado para o HF Hub ou use localmente</li>
          </ol>
          <p className="mt-2 text-xs text-gray-400">
            O modelo CNN-Transformer tem apenas 138MB, ideal para SLM em edge computing.
          </p>
        </div>
      </div>
    </div>
  )
}
