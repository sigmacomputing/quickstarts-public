import { useState } from "react";
import { useWorkbookPageHeight } from "./wrappers";

/**
 *
 * A hook that returns the height of the page in the iframe.
 * This HAS to be used with the responsive_height option in the embed.
 *
 * @example
 * ```
 * function MyEmbed() {
 *  const { iframeRef } = useSigmaIframe();
 * const height = usePageHeight(iframeRef);
 *  return (
 *   <>
 *     <iframe
 *       style={{ height }}
 *       ref={iframeRef}
 *       src="https://app.sigmacomputing.com/embed"
 *     />
 *   </>
 * );
 * }
 * ```
 */
export function usePageHeight(
  iframeRef: React.RefObject<HTMLIFrameElement>,
): number | undefined {
  const [height, setHeight] = useState<undefined | number>(undefined);
  useWorkbookPageHeight(iframeRef, (event) => {
    if (!iframeRef.current) return;
    setHeight(event.pageHeight);
  });
  return height;
}
