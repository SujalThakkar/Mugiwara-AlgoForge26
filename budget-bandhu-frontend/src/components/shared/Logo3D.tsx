'use client'

import React, { useRef, useState, useEffect, useCallback, memo, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { useGLTF, OrbitControls } from '@react-three/drei'
import { motion, AnimatePresence } from 'framer-motion'
import * as THREE from 'three'

// ═══════════════════════════════════════
// 1. CORE 3D SETUP — ROTATING MODEL
// ═══════════════════════════════════════
interface RotatingModelProps {
  url: string
  onLoad?: () => void
  rotationSpeed?: number
}

const RotatingModel = memo(function RotatingModel({
  url,
  onLoad,
  rotationSpeed = 0.6
}: RotatingModelProps) {
  // Use GLTF with optional Draco (if handled by @react-three/drei's useGLTF default)
  const { scene } = useGLTF(url)
  const meshRef = useRef<THREE.Group>(null)

  useEffect(() => {
    if (scene) {
      onLoad?.()
    }
  }, [scene, onLoad])

  useFrame((state, delta) => {
    if (meshRef.current) {
      // Delta-time based rotation for frame-rate independence
      meshRef.current.rotation.y += delta * rotationSpeed
    }
  })

  return (
    <primitive
      ref={meshRef}
      object={scene}
      scale={[1.8, 1.8, 1.8]}
      position={[0, -0.5, 0]}
    />
  )
})

// ═══════════════════════════════════════
// 2. LIGHTING SETUP FOR PURPLE MODEL
// ═══════════════════════════════════════
function Lighting() {
  return (
    <>
      <ambientLight intensity={1.5} />

      {/* Target purple pop with key and rim lights */}
      <directionalLight
        position={[5, 5, 5]}
        intensity={2}
        castShadow={false}
      />

      <directionalLight
        position={[-3, -2, -3]}
        intensity={0.8}
        color="#c4b5fd"
      />

      <pointLight
        position={[2, 3, 2]}
        intensity={1.5}
        color="#a855f7"
      />

      <pointLight
        position={[-2, -1, 2]}
        intensity={0.8}
        color="#2dd4bf"
      />

      <pointLight
        position={[0, 5, 0]}
        intensity={1}
        color="#a855f7"
      />
    </>
  )
}

// ═══════════════════════════════════════
// 3. LOGO3D CANVAS COMPONENT
// ═══════════════════════════════════════
interface Logo3DCanvasProps {
  rotationSpeed?: number
  onLoad?: () => void
}

function Logo3DCanvas({ rotationSpeed = 0.6, onLoad }: Logo3DCanvasProps) {
  return (
    <Canvas
      frameloop="always"
      camera={{ position: [0, 0, 4], fov: 45 }}
      gl={{
        alpha: true,
        antialias: true,
        powerPreference: 'high-performance',
      }}
      performance={{ min: 0.5 }}
      style={{ width: '100%', height: '100%', background: 'transparent' }}
      dpr={[1, 2]}
    >
      <Lighting />
      <Suspense fallback={null}>
        <RotatingModel
          url="/logo.glb"
          onLoad={onLoad}
          rotationSpeed={rotationSpeed}
        />
      </Suspense>
      <OrbitControls
        enableZoom={false}
        enablePan={false}
        enableRotate={false}
      />
    </Canvas>
  )
}

// ═══════════════════════════════════════
// 4. MAIN EXPORT — STATE MACHINE
// ═══════════════════════════════════════
interface Logo3DProps {
  heroMode?: boolean
}

type Stage = 'preloader' | 'flight' | 'corner'

export function Logo3D({ heroMode = false }: Logo3DProps) {
  const [stage, setStage] = useState<Stage>('preloader')
  const [modelLoaded, setModelLoaded] = useState(false)
  const [isHovered, setIsHovered] = useState(false)

  // Ref to resolve the loading promise
  const modelLoadedResolverRef = useRef<((value: unknown) => void) | null>(null)

  // ═══════════════════════════════════════
  // HEROMODE BYPASS
  // ═══════════════════════════════════════
  if (heroMode) {
    return (
      <div className="w-full h-full relative">
        <Logo3DCanvas rotationSpeed={0.5} />
      </div>
    )
  }

  // ═══════════════════════════════════
  // STATE TRANSITION LOGIC
  // ═══════════════════════════════════
  useEffect(() => {
    // Minimum 4.5s preloader time
    const minTimer = new Promise(res => setTimeout(res, 4500))

    // Model load promise
    const loadPromise = new Promise(res => {
      if (modelLoaded) res(null)
      else modelLoadedResolverRef.current = res
    })

    // Transition preloader -> flight -> corner
    Promise.all([minTimer, loadPromise]).then(() => {
      setStage('flight')

      // Page content visible trigger
      document.body.classList.add('page-visible')

      // Flight duration 1.2s before settling into corner
      setTimeout(() => {
        setStage('corner')
      }, 1200)
    })
  }, [modelLoaded])

  const handleModelLoad = useCallback(() => {
    setModelLoaded(true)
    if (modelLoadedResolverRef.current) {
      modelLoadedResolverRef.current(null)
    }
  }, [])

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <>
      {/* STATE 1: PRELOADER OVERLAY */}
      <AnimatePresence>
        {stage === 'preloader' && (
          <motion.div
            className="fixed inset-0 z-[9999] flex flex-col items-center justify-center gap-0 overflow-hidden"
            style={{
              background: 'radial-gradient(ellipse at center, #1a0a3d 0%, #0d0520 60%, #080310 100%)'
            }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
          >
            {/* Brand Title — TOP, large and prominent */}
            <motion.div
              className="flex flex-col items-center mb-2"
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: 'easeOut' }}
            >
              <h1
                className="font-extrabold text-transparent bg-clip-text"
                style={{
                  fontSize: '2.8rem',
                  letterSpacing: '-0.02em',
                  backgroundImage: 'linear-gradient(135deg, #ffffff 0%, #c4b5fd 50%, #2dd4bf 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}
              >
                Budget Bandhu
              </h1>
              <motion.p
                className="text-purple-300/80 text-sm font-medium tracking-widest uppercase mt-1"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5 }}
              >
                Your Smart Finance Friend
              </motion.p>
            </motion.div>

            {/* 3D Pig Canvas — Reserved space in center */}
            <div className="w-[300px] h-[300px]" />

            {/* Loading Bar + status — BOTTOM */}
            <motion.div
              className="flex flex-col items-center gap-3 mt-2"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.4 }}
            >
              <div className="w-[240px] h-[3px] bg-white/10 rounded-full relative overflow-hidden">
                <motion.div
                  className="absolute inset-0 rounded-full"
                  style={{ background: 'linear-gradient(90deg, #7c3aed, #2dd4bf)' }}
                  initial={{ width: '0%' }}
                  animate={{ width: '100%' }}
                  transition={{ duration: 4.5, ease: 'easeInOut' }}
                />
              </div>
              <motion.p
                className="text-white/40 text-xs tracking-widest"
                animate={{ opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 2, repeat: Infinity }}
              >
                Loading your financial universe...
              </motion.p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* PERSISTENT CANVAS CONTAINER — fixed 300px, scale-shrinks to corner */}
      {/* Using scale transform instead of width/height to prevent 3D viewport clipping */}
      <motion.div
        initial={false}
        className="fixed z-[1000] will-change-transform"
        style={{ width: 300, height: 300 }}
        animate={stage === 'preloader' ? {
          top: '50%',
          left: '50%',
          x: '-50%',
          y: '-50%',
          scale: 1,
        } : {
          bottom: 24 - 95, // offset: 110px corner target, centered in 300px = (300-110)/2 = 95
          right: 24 - 95,
          top: 'auto',
          left: 'auto',
          x: 0,
          y: 0,
          scale: 110 / 300,  // shrink to 110px visually without changing Canvas size
        }}
        transition={{
          duration: 1.1,
          ease: [0.34, 1.1, 0.64, 1], // spring-like, smooth
        }}
      >
        <motion.div
          className={`w-full h-full relative flex items-center justify-center
            ${stage === 'corner' ? 'cursor-pointer' : ''}`}
          animate={stage === 'corner' ? {
            y: [0, -6, 0]
          } : {}}
          transition={stage === 'corner' ? {
            duration: 3,
            repeat: Infinity,
            ease: 'easeInOut'
          } : {}}
          onMouseEnter={() => stage === 'corner' && setIsHovered(true)}
          onMouseLeave={() => stage === 'corner' && setIsHovered(false)}
          onClick={() => stage === 'corner' && scrollToTop()}
          whileHover={stage === 'corner' ? {
            scale: 1.1,
            boxShadow: '0 12px 40px rgba(124,58,237,0.4)'
          } : {}}
          whileTap={stage === 'corner' ? { scale: 0.9 } : {}}
        >
          {/* Use higher rotation in corner/loaded states */}
          <Logo3DCanvas
            rotationSpeed={stage === 'preloader' ? 0.4 : 0.6}
            onLoad={handleModelLoad}
          />

          {/* Tooltip Pill */}
          <AnimatePresence>
            {(stage === 'corner' && isHovered) && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: -60 }}
                exit={{ opacity: 0, y: 10 }}
                className="absolute whitespace-nowrap bg-[#7c3aed] text-white text-[12px] font-bold px-3 py-1.5 rounded-full shadow-lg pointer-events-none"
              >
                Financial Score: 782
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </motion.div>
    </>
  )
}

// Global preloader to start fetching immediately
if (typeof window !== 'undefined') {
  useGLTF.preload('/logo.glb')
}
