import { Composition } from "remotion";
import { AIOSTutorial } from "./Tutorial";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="AIOSTutorial"
        component={AIOSTutorial}
        durationInFrames={180 * 30}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
