import React, { useState } from 'react'

type MedicalImageViewerProps = {
  src: string
  alt?: string
  caption?: string
  annotationUrl?: string
}

export const MedicalImageViewer: React.FC<MedicalImageViewerProps> = ({
  src,
  alt = 'Imagerie médicale',
  caption,
  annotationUrl,
}) => {
  const [zoom, setZoom] = useState<number>(1)
  const [brightness, setBrightness] = useState<number>(100)
  const [contrast, setContrast] = useState<number>(100)
  const [showAnnotation, setShowAnnotation] = useState<boolean>(true)

  const handleReset = () => {
    setZoom(1)
    setBrightness(100)
    setContrast(100)
    setShowAnnotation(true)
  }

  return (
    <div className="medical-viewer-container" style={{ border: '1px solid var(--border, #333)', borderRadius: '8px', padding: '12px', background: '#0f0f14', color: '#f4f4f6', margin: '12px 0' }}>
      <div className="medical-viewer-controls" style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center', marginBottom: '8px', fontSize: '12px' }}>
        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
          <span>Zoom: {(zoom * 100).toFixed(0)}%</span>
          <button type="button" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} style={{ padding: '2px 8px', borderRadius: '4px', cursor: 'pointer' }}>-</button>
          <button type="button" onClick={() => setZoom((z) => Math.min(3, z + 0.25))} style={{ padding: '2px 8px', borderRadius: '4px', cursor: 'pointer' }}>+</button>
        </div>

        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <span>Luminosité:</span>
          <input
            type="range"
            min="50"
            max="150"
            value={brightness}
            onChange={(e) => setBrightness(Number(e.target.value))}
            style={{ width: '80px' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <span>Contraste:</span>
          <input
            type="range"
            min="50"
            max="150"
            value={contrast}
            onChange={(e) => setContrast(Number(e.target.value))}
            style={{ width: '80px' }}
          />
        </div>

        {annotationUrl && (
          <label style={{ display: 'flex', gap: '4px', alignItems: 'center', cursor: 'pointer', marginLeft: 'auto' }}>
            <input
              type="checkbox"
              checked={showAnnotation}
              onChange={(e) => setShowAnnotation(e.target.checked)}
            />
            <span>Afficher calque d'annotation</span>
          </label>
        )}

        <button
          type="button"
          onClick={handleReset}
          style={{ padding: '2px 8px', borderRadius: '4px', background: '#333', color: '#fff', cursor: 'pointer', marginLeft: annotationUrl ? '0' : 'auto' }}
        >
          Réinitialiser
        </button>
      </div>

      <div
        className="medical-viewer-viewport"
        style={{
          position: 'relative',
          overflow: 'hidden',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '260px',
          maxHeight: '500px',
          background: '#000',
          borderRadius: '6px',
        }}
      >
        <img
          src={src}
          alt={alt}
          style={{
            transform: `scale(${zoom})`,
            filter: `brightness(${brightness}%) contrast(${contrast}%)`,
            transition: 'transform 120ms ease-out, filter 120ms ease-out',
            maxWidth: '100%',
            maxHeight: '100%',
            objectFit: 'contain',
          }}
        />

        {annotationUrl && showAnnotation && (
          <img
            src={annotationUrl}
            alt="Calque d'annotation"
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              pointerEvents: 'none',
              transform: `scale(${zoom})`,
              transition: 'transform 120ms ease-out',
              objectFit: 'contain',
            }}
          />
        )}
      </div>

      {caption && <div style={{ fontSize: '11.5px', color: '#a0a0ab', marginTop: '6px', fontStyle: 'italic' }}>{caption}</div>}
    </div>
  )
}
