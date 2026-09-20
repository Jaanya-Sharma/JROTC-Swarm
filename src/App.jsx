
import { useEffect, useMemo, useRef, useState } from 'react'
import { jsPDF } from 'jspdf'

const BACKEND_WS_URL = 'ws://127.0.0.1:8000/ws/tracks'
const BACKEND_VIDEO_URL = 'http://127.0.0.1:8000/video'
const BACKEND_API_URL = 'http://127.0.0.1:8000'
const WS_BUFFER_SECONDS = 60

function useLocalStorage(key, initialValue){
  const [value, setValue] = useState(()=>{
    try {
      const stored = window.localStorage.getItem(key)
      return stored === null ? initialValue : JSON.parse(stored)
    } catch {
      return initialValue
    }
  })

  useEffect(()=>{
    try {
      window.localStorage.setItem(key, JSON.stringify(value))
    } catch {
      // Keep the in-memory value when storage is unavailable or full.
    }
  }, [key, value])

  return [value, setValue]
}

function clamp(n, a, b){ return Math.max(a, Math.min(b, n)) }
function fmt(n, d=0){ return (n===null||n===undefined||Number.isNaN(n)) ? '—' : n.toFixed(d) }

function polarToXY(cx, cy, radius, bearingDeg, rangeU){
  const a = (bearingDeg - 90) * Math.PI / 180
  const rr = radius * rangeU
  return { x: cx + rr*Math.cos(a), y: cy + rr*Math.sin(a) }
}

function closestFrameForTime(frames, mediaTime){
  return frames.reduce((closest, frame) =>
    Math.abs(frame.media_t_sec - mediaTime) < Math.abs(closest.media_t_sec - mediaTime)
      ? frame
      : closest
  )
}

function makeTrack(id, t){
  const base = (id * 37) % 360
  const phase = (t/1000) * (0.10 + (id%7)*0.012)
  const bearing = (base + phase*160) % 360
  const rangeBase = 0.14 + ((id%10)/10)*0.82
  const wobble = Math.sin(phase*2 + id) * 0.07
  const range = clamp(rangeBase + wobble, 0.06, 0.98)

  const altBand = range < 0.35 ? 'LOW' : range < 0.7 ? 'MED' : 'HIGH'
  const type = id%11===0 ? 'multirotor' : id%7===0 ? 'fixedwing' : 'unknown'
  const conf = clamp(0.55 + (Math.sin(phase + id)+1)*0.20, 0.22, 0.98)
  const relSpeed = clamp(9 + Math.cos(phase*1.5 + id)*7, 0, 28)
  const heading = (bearing + 110 + Math.sin(phase + id)*26) % 360

  const flags = []
  if (conf < 0.5) flags.push('LOW_CONF')
  if (id%13===0 && Math.sin(phase*0.9) > 0.72) flags.push('OCCLUDED')
  if (id%29===0 && Math.sin(phase*0.7) > 0.83) flags.push('LOST')

  return {
    id,
    callsign: `UAV-${String(id).padStart(2,'0')}`,
    type,
    bearing,
    range_u: range,
    heading,
    rel_speed_u: relSpeed,
    alt_band: altBand,
    confidence: conf,
    flags,
  }
}

function groupClusters(tracks){
  const buckets = new Map()
  for (const tr of tracks){
    const b = Math.floor(tr.bearing/20)
    const r = Math.floor(tr.range_u/0.2)
    const key = `${b}-${r}`
    buckets.set(key, (buckets.get(key)||0)+1)
  }
  return [...buckets.entries()].map(([k,n])=>({k,n})).sort((a,b)=>b.n-a.n).slice(0,6)
}

function sev(track){
  if (track.flags.includes('LOST')) return 'bad'
  if (track.flags.includes('OCCLUDED')) return 'warn'
  if (track.confidence < 0.55) return 'warn'
  return 'ok'
}

function typeLabel(t){
  if (t==='fixedwing') return 'Fixed-wing'
  if (t==='multirotor') return 'Multirotor'
  return 'Unknown'
}

function nowTS(){
  const d = new Date()
  return d.toISOString().slice(11,19)
}

