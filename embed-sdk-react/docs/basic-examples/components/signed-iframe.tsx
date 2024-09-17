import { signEmbedUrl } from "@/lib/utils";
import { IframeHTMLAttributes, forwardRef } from "react";

export async function SignedIframe(
  props: IframeHTMLAttributes<HTMLIFrameElement>,
  ref: React.ForwardedRef<HTMLIFrameElement>,
) {
  const { src, ...rest } = props;
  if (!src) {
    throw new Error("src is required");
  }
  const signedSrc = await signEmbedUrl(src);
  return <iframe src={signedSrc} {...rest} ref={ref} />;
}

const SignedIframeWithRef = forwardRef(SignedIframe);

export default SignedIframeWithRef;
