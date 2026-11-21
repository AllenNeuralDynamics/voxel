struct Uniforms {
  surface: vec4f,
  display: vec4f,
  view_channel_offset: vec4f,
  channel: vec4f,
  overview_rect: vec4f,
  overview_size_flags: vec4f,
  detail_rect: vec4f,
  detail_size_flags: vec4f,
  levels: vec4f,
}

@group(0) @binding(0) var<uniform> uniforms: Uniforms;
@group(0) @binding(1) var overview_low: texture_2d<u32>;
@group(0) @binding(2) var overview_high: texture_2d<u32>;
@group(0) @binding(3) var detail_low: texture_2d<u32>;
@group(0) @binding(4) var detail_high: texture_2d<u32>;
@group(0) @binding(5) var color_lut: texture_2d<f32>;
@group(0) @binding(6) var color_sampler: sampler;

struct VertexOutput {
  @builtin(position) position: vec4f,
}

@vertex
fn vertex_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
  let positions = array<vec2f, 3>(
    vec2f(-1.0, -1.0),
    vec2f(3.0, -1.0),
    vec2f(-1.0, 3.0),
  );
  var output: VertexOutput;
  output.position = vec4f(positions[vertex_index], 0.0, 1.0);
  return output;
}

fn inside(point: vec2f, rect: vec4f) -> bool {
  return all(point >= rect.xy) && all(point < rect.xy + rect.zw);
}

fn sensor_coordinate(stage: vec2f, rotation: f32) -> vec2f {
  if (rotation < 0.5) {
    return stage;
  }
  if (rotation < 1.5) {
    return vec2f(stage.y, 1.0 - stage.x);
  }
  if (rotation < 2.5) {
    return vec2f(1.0 - stage.x, 1.0 - stage.y);
  }
  return vec2f(1.0 - stage.y, stage.x);
}

fn overview_value(sensor: vec2f) -> u32 {
  let uv = clamp((sensor - uniforms.overview_rect.xy) / uniforms.overview_rect.zw, vec2f(0.0), vec2f(0.999999));
  let size = vec2u(uniforms.overview_size_flags.xy);
  let pixel = vec2i(min(vec2u(uv * vec2f(size)), size - vec2u(1u)));
  return textureLoad(overview_low, pixel, 0).r | (textureLoad(overview_high, pixel, 0).r << 8u);
}

fn detail_value(sensor: vec2f) -> u32 {
  let uv = clamp((sensor - uniforms.detail_rect.xy) / uniforms.detail_rect.zw, vec2f(0.0), vec2f(0.999999));
  let size = vec2u(uniforms.detail_size_flags.xy);
  let pixel = vec2i(min(vec2u(uv * vec2f(size)), size - vec2u(1u)));
  return textureLoad(detail_low, pixel, 0).r | (textureLoad(detail_high, pixel, 0).r << 8u);
}

@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
  let pixel = input.position.xy;
  let draw_origin = uniforms.surface.zw;
  let draw_size = uniforms.display.xy;
  if (any(pixel < draw_origin) || any(pixel >= draw_origin + draw_size)) {
    return vec4f(0.0);
  }

  let bounding_coordinate = uniforms.display.zw + ((pixel - draw_origin) / draw_size) * uniforms.view_channel_offset.xy;
  let channel_coordinate = (bounding_coordinate - uniforms.view_channel_offset.zw) / uniforms.channel.xy;
  if (any(channel_coordinate < vec2f(0.0)) || any(channel_coordinate >= vec2f(1.0))) {
    return vec4f(0.0);
  }

  let sensor = sensor_coordinate(channel_coordinate, uniforms.channel.z);
  var raw: u32;
  if (uniforms.detail_size_flags.z > 0.5 && inside(sensor, uniforms.detail_rect)) {
    raw = detail_value(sensor);
  } else if (uniforms.overview_size_flags.z > 0.5 && inside(sensor, uniforms.overview_rect)) {
    raw = overview_value(sensor);
  } else {
    return vec4f(0.0);
  }

  let normalized = f32(raw) / uniforms.channel.w;
  let width = max(uniforms.levels.y - uniforms.levels.x, 1.0 / uniforms.channel.w);
  let mapped = clamp((normalized - uniforms.levels.x) / width, 0.0, 1.0);
  if (mapped <= 0.0) {
    return vec4f(0.0, 0.0, 0.0, 1.0);
  }
  let color = textureSampleLevel(color_lut, color_sampler, vec2f(mapped, 0.5), 0.0);
  return vec4f(color.rgb, 1.0);
}
