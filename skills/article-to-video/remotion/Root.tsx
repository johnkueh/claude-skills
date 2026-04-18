import { Composition } from "remotion";
import { VideoArticle } from "./VideoArticle";
import type { VideoArticleProps } from "./types";

// Minimal placeholder used only when Remotion Studio opens without --props.
// Actual renders pass --props=/path/to/props.json which overrides everything.
const placeholder: VideoArticleProps = {
  slug: "placeholder",
  title: "Video Article",
  fps: 30,
  width: 1920,
  height: 1080,
  totalFrames: 30,
  totalSeconds: 1,
  scenes: [],
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="VideoArticle"
        component={VideoArticle as any}
        durationInFrames={placeholder.totalFrames}
        fps={placeholder.fps}
        width={placeholder.width}
        height={placeholder.height}
        defaultProps={placeholder}
        calculateMetadata={({ props }) => {
          const p = props as VideoArticleProps;
          return {
            durationInFrames: p.totalFrames,
            fps: p.fps,
            width: p.width,
            height: p.height,
          };
        }}
      />
    </>
  );
};
