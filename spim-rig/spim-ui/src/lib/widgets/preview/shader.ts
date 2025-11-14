/**
 * Dynamic WGSL shader generator for preview rendering
 * Generates shader code based on MAX_CHANNELS configuration
 */

export function generateShaderCode(maxChannels: number): string {
	// Generate texture and colormap bindings for each channel
	const generateBindings = (): string => {
		let bindings = '';
		for (let i = 0; i < maxChannels; i++) {
			const bindingStart = 2 + i * 2;
			bindings += `@group(0) @binding(${bindingStart}) var frameTexture${i} : texture_2d<f32>;\n`;
			bindings += `@group(0) @binding(${bindingStart + 1}) var colormapTexture${i} : texture_2d<f32>;\n`;
			if (i < maxChannels - 1) bindings += '\n';
		}
		return bindings;
	};

	// Generate the if-else chain for sampling textures in fragment shader
	const generateFragmentSampling = (): string => {
		let sampling = '';
		for (let i = 0; i < maxChannels; i++) {
			const ifKeyword = i === 0 ? 'if' : 'else if';
			sampling += `        ${ifKeyword} (i == ${i}u) {
            channelColor = textureSample(frameTexture${i}, frameSampler, input.fragUV);
            remapped = remap_intensity(channelColor.r, ch.intensity_min, ch.intensity_max);
            if (ch.applyLUT == 1u) {
                channelColor = apply_lut(remapped, channelColor, colormapTexture${i});
            } else {
                channelColor = vec4<f32>(vec3(remapped), channelColor.a);
            }
        }`;
			if (i < maxChannels - 1) sampling += ' ';
		}
		return sampling;
	};

	return `struct VertexOutput {
    @builtin(position) Position: vec4<f32>,
    @location(0) fragUV: vec2<f32>, // Transformed UV coordinates.
};

struct Transform2D {
    x: f32,
    y: f32,
    k: f32, // normalized: 0 = no zoom, 1 = maximum zoom.
    pad: f32,
};

struct ChannelSettings {
    intensity_min: f32,     // Minimum intensity value (black level) 0.0-1.0
    intensity_max: f32,     // Maximum intensity value (white level) 0.0-1.0
    applyLUT: u32,          // 1u to apply LUT, 0u to skip it.
    enabled: u32,           // 1u if this channel is enabled, 0u otherwise
};

const MAX_CHANNELS: u32 = ${maxChannels};

struct GlobalSettings {
    transform: Transform2D, // Global transform settings.
    display_mode: u32,      // 0: overlayed, 1: 2X2 grid, etc.
    num_channels: u32,      // Number of active channels, must be <= MAX_CHANNELS.
    pad0: u32,              // Padding to align channels to 16 bytes
    pad1: u32,              // Padding to align channels to 16 bytes
    @align(16) channels: array<ChannelSettings, MAX_CHANNELS>, // Per-channel intensity/LUT settings.
};

@group(0) @binding(0) var<uniform> settings : GlobalSettings;
@group(0) @binding(1) var frameSampler : sampler;

// Bindings for channel textures and LUTs.
${generateBindings()}

//---------------------------------------------------------------------
// Global transform applied in the vertex shader.
// k=0: no zoom (viewSize=1.0, full image visible)
// k increases: viewSize decreases, zooming in
// (x,y) is the top-left corner of the visible region
fn apply_transform(uv: vec2<f32>, transform: Transform2D) -> vec2<f32> {
    // Calculate the size of the visible viewport (1.0 = full image, smaller = zoomed in)
    let viewSize: f32 = 1.0 - clamp(transform.k, 0.0, 1.0);

    // Clamp transform.x and transform.y to valid range [0, 1-viewSize]
    let clampedX: f32 = clamp(transform.x, 0.0, 1.0 - viewSize);
    let clampedY: f32 = clamp(transform.y, 0.0, 1.0 - viewSize);

    // Scale UV by viewSize and offset by top-left corner (x,y)
    // This ensures final UVs stay within [0,1] range
    let finalUV = uv * viewSize + vec2<f32>(clampedX, clampedY);

    // Extra safety: clamp final UV to [0,1] to prevent any sampling artifacts
    return clamp(finalUV, vec2<f32>(0.0), vec2<f32>(1.0));
}

//---------------------------------------------------------------------
// Vertex Shader: Applies the global transform to UV coordinates.
@vertex
fn vs_main(@builtin(vertex_index) VertexIndex: u32) -> VertexOutput {
    const pos = array<vec2<f32>, 6>(
        vec2( 1.0,  1.0),
        vec2( 1.0, -1.0),
        vec2(-1.0, -1.0),
        vec2( 1.0,  1.0),
        vec2(-1.0, -1.0),
        vec2(-1.0,  1.0)
    );

    const uv = array<vec2<f32>, 6>(
        vec2(1.0, 0.0),
        vec2(1.0, 1.0),
        vec2(0.0, 1.0),
        vec2(1.0, 0.0),
        vec2(0.0, 1.0),
        vec2(0.0, 0.0)
    );

    var output: VertexOutput;
    output.Position = vec4<f32>(pos[VertexIndex], 0.0, 1.0);
    // Apply the global transform to the UV coordinates.
    output.fragUV = apply_transform(uv[VertexIndex], settings.transform);
    return output;
}

//---------------------------------------------------------------------
// Map raw intensity to display range using min/max intensity values.
// This is the microscopy-friendly way to control dynamic range.
//
// intensity: raw pixel value (0.0 - 1.0)
// min: black level - values at or below this map to 0
// max: white level - values at or above this map to 1
//
// Returns: remapped intensity (0.0 - 1.0)
fn remap_intensity(intensity: f32, min: f32, max: f32) -> f32 {
    if (max <= min) {
        return 0.0; // Avoid division by zero
    }
    return clamp((intensity - min) / (max - min), 0.0, 1.0);
}

//---------------------------------------------------------------------
// Apply a lookup table (LUT) if enabled.
fn apply_lut(remapped: f32, baseColor: vec4<f32>, lutTex: texture_2d<f32>) -> vec4<f32> {
    let lutColor: vec4<f32> = textureSample(lutTex, frameSampler, vec2<f32>(remapped, 0.5));
    return vec4<f32>(lutColor.rgb, baseColor.a);
}

//---------------------------------------------------------------------
// Fragment Shader: Uses already-transformed UVs from the vertex shader.
@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    var finalColor: vec4<f32> = vec4<f32>(0.0);

    // Loop through all possible channels and check if each is enabled
    for (var i: u32 = 0u; i < MAX_CHANNELS; i = i + 1u) {
        let ch = settings.channels[i];

        // Skip disabled channels
        if (ch.enabled == 0u) {
            continue;
        }

        var channelColor: vec4<f32>;
        var remapped: f32;

${generateFragmentSampling()}

        // Additive blending (typical for fluorescence microscopy)
        finalColor = finalColor + channelColor;
    }

    // Clamp to prevent oversaturation
    return clamp(finalColor, vec4<f32>(0.0), vec4<f32>(1.0));
}
`;
}
