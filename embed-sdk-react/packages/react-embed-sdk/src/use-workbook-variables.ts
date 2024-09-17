import { useCallback, useEffect, useState } from "react";
import {
  workbookVariablesList,
  workbookCurrentVariablesListener,
  workbookVariablesUpdate,
} from "@sigmacomputing/embed-sdk";

type CallBackState =
  | {
      state: "pending";
      callback: (variables: Record<string, string>) => void;
    }
  | {
      state: "success";
      variables: Record<string, string>;
    };

/**
 * A hook that returns functions to get and set the variables in a workbook.
 * @example
 * ```
 * function MyEmbed() {
 *   const { getVariables, setVariables } = useWorkbookVariables(iframeRef);
 *   return (
 *    <>
 *     <button onClick={() => setVariables({ foo: "bar" })}>Set Variables</button>
 *     <button onClick={() => const variable = await getVariables()}>Get Variables</button>
 *     <iframe
 *       ref={iframeRef}
 *       src="https://app.sigmacomputing.com/embed"
 *     />
 *    <>
 *   );
 * }
 * ```
 */
export const useWorkbookVariables = (
  iframeRef: React.RefObject<HTMLIFrameElement>,
) => {
  const [state, setState] = useState<CallBackState>();
  const getVariables = useCallback(() => {
    if (!iframeRef.current) {
      throw new Error("iframe is not available");
    }
    workbookVariablesList(iframeRef.current);
    const promise = new Promise((resolve) => {
      setState({ state: "pending", callback: resolve });
    });
    return promise;
  }, [iframeRef]);
  const setVariables = useCallback(
    (variables: Record<string, string>) => {
      if (!iframeRef.current) {
        throw new Error("iframe is not available");
      }
      workbookVariablesUpdate(iframeRef.current, variables);
    },
    [iframeRef],
  );
  useEffect(() => {
    if (!iframeRef.current) return;
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookCurrentVariablesListener(event, iframeRef.current, (event) => {
        if (state?.state === "pending") {
          setState({ state: "success", variables: event.variables });
          state.callback(event.variables);
        }
      });
    };
    window.addEventListener("message", listener);
    return () => {
      window.removeEventListener("message", listener);
    };
  }, [iframeRef, state]);
  return {
    getVariables,
    setVariables,
  };
};
