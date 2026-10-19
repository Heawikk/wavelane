#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float time;      // seconds of animation, already sped up by loudness
    float level;     // overall loudness, 0..1
    float bass;      // 0..1
    float mid;       // 0..1
    float treble;    // 0..1
    float aspect;    // width / height of the item
    float flash;     // 0..1, a pulse of flashColor passing through the blobs
    vec4 colorA;
    vec4 colorB;
    vec4 colorC;
    vec4 background;
    vec4 flashColor;
} ubuf;

// A soft "metaball": near 1 close to the centre, falling off smoothly. Summing
// several of them gives a field whose iso-lines merge and split as the centres
// drift, which reads as liquid rather than as separate circles.
float ball(vec2 p, vec2 centre, float radius)
{
    vec2 d = p - centre;
    return (radius * radius) / (dot(d, d) + 0.0008);
}

void main()
{
    // Centred coordinates, y spanning -0.5..0.5 and x scaled by the aspect.
    vec2 p = (qt_TexCoord0 - 0.5) * vec2(ubuf.aspect, 1.0);
    float t = ubuf.time;

    // Warp the plane a little, so the blobs ripple instead of staying round.
    vec2 w = p;
    w += 0.070 * vec2(sin(p.y * 3.6 + t * 0.55), cos(p.x * 3.6 - t * 0.47));
    w += (0.020 + 0.045 * ubuf.mid) * vec2(sin(p.y * 8.5 - t * 0.9), cos(p.x * 8.5 + t * 0.8));

    // The beat swells the blobs; the rest of the music brightens them.
    float swell = 1.0 + 0.55 * ubuf.bass + 0.30 * ubuf.flash;

    vec2 c1 = vec2(0.30 * sin(t * 0.31 + 0.3), 0.20 * cos(t * 0.43)) * vec2(ubuf.aspect * 0.8, 1.0);
    vec2 c2 = vec2(-0.32 * cos(t * 0.27 + 1.1), 0.22 * sin(t * 0.37 + 0.6)) * vec2(ubuf.aspect * 0.8, 1.0);
    vec2 c3 = vec2(0.20 * sin(t * 0.47 + 2.1), -0.26 * cos(t * 0.33 + 0.4)) * vec2(ubuf.aspect * 0.8, 1.0);
    vec2 c4 = vec2(-0.12 * cos(t * 0.53 + 0.8), 0.16 * sin(t * 0.61 + 1.7)) * vec2(ubuf.aspect * 0.8, 1.0);
    vec2 c5 = vec2(0.36 * cos(t * 0.23 + 2.6), 0.12 * sin(t * 0.49 + 0.2)) * vec2(ubuf.aspect * 0.8, 1.0);

    float f1 = ball(w, c1, 0.150 * swell);
    float f2 = ball(w, c2, 0.135 * swell);
    float f3 = ball(w, c3, 0.115 * (1.0 + 0.9 * ubuf.mid));
    float f4 = ball(w, c4, 0.090 * (1.0 + 1.2 * ubuf.treble));
    float f5 = ball(w, c5, 0.100 * swell);

    float field = f1 + f2 + f3 + f4 + f5;

    // Each blob contributes its own colour, weighted by how much of the field it makes.
    vec3 mixed = ubuf.colorA.rgb * f1
               + ubuf.colorB.rgb * f2
               + ubuf.colorC.rgb * f3
               + mix(ubuf.colorA.rgb, ubuf.colorC.rgb, 0.5) * f4
               + mix(ubuf.colorB.rgb, ubuf.colorA.rgb, 0.5) * f5;
    vec3 tint = mixed / max(field, 0.001);
    // A reaction (a like, a dislike) washes the blobs with its colour and fades.
    tint = mix(tint, ubuf.flashColor.rgb, 0.9 * ubuf.flash);

    // A solid body where the field is strong, and a wide halo around it.
    float body = smoothstep(0.85, 2.4, field);
    float halo = 1.0 - exp(-field * 0.55);

    float energy = (0.50 + 0.36 * ubuf.level + 0.16 * ubuf.mid) * (1.0 + 0.12 * ubuf.flash);
    vec3 colour = tint * (body * 0.80 + halo * 0.30) * energy;

    // Finer ripples riding on the surface when there is treble.
    float ripple = sin((p.x + p.y) * 26.0 - t * 3.0) * sin((p.x - p.y) * 19.0 + t * 2.2);
    colour += tint * ripple * 0.035 * ubuf.treble * body;

    // Roll the brightness off instead of letting it clip: a clipped blob goes
    // flat white, a rolled-off one keeps its colour all the way to the highlight.
    colour = 1.0 - exp(-colour * 1.35);

    // Fade towards the edges so the effect has no hard border and the text stays readable.
    float vignette = smoothstep(1.15, 0.18, length(p * vec2(0.82, 1.15)));
    vec3 result = mix(ubuf.background.rgb, ubuf.background.rgb + colour, vignette);

    fragColor = vec4(result, 1.0) * ubuf.qt_Opacity;
}
