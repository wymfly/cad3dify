import * as THREE from 'three';

/**
 * Custom ShaderMaterial for DfAM heatmap visualization.
 * Maps vertex color R channel to green->yellow->red gradient.
 * R=0.0 -> red (danger), R=0.5 -> yellow (warning), R=1.0 -> green (safe).
 */
export function createDfamMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: `
      attribute vec4 color;
      varying float vRisk;
      void main() {
        vRisk = color.r;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying float vRisk;
      void main() {
        vec3 red    = vec3(0.863, 0.149, 0.149);
        vec3 yellow = vec3(0.918, 0.702, 0.031);
        vec3 green  = vec3(0.133, 0.773, 0.369);
        vec3 col;
        if (vRisk < 0.5) {
          col = mix(red, yellow, vRisk * 2.0);
        } else {
          col = mix(yellow, green, (vRisk - 0.5) * 2.0);
        }
        gl_FragColor = vec4(col, 1.0);
      }
    `,
    vertexColors: true,
  });
}

export interface DfamMeshMeta {
  analysis_type: 'wall_thickness' | 'overhang';
  threshold: number;
  min_value: number | null;
  max_value: number | null;
  vertices_at_risk_count: number;
  vertices_at_risk_percent: number;
}
