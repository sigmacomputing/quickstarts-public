import { signEmbedUrl } from "@/lib/utils";
import BasicExample from "./basic-example-embed";

export default async function SignedIframe() {
  const src =
    "https://staging.sigmacomputing.io/embed/1-156WHbeEOtenyfjDhfsnjY";
  const signedSrc = await signEmbedUrl(src);
  return <BasicExample src={signedSrc} />;
}
