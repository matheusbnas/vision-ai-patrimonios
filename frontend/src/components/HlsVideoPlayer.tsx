import { useEffect, useRef, useState } from 'react'
import Hls from 'hls.js'

interface HlsVideoPlayerProps {
  src: string
  onError: () => void
  className?: string
}

// Player HLS de verdade (via hls.js) — usado no lugar do iframe WebRTC quando
// a câmera tem uma URL HLS disponível (protocolo real da conta na Tixxi,
// confirmado pelo suporte deles). Chama onError se o HLS falhar, pra quem
// usa esse componente poder cair de volta pro iframe WebRTC.
export default function HlsVideoPlayer({ src, onError, className }: HlsVideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const video = videoRef.current
    if (!video || !src) return

    setLoading(true)
    let hls: Hls | null = null

    if (Hls.isSupported()) {
      hls = new Hls({ maxLiveSyncPlaybackRate: 1.5 })
      hls.loadSource(src)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setLoading(false)
        video.play().catch(() => {})
      })
      hls.on(Hls.Events.ERROR, (_evt, data) => {
        if (data.fatal) {
          hls?.destroy()
          onError()
        }
      })
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari — suporte nativo a HLS
      video.src = src
      video.addEventListener('loadedmetadata', () => {
        setLoading(false)
        video.play().catch(() => {})
      })
      video.addEventListener('error', onError)
    } else {
      onError()
    }

    return () => {
      hls?.destroy()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src])

  return (
    <div className={`relative ${className || ''}`}>
      <video
        ref={videoRef}
        muted
        playsInline
        autoPlay
        className="absolute inset-0 w-full h-full object-cover"
      />
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center text-gray-400 text-xs bg-black/50 pointer-events-none">
          Carregando HLS...
        </div>
      )}
    </div>
  )
}
