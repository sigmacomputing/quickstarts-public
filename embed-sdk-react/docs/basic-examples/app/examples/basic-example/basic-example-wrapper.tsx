import { signEmbedUrl } from "@/lib/utils";
import BasicExample from "./basic-example-embed";

export default async function SignedIframe() {
  const src =
    "process.env.EMBED_URL;";
  const signedSrc = await signEmbedUrl(src);
  return <BasicExample src={signedSrc} />;
}
