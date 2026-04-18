export type Overlay = {
  headline: string;
  subhead: string;
  citation: string;
};

export type Caption = {
  text: string;
  startMs: number;
  endMs: number;
};

export type SceneProps = {
  id: number;
  section: string;
  startFrame: number;
  durationInFrames: number;
  durationSeconds: number;
  imageFile: string;
  audioFile: string;
  overlay: Overlay;
  captions: Caption[];
  kenBurns: "zoom-in-center" | "zoom-in-left" | "zoom-out-center" | "zoom-in-right";
};

export type VideoArticleProps = {
  slug: string;
  title: string;
  fps: number;
  width: number;
  height: number;
  totalFrames: number;
  totalSeconds: number;
  scenes: SceneProps[];
};
