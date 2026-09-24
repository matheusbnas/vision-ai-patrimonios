import { useEffect, useState } from 'react'
import { toProxiedVideoUrl } from '../api/client'
import HlsVideoPlayer from './HlsVideoPlayer'

interface CameraStreamViewProps {
  code: string
  streamUrl?: string
  hlsUrl?: string
  streamType?: string
  // Incrementa pra forçar remount do player (botão "Recarregar").
  reloadToken?: number
  onLoad?: () => void
  onError?: () => void
  className?: string
}

// Player de câmera única, usado tanto no grid de Monitoramento quanto no
// player individual de Patrimônios — mesma lógica de qual tag usar pra cada
// protocolo, num só lugar:
//   - HLS (protocolo real da Tixxi) quando disponível: <video>+hls.js
//   - stream_type "raw" (MJPEG puro, multipart/x-mixed-replace): <img>
//   - stream_type "html" (página com player WebRTC/WHEP da Tixxi): <iframe>,
//     passando pelo NOSSO backend (toProxiedVideoUrl → video_proxy.py) —
//     necessário pro player WebRTC deles funcionar embutido (ver
//     video_proxy.py pro porquê).
export default function CameraStreamView({
  code,
  streamUrl,
  hlsUrl,
  streamType,
  reloadToken = 0,
  onLoad,
  onError,
  className,
}: CameraStreamViewProps) {
  const [hlsFailed, setHlsFailed] = useState(false)

  // Nova hlsUrl (ex: depois de "Recarregar") ou troca de câmera — dá uma
  // nova chance pro HLS antes de cair pro fallback de novo.
  useEffect(() => {
    setHlsFailed(false)
  }, [code, hlsUrl])

  if (hlsUrl && !hlsFailed) {
    return (
      <HlsVideoPlayer
        key={`hls-${code}`}
        src={hlsUrl}
        className={className}
        onError={() => setHlsFailed(true)}
      />
    )
  }

  if (streamType === 'raw') {
    return (
      <img
        key={`mjpeg-${code}-${reloadToken}`}
        src={streamUrl}
        alt={`Stream ao vivo ${code}`}
        referrerPolicy="no-referrer"
        className={className}
        onLoad={onLoad}
        onError={onError}
      />
    )
  }

  return (
    <iframe
      key={`iframe-${code}-${reloadToken}`}
      src={streamUrl ? toProxiedVideoUrl(streamUrl) : undefined}
      referrerPolicy="no-referrer"
      className={className}
      allow="accelerometer;autoplay;encrypted-media;gyroscope"
      allowFullScreen
      onLoad={onLoad}
      onError={onError}
    />
  )
}