export default function App(){
  const [authToken, setAuthToken] = useState(()=> window.sessionStorage.getItem('radar-access-token') || '')
  const [authUsername, setAuthUsername] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authError, setAuthError] = useState('')
  const [authSubmitting, setAuthSubmitting] = useState(false)
  const [videoUrl, setVideoUrl] = useState(null)
  const [videoRequestVersion, setVideoRequestVersion] = useState(0)
  const [backendOffline, setBackendOffline] = useState(false)
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(1)
  const [tick, setTick] = useState(0)
  const [videoDuration, setVideoDuration] = useState(600)
  const [videoLoaded, setVideoLoaded] = useState(false)
  const [selectedId, setSelectedId] = useState(7)
  const [notesById, setNotesById] = useLocalStorage('commander-notes-by-track-id', {})
  const [search, setSearch] = useState('')
  const [alertsOnly, setAlertsOnly] = useState(false)
  const [showVectors, setShowVectors] = useState(true)
  const [rings, setRings] = useState(5)
  const [syncedTracks, setSyncedTracks] = useState(null)
  const [zoneEvents, setZoneEvents] = useState([])
  const [drawZoneMode, setDrawZoneMode] = useState(false)
  const [zoneDrag, setZoneDrag] = useState(null)
  const [zones, setZones] = useState([])
  const [expandedPanel, setExpandedPanel] = useState(null)

  const timerRef = useRef(null)
  const videoRef = useRef(null)
  const overlayCanvasRef = useRef(null)
  const wsFrameBufferRef = useRef([])
  const frameSizeRef = useRef({ width: 0, height: 0 })
  const syncedFrameRef = useRef(null)
  const radarSvgRef = useRef(null)

  useEffect(()=>{
    clearInterval(timerRef.current)
    if (!playing || videoLoaded) return
    timerRef.current = setInterval(()=> setTick(t=>t+1), 250 / speed)
    return ()=> clearInterval(timerRef.current)
  }, [playing, speed, videoLoaded])

  useEffect(()=>{
    const video = videoRef.current
    if (!video) return
    video.playbackRate = speed
    if (playing) video.play().catch(()=>{})
    else video.pause()
  }, [playing, speed])

  useEffect(()=>{
    let objectUrl
    let cancelled = false
    setVideoLoaded(false)
    if (!authToken){
      setVideoUrl(null)
      return undefined
    }

    fetch(BACKEND_VIDEO_URL, { headers: { Authorization: `Bearer ${authToken}` } })
      .then(response => {
        if (response.status === 401 || response.status === 403) {
          const error = new Error('Video request was rejected')
          error.authFailure = true
          throw error
        }
        if (!response.ok) throw new Error('Video request failed')
        return response.blob()
      })
      .then(blob => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setVideoUrl(objectUrl)
      })
      .catch(error => {
        if (!cancelled) {
          if (error.authFailure) {
            window.sessionStorage.removeItem('radar-access-token')
            setAuthError('Your session has expired. Sign in again.')
            setAuthToken('')
          } else {
            setBackendOffline(true)
          }
        }
      })

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [authToken, videoRequestVersion])

  useEffect(()=>{
    let socket
    let retryTimer
    let cancelled = false
    if (!authToken) return undefined

    const connect = () => {
      const wsUrl = new URL(BACKEND_WS_URL)
      wsUrl.searchParams.set('access_token', authToken)
      socket = new WebSocket(wsUrl)

      socket.onopen = () => {
        setBackendOffline(false)
        setVideoRequestVersion(version => version + 1)
      }

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data)
        if (Number.isFinite(message.frame_w) && Number.isFinite(message.frame_h)){
          frameSizeRef.current = { width: message.frame_w, height: message.frame_h }
        }
        if (Number.isFinite(message.media_t_sec) && (Array.isArray(message.bboxes) || Array.isArray(message.tracks))){
          const frames = wsFrameBufferRef.current
          frames.push(message)
          const cutoff = message.media_t_sec - WS_BUFFER_SECONDS
          while (frames.length && frames[0].media_t_sec < cutoff) frames.shift()
        }
        if (message.type === 'events' && Array.isArray(message.events)){
          setZoneEvents(currentEvents => [...message.events, ...currentEvents].slice(0, 100))
        }
      }

      socket.onclose = (event) => {
        if (cancelled) return
        if (event.code === 1008) {
          window.sessionStorage.removeItem('radar-access-token')
          setAuthError('Your session is invalid or has expired. Sign in again.')
          setAuthToken('')
          return
        }
        setBackendOffline(true)
        setSyncedTracks(null)
        syncedFrameRef.current = null
        wsFrameBufferRef.current = []
        if (!cancelled) retryTimer = window.setTimeout(connect, 2000)
      }

      socket.onerror = () => socket.close()
    }

    retryTimer = window.setTimeout(connect, 0)

    return () => {
      cancelled = true
      window.clearTimeout(retryTimer)
      socket?.close()
    }
  }, [authToken])

  useEffect(()=>{
    let animationFrameId

    const drawOverlay = () => {
      const video = videoRef.current
      const canvas = overlayCanvasRef.current
      if (!video || !canvas) return

      const width = video.clientWidth
      const height = video.clientHeight
      const pixelRatio = window.devicePixelRatio || 1
      if (canvas.width !== Math.round(width * pixelRatio) || canvas.height !== Math.round(height * pixelRatio)){
        canvas.width = Math.round(width * pixelRatio)
        canvas.height = Math.round(height * pixelRatio)
      }

      const context = canvas.getContext('2d')
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
      context.clearRect(0, 0, width, height)

      const frames = wsFrameBufferRef.current
      if (frames.length){
        const closestFrame = closestFrameForTime(frames, video.currentTime)
        if (closestFrame !== syncedFrameRef.current){
          syncedFrameRef.current = closestFrame
          setSyncedTracks(Array.isArray(closestFrame.tracks) ? closestFrame.tracks : null)
        }
        const sourceWidth = closestFrame.frame_w || frameSizeRef.current.width || video.videoWidth
        const sourceHeight = closestFrame.frame_h || frameSizeRef.current.height || video.videoHeight

        if (sourceWidth && sourceHeight){
          context.strokeStyle = '#22c55e'
          context.fillStyle = '#22c55e'
          context.lineWidth = 2
          context.font = '12px ui-monospace, monospace'
          for (const bbox of closestFrame.bboxes || []){
            const [x1, y1, x2, y2, confidence] = Array.isArray(bbox)
              ? bbox
              : [bbox.x1, bbox.y1, bbox.x2, bbox.y2, bbox.confidence]
            if (![x1, y1, x2, y2].every(Number.isFinite)) continue

            const x = x1 * width / sourceWidth
            const y = y1 * height / sourceHeight
            const boxWidth = (x2 - x1) * width / sourceWidth
            const boxHeight = (y2 - y1) * height / sourceHeight
            context.strokeRect(x, y, boxWidth, boxHeight)
            if (Number.isFinite(confidence)) context.fillText(confidence.toFixed(2), x, Math.max(12, y - 4))
          }
        }
      }

      animationFrameId = requestAnimationFrame(drawOverlay)
    }

    animationFrameId = requestAnimationFrame(drawOverlay)
    return () => cancelAnimationFrame(animationFrameId)
  }, [])

  const t = Date.now() + tick*120
  const tracks = useMemo(()=>{
    if (syncedTracks !== null) return syncedTracks

    const list = []
    for (let i=1;i<=72;i++) list.push(makeTrack(i, t))
    return list
  }, [t, syncedTracks])

  const clusters = useMemo(()=>groupClusters(tracks), [tracks])
  const selected = useMemo(()=> tracks.find(x=>x.id===selectedId) || null, [tracks, selectedId])

  const alertCount = useMemo(()=> tracks.filter(x=> x.flags.length>0 || x.confidence<0.55).length, [tracks])

  const filtered = useMemo(()=>{
    let list = tracks
    if (search.trim()){
      const q = search.trim().toLowerCase()
      list = list.filter(x => x.callsign.toLowerCase().includes(q) || typeLabel(x.type).toLowerCase().includes(q))
    }
    if (alertsOnly){
      list = list.filter(x => x.flags.length>0 || x.confidence<0.55)
    }
    return list
  }, [tracks, search, alertsOnly])

  const logRows = useMemo(()=>{
    const rows = zoneEvents.map(event => ({
      ts: new Date(event.ts_ms).toISOString().slice(11,19),
      msg: `Zone ${event.type.toUpperCase()}: Track ${event.track_id} • ${event.zone_name || event.zone_id}`,
    }))
    rows.push({ ts: nowTS(), msg: `AI stream active • ${tracks.length} tracks • ${alertCount} flagged` })
    if (clusters[0]) rows.push({ ts: nowTS(), msg: `Cohesion: Cluster 1 ~ ${clusters[0].n} tracks` })
    const lost = tracks.filter(x=>x.flags.includes('LOST')).length
    if (lost) rows.push({ ts: nowTS(), msg: `Alert: ${lost} track(s) marked LOST (reacquire required)` })
    const occ = tracks.filter(x=>x.flags.includes('OCCLUDED')).length
    if (occ) rows.push({ ts: nowTS(), msg: `Info: ${occ} track(s) OCCLUDED (line-of-sight / clutter)` })
    rows.push({ ts: nowTS(), msg: `Mode: Relative range units + inferred altitude bands (no telemetry)` })
    return rows
  }, [zoneEvents, tracks, clusters, alertCount])

  const seekVideo = (seconds) => {
    const video = videoRef.current
    if (video) video.currentTime = Math.max(0, video.currentTime + seconds)
    setTick(v=> Math.max(0, v + seconds))
  }
  const rewind = ()=> seekVideo(-12)
  const stepBack = ()=> seekVideo(-1 / 30)
  const stepFwd = ()=> seekVideo(1 / 30)
  const fastFwd = ()=> seekVideo(12)

  const W=680, H=520
  const cx=W/2, cy=H/2
  const radius=Math.min(W,H)/2 - 28

  const ringEls = []
  for (let i=1;i<=rings;i++){
    ringEls.push(
      <circle key={i} cx={cx} cy={cy} r={(radius*i)/rings} className="ring" />
    )
  }

  const radarPoint = (event) => {
    const svg = radarSvgRef.current
    const matrix = svg?.getScreenCTM()
    if (!svg || !matrix) return null
    const point = svg.createSVGPoint()
    point.x = event.clientX
    point.y = event.clientY
    const { x, y } = point.matrixTransform(matrix.inverse())
    return { x: clamp(x, 0, W), y: clamp(y, 0, H) }
  }

  const startZoneDrag = (event) => {
    if (!drawZoneMode) return
    const point = radarPoint(event)
    if (point) setZoneDrag({ start: point, current: point })
  }

  const updateZoneDrag = (event) => {
    if (!zoneDrag) return
    const point = radarPoint(event)
    if (point) setZoneDrag(drag => ({ ...drag, current: point }))
  }

  const finishZoneDrag = async (event) => {
    if (!zoneDrag) return
    const point = radarPoint(event) || zoneDrag.current
    const x1 = Math.min(zoneDrag.start.x, point.x) / W
    const y1 = Math.min(zoneDrag.start.y, point.y) / H
    const x2 = Math.max(zoneDrag.start.x, point.x) / W
    const y2 = Math.max(zoneDrag.start.y, point.y) / H
    setZoneDrag(null)

    if (x2 - x1 < 0.01 || y2 - y1 < 0.01) return
    const name = window.prompt('Zone name')?.trim()
    if (!name) return

    try {
      const response = await fetch(`${BACKEND_API_URL}/zones`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
        body: JSON.stringify({ name, rect: { x1, y1, x2, y2 } }),
      })
      if (!response.ok) throw new Error('Zone creation failed')
      const createdZone = await response.json()
      setZones(currentZones => [...currentZones, createdZone])
    } catch {
      window.alert('Could not create zone.')
    }
  }

  const visibleZoneRect = (zone) => ({
    x: zone.rect.x1 * W,
    y: zone.rect.y1 * H,
    width: (zone.rect.x2 - zone.rect.x1) * W,
    height: (zone.rect.y2 - zone.rect.y1) * H,
  })

  const exportAar = async () => {
    const endMs = Date.now()
    const startMs = endMs - 5 * 60 * 1000
    const query = new URLSearchParams({
      start_ms: String(startMs),
      end_ms: String(endMs),
      limit: '20000',
    })

    try {
      const [replayResponse, eventsResponse] = await Promise.all([
        fetch(`${BACKEND_API_URL}/replay?${query}`, { headers: { Authorization: `Bearer ${authToken}` } }),
        fetch(`${BACKEND_API_URL}/events?${query}`, { headers: { Authorization: `Bearer ${authToken}` } }),
      ])
      if (!replayResponse.ok || !eventsResponse.ok) throw new Error('AAR fetch failed')

      const [replay, events] = await Promise.all([
        replayResponse.json(),
        eventsResponse.json(),
      ])
      const eventList = events.events || []
      const pdf = new jsPDF({ unit: 'pt', format: 'letter' })
      const pageWidth = pdf.internal.pageSize.getWidth()
      const margin = 42
      const timeline = { x: margin, y: 158, width: pageWidth - margin * 2, height: 110 }
      const zoneMap = { x: margin, y: 330, width: 250, height: 180 }

      pdf.setFillColor(10, 18, 30)
      pdf.rect(0, 0, pageWidth, 76, 'F')
      pdf.setTextColor(230, 242, 255)
      pdf.setFontSize(20)
      pdf.text('After-Action Report', margin, 36)
      pdf.setFontSize(10)
      pdf.text(`Generated ${new Date(endMs).toISOString()}`, margin, 56)

      pdf.setTextColor(30, 41, 59)
      pdf.setFontSize(11)
      pdf.text(`Window: ${new Date(startMs).toLocaleTimeString()} to ${new Date(endMs).toLocaleTimeString()}`, margin, 100)
      pdf.text(`Track samples: ${replay.samples?.length || 0}   Zone events: ${eventList.length}   Zones: ${zones.length}`, margin, 117)
      if (!(replay.samples?.length) && !eventList.length){
        pdf.setTextColor(180, 83, 9)
        pdf.setFontSize(9)
        pdf.text('No stored samples or events were returned for this five-minute window.', margin, 136)
      }

      pdf.setFontSize(12)
      pdf.text('Event timeline', timeline.x, timeline.y - 10)
      pdf.setDrawColor(148, 163, 184)
      pdf.rect(timeline.x, timeline.y, timeline.width, timeline.height)
      pdf.setFontSize(9)
      pdf.setTextColor(71, 85, 105)
      pdf.text(new Date(startMs).toLocaleTimeString(), timeline.x, timeline.y + timeline.height + 14)
      pdf.text(new Date(endMs).toLocaleTimeString(), timeline.x + timeline.width - 54, timeline.y + timeline.height + 14)

      const eventColors = { enter: [34, 197, 94], exit: [239, 68, 68], dwell: [245, 158, 11] }
      eventList.forEach((event, index) => {
        const ratio = clamp((event.ts_ms - startMs) / (endMs - startMs), 0, 1)
        const x = timeline.x + ratio * timeline.width
        const color = eventColors[event.type] || [56, 189, 248]
        pdf.setDrawColor(...color)
        pdf.setFillColor(...color)
        pdf.line(x, timeline.y + 14, x, timeline.y + timeline.height - 14)
        pdf.circle(x, timeline.y + 24 + (index % 3) * 22, 3, 'F')
      })
      pdf.setFontSize(9)
      ;[['ENTER', eventColors.enter], ['EXIT', eventColors.exit], ['DWELL', eventColors.dwell]].forEach(([label, color], index) => {
        const x = timeline.x + index * 76
        pdf.setFillColor(...color)
        pdf.circle(x, timeline.y + timeline.height - 8, 3, 'F')
        pdf.setTextColor(71, 85, 105)
        pdf.text(label, x + 7, timeline.y + timeline.height - 5)
      })

      pdf.setTextColor(30, 41, 59)
      pdf.setFontSize(12)
      pdf.text('Zone map', zoneMap.x, zoneMap.y - 10)
      pdf.setFillColor(241, 245, 249)
      pdf.rect(zoneMap.x, zoneMap.y, zoneMap.width, zoneMap.height, 'F')
      pdf.setDrawColor(148, 163, 184)
      pdf.rect(zoneMap.x, zoneMap.y, zoneMap.width, zoneMap.height)
      zones.forEach(zone => {
        const x = zoneMap.x + zone.rect.x1 * zoneMap.width
        const y = zoneMap.y + zone.rect.y1 * zoneMap.height
        const width = (zone.rect.x2 - zone.rect.x1) * zoneMap.width
        const height = (zone.rect.y2 - zone.rect.y1) * zoneMap.height
        pdf.setFillColor(56, 189, 248)
        pdf.setDrawColor(14, 116, 144)
        pdf.setGState(new pdf.GState({ opacity: 0.25 }))
        pdf.rect(x, y, width, height, 'FD')
        pdf.setGState(new pdf.GState({ opacity: 1 }))
        pdf.setTextColor(8, 47, 73)
        pdf.setFontSize(8)
        pdf.text(zone.name, x + 4, y + 12, { maxWidth: Math.max(10, width - 8) })
      })

      const eventListX = zoneMap.x + zoneMap.width + 34
      pdf.setTextColor(30, 41, 59)
      pdf.setFontSize(12)
      pdf.text('Recent events', eventListX, zoneMap.y - 10)
      pdf.setFontSize(9)
      eventList.slice(-12).reverse().forEach((event, index) => {
        const y = zoneMap.y + 16 + index * 13
        const text = `${new Date(event.ts_ms).toLocaleTimeString()}  ${event.type.toUpperCase()}  T${event.track_id}  ${event.zone_name || event.zone_id}`
        pdf.text(text, eventListX, y, { maxWidth: pageWidth - eventListX - margin })
      })
      if (!eventList.length) pdf.text('No events recorded in this window.', eventListX, zoneMap.y + 16)

      pdf.save(`aar-${endMs}.pdf`)
    } catch {
      window.alert('Could not export the AAR.')
    }
  }

  const signIn = async (event) => {
    event.preventDefault()
    setAuthError('')
    setAuthSubmitting(true)
    try {
      const response = await fetch(`${BACKEND_API_URL}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: authUsername, password: authPassword }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || typeof payload.access_token !== 'string') {
        throw new Error(payload.detail || 'Sign-in failed')
      }
      window.sessionStorage.setItem('radar-access-token', payload.access_token)
      setAuthPassword('')
      setAuthToken(payload.access_token)
    } catch (error) {
      setAuthError(typeof error.message === 'string' ? error.message : 'Sign-in failed')
    } finally {
      setAuthSubmitting(false)
    }
  }

  const signOut = () => {
    window.sessionStorage.removeItem('radar-access-token')
    setAuthToken('')
    setSyncedTracks(null)
    setZoneEvents([])
    setBackendOffline(false)
    wsFrameBufferRef.current = []
  }

  if (!authToken) return (
    <main className="authShell">
      <form className="authCard" onSubmit={signIn}>
        <div className="authEyebrow">JROTC SWARM TACTICAL CONSOLE</div>
        <h1>Operator sign in</h1>
        <p>Enter the credentials configured in <code>backend/.env</code> to access the live tactical picture.</p>
        <label>
          Username
          <input value={authUsername} onChange={event => setAuthUsername(event.target.value)} autoComplete="username" maxLength="128" required />
        </label>
        <label>
          Password
          <input type="password" value={authPassword} onChange={event => setAuthPassword(event.target.value)} autoComplete="current-password" maxLength="1024" required />
        </label>
        {authError && <div className="authError" role="alert">{authError}</div>}
        <button className="btn primary authSubmit" disabled={authSubmitting}>
          {authSubmitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )

  return (
    <div className="shell">
      <div className="topbar">
        <div className="brand">
          <div className="logo">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M12 2v4" stroke="rgba(234,242,255,.9)" strokeWidth="2" strokeLinecap="round"/>
              <path d="M4.93 4.93l2.83 2.83" stroke="rgba(234,242,255,.9)" strokeWidth="2" strokeLinecap="round"/>
              <path d="M2 12h4" stroke="rgba(234,242,255,.9)" strokeWidth="2" strokeLinecap="round"/>
              <path d="M4.93 19.07l2.83-2.83" stroke="rgba(234,242,255,.9)" strokeWidth="2" strokeLinecap="round"/>
              <path d="M12 18v4" stroke="rgba(234,242,255,.9)" strokeWidth="2" strokeLinecap="round"/>
              <path d="M19.07 19.07l-2.83-2.83" stroke="rgba(234,242,255,.9)" strokeWidth="2" strokeLinecap="round"/>
              <path d="M18 12h4" stroke="rgba(234,242,255,.9)" strokeWidth="2" strokeLinecap="round"/>
              <path d="M19.07 4.93l-2.83 2.83" stroke="rgba(234,242,255,.9)" strokeWidth="2" strokeLinecap="round"/>
              <circle cx="12" cy="12" r="4" stroke="rgba(34,197,94,.9)" strokeWidth="2"/>
            </svg>
          </div>
          <div>
            <h1>JROTC Swarm Tactical Console</h1>
            <div className="sub">2026 layout • ATAK-inspired, modernized • training mode</div>
          </div>
        </div>

        <div className="pills">
          <div className="pill"><span className="dot" /> AI <b>LIVE</b></div>
          <div className="pill">Tracks <b>{tracks.length}</b></div>
          <div className="pill">Flagged <b>{alertCount}</b></div>
          <div className="pill">Mode <b>REL</b></div>
          <div className="pill">T+ <b>{tick}s</b></div>
        </div>

        <div className="actions">
          <button className="btn" onClick={()=>setShowVectors(v=>!v)}>{showVectors ? 'Vectors: ON' : 'Vectors: OFF'}</button>
          <button className="btn" onClick={()=>setAlertsOnly(v=>!v)}>{alertsOnly ? 'Alerts: ON' : 'Alerts: OFF'}</button>
          <button className="btn primary topPlaybackButton" onClick={()=>setPlaying(p=>!p)}>{playing ? 'Pause' : 'Play'}</button>
          <button className="btn" onClick={rewind}>⟲ Rewind</button>
          <button className="btn" onClick={fastFwd}>Fast ⟳</button>
          <button className="btn" onClick={exportAar}>Export AAR</button>
          <button className="btn" onClick={signOut}>Sign out</button>
        </div>
      </div>

      <div className="mid">
        {/* LEFT: Video + playback */}
        <div className={`panel workspacePanel${expandedPanel === 'video' ? ' panelExpanded' : ''}`}>
          <div className="panelHeader">
            <div className="panelTitle">
              <div className="t">Video Feed</div>
              <div className="d">MP4 feed with time-synchronized detection overlay</div>
            </div>
            <div className="kpi"><span>DVIDS • Perdix demo</span></div>
            <button className="btn" onClick={()=>setExpandedPanel(expandedPanel === 'video' ? null : 'video')}>
              {expandedPanel === 'video' ? 'Restore' : 'Expand'}
            </button>
          </div>

          <div className="panelBody">
            <div className="videoBox">
              <video ref={videoRef} className="videoFeed" src={videoUrl || undefined} autoPlay muted playsInline onLoadedMetadata={()=>{ const video = videoRef.current; video.playbackRate = speed; setVideoDuration(video.duration || 600); setVideoLoaded(true) }} onTimeUpdate={(event)=>setTick(event.currentTarget.currentTime)} />
              <canvas ref={overlayCanvasRef} className="videoOverlay" aria-label="Detection overlay" />
              {backendOffline && <div className="offlineNotice">Backend offline — simulator fallback active</div>}
              <div className="hud">
                <div className="tag tagTL"><b>HUD</b> • IDs • Conf • Flags</div>
                <div className="tag tagTR"><b>INTEGRITY</b> • no false precision</div>
                <div className="tag tagBL"><b>NOTE</b> • range units + altitude bands are inferred</div>
              </div>
            </div>

            <div className="controlsRow">
              <button className="btn primary" onClick={()=>setPlaying(p=>!p)}>{playing ? 'Pause' : 'Play'}</button>
              <button className="btn" onClick={stepBack}>Step -1</button>
              <button className="btn" onClick={stepFwd}>Step +1</button>
              <button className="btn" onClick={rewind}>-12</button>
              <button className="btn" onClick={fastFwd}>+12</button>

              <select className="select" value={speed} onChange={(e)=>setSpeed(Number(e.target.value))}>
                <option value={0.5}>0.5×</option>
                <option value={1}>1×</option>
                <option value={2}>2×</option>
                <option value={4}>4×</option>
              </select>

              <div className="small">Playback • T+ {tick}s</div>
            </div>

            <div style={{ marginTop: 10 }}>
              <input className="range" type="range" min="0" max={videoDuration} step="0.1" value={Math.min(tick, videoDuration)} onChange={(e)=>{ const time = Number(e.target.value); if (videoRef.current) videoRef.current.currentTime = time; setTick(time) }} />
              <div className="small">Timeline scrub • deterministic simulation</div>
            </div>
          </div>
        </div>

        {/* CENTER: Radar */}
        <div className={`panel workspacePanel${expandedPanel === 'radar' ? ' panelExpanded' : ''}`}>
          <div className="panelHeader radarPanelHeader">
            <div className="panelTitle">
              <div className="t">Radar / Tactical Picture</div>
              <div className="d">Bearing + relative range • vectors optional • click a track for details</div>
            </div>
            <div className="kpi">
              <span>Rings: {rings}</span>
              <span>Clusters: {clusters.length}</span>
              <span>Selected: {selected ? selected.callsign : '—'}</span>
              <button className={`btn${drawZoneMode ? ' primary' : ''}`} onClick={()=>setDrawZoneMode(enabled=>!enabled)}>
                {drawZoneMode ? 'Drawing zone…' : 'Draw zone'}
              </button>
              <button className="btn" onClick={()=>setExpandedPanel(expandedPanel === 'radar' ? null : 'radar')}>
                {expandedPanel === 'radar' ? 'Restore' : 'Expand'}
              </button>
            </div>
          </div>

          <div className="panelBody" style={{ overflow:'hidden' }}>
            <div className="radarWrap">
              <svg
                ref={radarSvgRef}
                className={`radarSvg${drawZoneMode ? ' drawingZone' : ''}`}
                viewBox={`0 0 ${W} ${H}`}
                onMouseDown={startZoneDrag}
                onMouseMove={updateZoneDrag}
                onMouseUp={finishZoneDrag}
              >
                {/* Base circle + rings */}
                <circle cx={cx} cy={cy} r={radius} stroke="rgba(255,255,255,.22)" fill="none" />
                {ringEls.map((el, idx)=>{
                  return (
                    <circle key={idx} cx={cx} cy={cy} r={(radius*(idx+1))/rings} stroke="rgba(255,255,255,.10)" fill="none" strokeDasharray={idx+1===rings ? "0" : "3 7"} />
                  )
                })}
                <line x1="20" y1={cy} x2={W-20} y2={cy} stroke="rgba(255,255,255,.07)" />
                <line x1={cx} y1="20" x2={cx} y2={H-20} stroke="rgba(255,255,255,.07)" />

                {/* Sweep wedge */}
                <path d={`M ${cx} ${cy} L ${cx} ${cy-radius} A ${radius} ${radius} 0 0 1 ${cx + radius*0.35} ${cy - radius*0.94} Z`}
                      fill="rgba(34,197,94,.10)" />

                {zones.map(zone => {
                  const rect = visibleZoneRect(zone)
                  return (
                    <g key={zone.id} pointerEvents="none">
                      <rect {...rect} fill="rgba(56,189,248,.12)" stroke="rgba(56,189,248,.9)" strokeWidth="2" />
                      <text x={rect.x + 6} y={rect.y + 16} fill="rgba(186,230,253,.95)" fontSize="12">{zone.name}</text>
                    </g>
                  )
                })}
                {zoneDrag ? (
                  <rect
                    x={Math.min(zoneDrag.start.x, zoneDrag.current.x)}
                    y={Math.min(zoneDrag.start.y, zoneDrag.current.y)}
                    width={Math.abs(zoneDrag.current.x - zoneDrag.start.x)}
                    height={Math.abs(zoneDrag.current.y - zoneDrag.start.y)}
                    fill="rgba(56,189,248,.12)"
                    stroke="rgba(56,189,248,.95)"
                    strokeDasharray="6 4"
                    pointerEvents="none"
                  />
                ) : null}

                {/* Tracks */}
                {tracks.map(tr=>{
                  const p = polarToXY(cx, cy, radius, tr.bearing, tr.range_u)
                  const isSel = tr.id===selectedId
                  const s = isSel ? 7 : 5
                  const alpha = clamp(tr.confidence, 0.35, 0.95)
                  const vLen = showVectors ? (18 + tr.rel_speed_u*0.7) : 0
                  const v = polarToXY(p.x, p.y, vLen, tr.heading, 1)

                  const color = tr.flags.includes('LOST') ? 'rgba(239,68,68,.95)'
                              : tr.flags.includes('OCCLUDED') ? 'rgba(245,158,11,.95)'
                              : 'rgba(34,197,94,.95)'

                  return (
                    <g key={tr.id} style={{ cursor:'pointer' }} onClick={()=>setSelectedId(tr.id)}>
                      {showVectors ? (
                        <line x1={p.x} y1={p.y} x2={v.x} y2={v.y}
                              stroke={isSel ? 'rgba(56,189,248,.95)' : 'rgba(255,255,255,.22)'} strokeWidth={isSel ? 2 : 1} />
                      ) : null}
                      <circle cx={p.x} cy={p.y} r={s} fill={color} opacity={alpha} />
                      <circle cx={p.x} cy={p.y} r={s+12} fill={color} opacity={isSel ? 0.08 : 0.03} />
                      <text x={p.x+10} y={p.y-10} fontSize="11" fill={isSel ? 'rgba(56,189,248,.95)' : 'rgba(159,178,209,.9)'}>
                        {tr.callsign}
                      </text>
                    </g>
                  )
                })}

                {/* Center */}
                <circle cx={cx} cy={cy} r="4" fill="rgba(34,197,94,.95)" />
              </svg>

              <div className="legendRow">
                <div className="legend"><span className="swatch"></span> Normal</div>
                <div className="legend"><span className="swatch3"></span> Occluded / low conf</div>
                <div className="legend"><span className="swatch2"></span> Selected vector</div>
                <div className="legend">Altitude shown as <b style={{ marginLeft: 6, fontFamily:'var(--mono)' }}>LOW/MED/HIGH</b> (inferred)</div>
              </div>

              <div style={{ display:'flex', gap:10, marginTop:10, width:'100%', alignItems:'center', justifyContent:'space-between' }}>
                <div className="small">Display</div>
                <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                  <button className="btn" onClick={()=>setRings(r=>clamp(r-1,3,7))}>- Ring</button>
                  <button className="btn" onClick={()=>setRings(r=>clamp(r+1,3,7))}>+ Ring</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT: Inspector + table */}
        <div className={`panel workspacePanel${expandedPanel === 'inspector' ? ' panelExpanded' : ''}`}>
          <div className="panelHeader">
            <div className="panelTitle">
              <div className="t">Track Inspector</div>
              <div className="d">Commander-ready detail + notes per track</div>
            </div>
            <div className="kpi"><span>Integrity: ON</span></div>
            <button className="btn" onClick={()=>setExpandedPanel(expandedPanel === 'inspector' ? null : 'inspector')}>
              {expandedPanel === 'inspector' ? 'Restore' : 'Expand'}
            </button>
          </div>

          <div className="panelBody">
            <div style={{ display:'flex', gap:8, alignItems:'center' }}>
              <input
                className="select"
                style={{ flex:1 }}
                placeholder="Search callsign or type…"
                value={search}
                onChange={(e)=>setSearch(e.target.value)}
              />
              <button className="btn" onClick={()=>setAlertsOnly(v=>!v)}>{alertsOnly ? 'Alerts only' : 'All tracks'}</button>
            </div>

            <div style={{ marginTop: 10 }}>
              {selected ? (
                <>
                  <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:10 }}>
                    <div style={{ fontSize:16, fontWeight:750 }}>{selected.callsign}</div>
                    <span className={`badge ${sev(selected)}`}>
                      <span className="m">{typeLabel(selected.type)}</span>
                    </span>
                  </div>

                  <div className="inspectorGrid" style={{ marginTop: 10 }}>
                    <div className="cardMini"><div className="k">Bearing</div><div className="v">{fmt(selected.bearing,0)}°</div></div>
                    <div className="cardMini"><div className="k">Range</div><div className="v">{fmt(selected.range_u,2)} u</div></div>
                    <div className="cardMini"><div className="k">Heading</div><div className="v">{fmt(selected.heading,0)}°</div></div>
                    <div className="cardMini"><div className="k">Rel Speed</div><div className="v">{fmt(selected.rel_speed_u,0)} u/s</div></div>
                    <div className="cardMini"><div className="k">Altitude Band</div><div className="v">{selected.alt_band}</div></div>
                    <div className="cardMini"><div className="k">Confidence</div><div className="v">{fmt(selected.confidence,2)}</div></div>
                  </div>

                  <div className="notes">
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                      <div style={{ fontSize:12, fontWeight:700 }}>Commander Notes</div>
                      <div className="small">Saved locally (prototype)</div>
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <textarea
                        value={notesById[selected.id] || ''}
                        onChange={(e)=> setNotesById(n => ({...n, [selected.id]: e.target.value}))}
                        placeholder="Observations, anomalies, cluster notes, confidence issues, cadet tasking…"
                      />
                    </div>
                  </div>
                </>
              ) : (
                <div className="small">Select a track on the radar or table.</div>
              )}
            </div>

            <div style={{ marginTop: 12, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <div style={{ fontSize:12, fontWeight:750 }}>Track List</div>
              <div className="small">{filtered.length} shown</div>
            </div>

            <div style={{ marginTop: 8, maxHeight: 260, overflow:'auto', borderRadius: 18, border:'1px solid rgba(255,255,255,.10)', background:'rgba(0,0,0,.10)' }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Callsign</th>
                    <th>Type</th>
                    <th>Conf</th>
                    <th>Bear</th>
                    <th>Alt</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(tr=>{
                    const isSel = tr.id===selectedId
                    const bClass = sev(tr)
                    return (
                      <tr key={tr.id} onClick={()=>setSelectedId(tr.id)} style={{ background: isSel ? 'rgba(56,189,248,.08)' : undefined }}>
                        <td style={{ fontWeight:650 }}>{tr.callsign}</td>
                        <td><span className="badge"><span className="m">{typeLabel(tr.type)}</span></span></td>
                        <td><span className={`badge ${bClass}`}><span className="m">{fmt(tr.confidence,2)}</span></span></td>
                        <td style={{ fontFamily:'var(--mono)' }}>{fmt(tr.bearing,0)}°</td>
                        <td><span className="badge">{tr.alt_band}</span></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

          </div>
        </div>
      </div>

      <div className="bottom">
        <div className="log">
          {logRows.map((r, idx)=> (
            <div key={idx} className="logRow">
              <div className="ts">{r.ts}</div>
              <div className="msg">{r.msg}</div>
            </div>
          ))}
        </div>

        <div className="rightMini">
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
            <div style={{ fontSize:12, fontWeight:800 }}>Operational Snapshot</div>
            <div className="small">Training mode</div>
          </div>
          <div className="miniKpis">
            <div className="k"><div className="l">Tracks</div><div className="n">{tracks.length}</div></div>
            <div className="k"><div className="l">Flagged</div><div className="n">{alertCount}</div></div>
            <div className="k"><div className="l">Clusters</div><div className="n">{clusters.length}</div></div>
          </div>

          <div style={{ marginTop: 10 }} className="small">
            UX pillars: calm legibility • commander truthfulness • cadet learning loops • AAR ready.
          </div>
        </div>
      </div>
    </div>
  )
}
