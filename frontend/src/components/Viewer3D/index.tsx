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

export default function Viewer3D({ modelUrl, wireframe: externalWireframe, onLoaded }: Viewer3DProps) {
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

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        minHeight: 400,
        position: 'relative',
        background: '#f5f5f5',
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      <Canvas
        camera={{ position: [3, 3, 3], fov: 45, near: 0.1, far: 1000 }}
        style={{ width: '100%', height: '100%' }}
      >
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 5, 5]} intensity={1} />
        <directionalLight position={[-3, -3, -3]} intensity={0.3} />
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
            <meshStandardMaterial color="#d9d9d9" wireframe={wireframe} />
          </mesh>
        )}
        <gridHelper args={[10, 10, '#ccc', '#eee']} />
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
          <div style={{ marginTop: 8, color: '#999', fontSize: 13 }}>
            等待模型加载...
          </div>
        </div>
      )}

      <ViewControls
        wireframe={wireframe}
        onWireframeToggle={() => setInternalWireframe((v) => !v)}
        onViewChange={handleViewChange}
      />
    </div>
  );
}
