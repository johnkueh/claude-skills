import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { SceneProps } from "./types";

const INTRO_FRAMES = 12; // ~0.4s fade-in
const OUTRO_FRAMES = 12;

export const Scene: React.FC<SceneProps> = ({
  id,
  imageFile,
  audioFile,
  overlay,
  captions,
  kenBurns,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentMs = (frame / fps) * 1000;

  const progress = frame / durationInFrames;

  const kenBurnsTransform = (() => {
    const scale = interpolate(progress, [0, 1], [1.0, 1.08]);
    switch (kenBurns) {
      case "zoom-in-center":
        return `scale(${scale})`;
      case "zoom-in-left": {
        const tx = interpolate(progress, [0, 1], [0, -30]);
        return `scale(${scale}) translate(${tx}px, 0)`;
      }
      case "zoom-in-right": {
        const tx = interpolate(progress, [0, 1], [0, 30]);
        return `scale(${scale}) translate(${tx}px, 0)`;
      }
      case "zoom-out-center": {
        const s2 = interpolate(progress, [0, 1], [1.08, 1.0]);
        return `scale(${s2})`;
      }
      default:
        return `scale(${scale})`;
    }
  })();

  const sceneOpacity = interpolate(
    frame,
    [0, INTRO_FRAMES, durationInFrames - OUTRO_FRAMES, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const overlayOpacity = interpolate(
    frame,
    [INTRO_FRAMES, INTRO_FRAMES + 15, durationInFrames - OUTRO_FRAMES - 15, durationInFrames - OUTRO_FRAMES],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const currentCaption = captions.find(
    (c) => currentMs >= c.startMs && currentMs <= c.endMs + 150
  );

  const imageSrc = staticFile(`images/${imageFile}`);
  const audioSrc = staticFile(`audio/${audioFile}`);

  return (
    <AbsoluteFill style={{ opacity: sceneOpacity }}>
      {/* Background image with Ken Burns */}
      <AbsoluteFill style={{ overflow: "hidden" }}>
        <Img
          src={imageSrc}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: kenBurnsTransform,
            transformOrigin: "center",
          }}
        />
      </AbsoluteFill>

      {/* Narration audio */}
      <Audio src={audioSrc} />

      {/* Top overlay: headline + subhead + citation */}
      <AbsoluteFill
        style={{
          padding: "60px 80px",
          pointerEvents: "none",
          opacity: overlayOpacity,
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 40,
          }}
        >
          <div style={{ maxWidth: 1100 }}>
            {overlay.headline && (
              <div
                style={{
                  fontFamily: "Inter, -apple-system, Helvetica, sans-serif",
                  fontWeight: 700,
                  fontSize: 58,
                  lineHeight: 1.1,
                  color: "#2b1a22",
                  textShadow: "0 2px 12px rgba(248, 243, 234, 0.8)",
                }}
              >
                {overlay.headline}
              </div>
            )}
            {overlay.subhead && (
              <div
                style={{
                  marginTop: 12,
                  fontFamily: "Inter, -apple-system, Helvetica, sans-serif",
                  fontWeight: 500,
                  fontSize: 28,
                  lineHeight: 1.3,
                  color: "#4d3a43",
                  textShadow: "0 2px 10px rgba(248, 243, 234, 0.8)",
                }}
              >
                {overlay.subhead}
              </div>
            )}
          </div>

          {overlay.citation && (
            <div
              style={{
                fontFamily: "Inter, -apple-system, Helvetica, sans-serif",
                fontStyle: "italic",
                fontSize: 20,
                color: "#6b5964",
                textShadow: "0 2px 10px rgba(248, 243, 234, 0.8)",
                whiteSpace: "nowrap",
              }}
            >
              {overlay.citation}
            </div>
          )}
        </div>
      </AbsoluteFill>

      {/* Bottom captions */}
      {currentCaption && (
        <AbsoluteFill
          style={{
            alignItems: "center",
            justifyContent: "flex-end",
            paddingBottom: 90,
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              maxWidth: 1500,
              padding: "18px 36px",
              borderRadius: 8,
              backgroundColor: "rgba(30, 18, 24, 0.72)",
              fontFamily: "Inter, -apple-system, Helvetica, sans-serif",
              fontWeight: 600,
              fontSize: 44,
              lineHeight: 1.25,
              color: "#fdf8f2",
              textAlign: "center",
              letterSpacing: 0.2,
            }}
          >
            {currentCaption.text}
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
