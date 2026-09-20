import { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Environment, Text, Float } from "@react-three/drei";
import * as THREE from "three";

const CAMERA_POSITION = [4, 3, 6];
const AMBIENT_INTENSITY = 0.4;
const DIR_LIGHT_POSITION = [5, 10, 5];

/**
 * The central "core" that represents the agent.
 * Its appearance changes based on the agent's state:
 *   idle       → slow rotation, cool blue
 *   thinking   → pulsing scale, warm amber
 *   searching  → fast rotation, bright green with sparks
 *   responding → gentle bob, white-blue
 */
function AgentCore({ state }) {
    const meshRef = useRef();
    const ringRef = useRef();

    const color = useMemo(() => {
        switch (state) {
            case "thinking": return "#f59e0b";
            case "searching": return "#10b981";
            case "responding": return "#60a5fa";
            default: return "#6366f1";
        }
    }, [state]);

    useFrame((_, delta) => {
        if (!meshRef.current) return;

        // Rotation speed based on state
        const speed = state === "searching" ? 4 : state === "thinking" ? 2 : 0.5;
        meshRef.current.rotation.y += delta * speed;
        meshRef.current.rotation.x += delta * speed * 0.3;

        // Scale pulse when thinking or searching
        if (state === "thinking" || state === "searching") {
            const pulse = 1 + Math.sin(Date.now() * 0.004) * 0.08;
            meshRef.current.scale.setScalar(pulse);
        } else {
            meshRef.current.scale.lerp(new THREE.Vector3(1, 1, 1), 0.1);
        }
    });

    return (
        <group>
            {/* Central icosahedron core */}
            <mesh ref={meshRef} castShadow>
                <icosahedronGeometry args={[1, 1]} />
                <meshStandardMaterial
                    color={color}
                    roughness={0.2}
                    metalness={0.8}
                    emissive={color}
                    emissiveIntensity={0.3}
                />
            </mesh>

            {/* Orbiting ring */}
            <mesh ref={ringRef} rotation={[Math.PI / 2, 0, 0]}>
                <torusGeometry args={[1.8, 0.03, 16, 64]} />
                <meshStandardMaterial
                    color={color}
                    emissive={color}
                    emissiveIntensity={0.5}
                    transparent
                    opacity={0.6}
                />
            </mesh>
        </group>
    );
}

/**
 * Search result particles that appear when a web search is triggered.
 */
function SearchParticles({ active }) {
    const pointsRef = useRef();
    const COUNT = 60;

    const positions = useMemo(() => {
        const pos = new Float32Array(COUNT * 3);
        for (let i = 0; i < COUNT; i++) {
            pos[i * 3] = (Math.random() - 0.5) * 8;
            pos[i * 3 + 1] = (Math.random() - 0.5) * 4;
            pos[i * 3 + 2] = (Math.random() - 0.5) * 8;
        }
        return pos;
    }, []);

    useFrame((_, delta) => {
        if (!pointsRef.current) return;
        const opacity = active ? 0.8 : 0.0;
        pointsRef.current.material.opacity = THREE.MathUtils.lerp(
            pointsRef.current.material.opacity,
            opacity,
            0.05
        );
        pointsRef.current.rotation.y += delta * (active ? 0.5 : 0.1);
    });

    return (
        <points ref={pointsRef}>
            <bufferGeometry>
                <bufferAttribute
                    attach="attributes-position"
                    count={COUNT}
                    array={positions}
                    itemSize={3}
                />
            </bufferGeometry>
            <pointsMaterial
                size={0.06}
                color="#10b981"
                transparent
                opacity={0}
                sizeAttenuation
            />
        </points>
    );
}

export default function AgentScene({ agentState, lastQuery }) {
    return (
        <Canvas
            camera={{ position: CAMERA_POSITION, fov: 50, near: 0.1, far: 100 }}
            shadows={{ type: THREE.PCFShadowMap }}
            dpr={[1, 2]}
        >
            <ambientLight intensity={AMBIENT_INTENSITY} />
            <directionalLight
                position={DIR_LIGHT_POSITION}
                intensity={1.2}
                castShadow
                shadow-mapSize-width={2048}
                shadow-mapSize-height={2048}
            />

            <Float speed={1.5} rotationIntensity={0.3} floatIntensity={0.5}>
                <AgentCore state={agentState} />
            </Float>

            <SearchParticles active={agentState === "searching"} />

            {/* Query label that appears during search */}
            {agentState === "searching" && lastQuery && (
                <Float speed={2} floatIntensity={0.8}>
                    <Text
                        position={[0, -2.5, 0]}
                        fontSize={0.25}
                        color="#10b981"
                        anchorX="center"
                        anchorY="middle"
                        maxWidth={6}
                    >
                        {`Searching: ${lastQuery.slice(0, 40)}${lastQuery.length > 40 ? "..." : ""}`}
                    </Text>
                </Float>
            )}

            <Environment preset="studio" />
            <OrbitControls
                enableDamping
                dampingFactor={0.05}
                minDistance={3}
                maxDistance={20}
            />
        </Canvas>
    );
}