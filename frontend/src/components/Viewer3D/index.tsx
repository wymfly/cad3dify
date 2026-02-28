import { useState, useRef, useCallback, useEffect, Suspense } from 'react';
import { Canvas, useThree, useLoader } from '@react-three/fiber';
import { OrbitControls, Center, Environment } from '@react-three/drei';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import * as THREE from 'three';
import { Spin } from 'antd';
import ViewControls from './ViewControls.tsx';

interface Viewer3DProps {
  modelUrl: string | null;
  wireframe?: boolean;
  darkMode?: boolean;
  previewLoading?: boolean;
  previewError?: string | null;
  previewTimedOut?: boolean;
  onRetryPreview?: () => void;
  onLoaded?: () => void;
}

interface ModelProps {
  url: string;
  wireframe: boolean;
  onLoaded?: () => void;
}

function Model({ url, wireframe, onLoaded }: ModelProps) {
  const gltf = useLoader(GLTFLoader, url);

  // Apply wireframe to all meshes
  gltf.scene.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      if (Array.isArray(child.material)) {
        child.material.forEach((mat) => {
          mat.wireframe = wireframe;
        });
      } else {
        child.material.wireframe = wireframe;
      }
    }
  });

  useEffect(() => {
    if (onLoaded) onLoaded();
  }, [url, onLoaded]);

  return (
    <Center>
      <primitive object={gltf.scene} />
    </Center>
  );
}

interface CameraControllerProps {
  targetPosition: [number, number, number] | null;
  onAnimationDone: () => void;
}

function CameraController({ targetPosition, onAnimationDone }: CameraControllerProps) {
  const { camera } = useThree();

  if (targetPosition) {
    // Scale position based on current distance to keep the model in view
    const currentDistance = camera.position.length();
    const targetVec = new THREE.Vector3(...targetPosition).normalize().multiplyScalar(currentDistance);
    camera.position.copy(targetVec);
    camera.lookAt(0, 0, 0);
    onAnimationDone();
  }

  return null;
}

export default function Viewer3D({
  modelUrl,
  wireframe: externalWireframe,
  darkMode = false,
  previewLoading = false,
  previewError,
  previewTimedOut = false,
  onRetryPreview,
  onLoaded,
}: Viewer3DProps) {
  const [internalWireframe, setInternalWireframe] = useState(false);
  const [cameraTarget, setCameraTarget] = useState<[number, number, number] | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const wireframe = externalWireframe ?? internalWireframe;

  const handleViewChange = useCallback((position: [number, number, number]) => {
    setCameraTarget(position);
  }, []);

  const handleAnimationDone = useCallback(() => {
    setCameraTarget(null);
  }, []);

  // 暗色模式配置
  const bgColor = darkMode ? '#0a0a0a' : '#f0f0f0';
  const ambientIntensity = darkMode ? 0.3 : 0.5;
  const gridColors: [string, string] = darkMode ? ['#333', '#222'] : ['#ccc', '#eee'];
  const placeholderColor = darkMode ? '#444' : '#d9d9d9';

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        minHeight: 400,
        position: 'relative',
        background: bgColor,
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      <Canvas
        camera={{ position: [3, 3, 3], fov: 45, near: 0.1, far: 1000 }}
        style={{ width: '100%', height: '100%' }}
      >
        <color attach="background" args={[bgColor]} />
        <ambientLight intensity={ambientIntensity} />
        <directionalLight position={[5, 5, 5]} intensity={darkMode ? 0.8 : 1} />
        <directionalLight position={[-3, -3, -3]} intensity={darkMode ? 0.2 : 0.3} />
        <Environment preset="studio" />
        <OrbitControls
          enableDamping
          dampingFactor={0.1}
          minDistance={1}
          maxDistance={100}
        />
        <CameraController
          targetPosition={cameraTarget}
          onAnimationDone={handleAnimationDone}
        />
        {modelUrl && (
          <Suspense fallback={null}>
            <Model url={modelUrl} wireframe={wireframe} onLoaded={onLoaded} />
          </Suspense>
        )}
        {!modelUrl && (
          <mesh>
            <boxGeometry args={[1, 1, 1]} />
            <meshStandardMaterial color={placeholderColor} wireframe={wireframe} />
          </mesh>
        )}
        <gridHelper key={darkMode ? 'dark' : 'light'} args={[10, 10, gridColors[0], gridColors[1]]} />
      </Canvas>

      {!modelUrl && (
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            textAlign: 'center',
            pointerEvents: 'none',
          }}
        >
          <Spin size="default" />
          <div style={{ marginTop: 8, color: darkMode ? '#666' : '#999', fontSize: 13 }}>
            等待模型加载...
          </div>
        </div>
      )}

      <ViewControls
        wireframe={wireframe}
        darkMode={darkMode}
        onWireframeToggle={() => setInternalWireframe((v) => !v)}
        onViewChange={handleViewChange}
      />

      {/* Preview loading overlay */}
      {previewLoading && modelUrl && (
        <div
          style={{
            position: 'absolute',
            top: 12,
            right: 12,
            background: darkMode ? 'rgba(0,0,0,0.7)' : 'rgba(255,255,255,0.85)',
            borderRadius: 6,
            padding: '6px 12px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 12,
            color: darkMode ? '#aaa' : '#666',
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
          }}
        >
          <Spin size="small" />
          预览更新中...
        </div>
      )}

      {/* Timeout / error overlay */}
      {(previewTimedOut || previewError) && !previewLoading && (
        <div
          style={{
            position: 'absolute',
            top: 12,
            right: 12,
            background: darkMode ? 'rgba(0,0,0,0.8)' : 'rgba(255,255,255,0.9)',
            borderRadius: 6,
            padding: '8px 12px',
            fontSize: 12,
            color: previewTimedOut ? (darkMode ? '#faad14' : '#d48806') : '#ff4d4f',
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
            maxWidth: 200,
          }}
        >
          <div>{previewTimedOut ? '预览超时' : '预览不可用'}</div>
          {previewError && (
            <div style={{ fontSize: 11, marginTop: 2, opacity: 0.8 }}>
              {previewError}
            </div>
          )}
          {onRetryPreview && (
            <button
              onClick={onRetryPreview}
              style={{
                marginTop: 4,
                padding: '2px 8px',
                fontSize: 11,
                border: '1px solid currentColor',
                borderRadius: 4,
                background: 'transparent',
                color: 'inherit',
                cursor: 'pointer',
              }}
            >
              重试
            </button>
          )}
        </div>
      )}
    </div>
  );
}
