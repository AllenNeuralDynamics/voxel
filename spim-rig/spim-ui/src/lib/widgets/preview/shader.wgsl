struct VertexOutput {
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
    enabled: u32,           // Can be used to disable the channel if needed.
};

const MAX_CHANNELS: u32 = 4;

struct GlobalSettings {
    transform: Transform2D, // Global transform settings.
    layout: u32,            // 0: overlayed, 1: 2X2 grid, etc.
    num_channels: u32,      // Number of active channels, must be <= MAX_CHANNELS.
    channels: array<ChannelSettings, MAX_CHANNELS>, // Per-channel intensity/LUT settings.
};

@group(0) @binding(0) var<uniform> settings : GlobalSettings;
@group(0) @binding(1) var frameSampler : sampler;

// Bindings for channel textures and LUTs.
@group(0) @binding(2) var frameTexture0 : texture_2d<f32>;
@group(0) @binding(3) var colormapTexture0 : texture_2d<f32>;

@group(0) @binding(4) var frameTexture1 : texture_2d<f32>;
@group(0) @binding(5) var colormapTexture1 : texture_2d<f32>;

@group(0) @binding(6) var frameTexture2 : texture_2d<f32>;
@group(0) @binding(7) var colormapTexture2 : texture_2d<f32>;

@group(0) @binding(8) var frameTexture3 : texture_2d<f32>;
@group(0) @binding(9) var colormapTexture3 : texture_2d<f32>;

//---------------------------------------------------------------------
// Utility: Linear interpolation.
fn lerp(a: f32, b: f32, t: f32) -> f32 {
    return a + t * (b - a);
}

//---------------------------------------------------------------------
// Global transform applied in the vertex shader.
// In this example, a k value of 0 applies no zoom (scale = 1.0)
// and a k value of 1 applies maximum zoom (scale = 0.25, i.e. 4× zoom in).
fn apply_transform(uv: vec2<f32>, transform: Transform2D) -> vec2<f32> {
    let minScale: f32 = 0.25; // Adjust this value for maximum zoom.
    let scale: f32 = lerp(1.0, minScale, transform.k);
    return uv * scale + vec2<f32>(transform.x, transform.y);
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

    // Use the transformed UV coordinates from the vertex shader.
    for (var i: u32 = 0u; i < settings.num_channels; i = i + 1u) {
        let ch = settings.channels[i];
        var channelColor: vec4<f32>;

        if (i == 0u) {
            channelColor = textureSample(frameTexture0, frameSampler, input.fragUV);
            let remapped = remap_intensity(channelColor.r, ch.intensity_min, ch.intensity_max);
            if (ch.applyLUT == 1u) {
                channelColor = apply_lut(remapped, channelColor, colormapTexture0);
            } else {
                channelColor = vec4<f32>(vec3(remapped), channelColor.a);
            }
        } else if (i == 1u) {
            channelColor = textureSample(frameTexture1, frameSampler, input.fragUV);
            let remapped = remap_intensity(channelColor.r, ch.intensity_min, ch.intensity_max);
            if (ch.applyLUT == 1u) {
                channelColor = apply_lut(remapped, channelColor, colormapTexture1);
            } else {
                channelColor = vec4<f32>(vec3(remapped), channelColor.a);
            }
        } else if (i == 2u) {
            channelColor = textureSample(frameTexture2, frameSampler, input.fragUV);
            let remapped = remap_intensity(channelColor.r, ch.intensity_min, ch.intensity_max);
            if (ch.applyLUT == 1u) {
                channelColor = apply_lut(remapped, channelColor, colormapTexture2);
            } else {
                channelColor = vec4<f32>(vec3(remapped), channelColor.a);
            }
        } else if (i == 3u) {
            channelColor = textureSample(frameTexture3, frameSampler, input.fragUV);
            let remapped = remap_intensity(channelColor.r, ch.intensity_min, ch.intensity_max);
            if (ch.applyLUT == 1u) {
                channelColor = apply_lut(remapped, channelColor, colormapTexture3);
            } else {
                channelColor = vec4<f32>(vec3(remapped), channelColor.a);
            }
        }
        // Composite the channel color over the final color using a simple "over" operator.
        finalColor = channelColor + finalColor * (1.0 - channelColor.a);
    }

    return finalColor;
}
