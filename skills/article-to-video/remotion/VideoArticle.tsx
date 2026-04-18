import { AbsoluteFill, Sequence } from "remotion";
import { Scene } from "./Scene";
import type { VideoArticleProps } from "./types";

export const VideoArticle: React.FC<VideoArticleProps> = ({ scenes }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#f8f3ea" }}>
      {scenes.map((scene) => (
        <Sequence
          key={scene.id}
          from={scene.startFrame}
          durationInFrames={scene.durationInFrames}
        >
          <Scene {...scene} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
