// This function can't be auto generated, but we can provide a
// better abstraction. In the final state of this project, it would
// be nice to see most functions auto generated but some
// hand generated for better abstraction.

import type {
  WorkbookErrorEvent,
  WorkbookLoadedEvent,
} from "@sigmacomputing/embed-sdk";
import { useCallback, useRef, useState } from "react";
import { useWorkbookLoaded, useWorkbookError } from "./wrappers";

/**
 * A hook that returns a ref to be used with an iframe element, and the loading and error state of the embed.
 *
 * @example
 * ```
 * function MyEmbed() {
 *  const { iframeRef, loading, error } = useSigmaIframe();
 *  return (
 *   <>
 *     {loading && <p>Loading...</p>}
 *     {error && <p>Error: {error.message}</p>}
 *     <iframe
 *       className={loading || error ? "hidden" : "show"}
 *       ref={iframeRef}
 *       src="https://app.sigmacomputing.com/embed"
 *     />
 *   </>
 * );
 * }
 * ```
 */
export function useSigmaIframe() {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [loading, setLoading] = useState(true);
  const [variables, setVariables] = useState<Record<string, string> | null>();
  const [error, setError] = useState<WorkbookErrorEvent | null>(null);
  const loadingCallback = useCallback((event: WorkbookLoadedEvent) => {
    setLoading(false);
    setVariables(event.workbook.variables);
  }, []);
  const errorCallback = useCallback((event: WorkbookErrorEvent) => {
    setError(event);
    setLoading(false);
  }, []);
  useWorkbookLoaded(iframeRef, loadingCallback);
  useWorkbookError(iframeRef, errorCallback);
  return { iframeRef, loading, error, variables };
}
