import type {
  WorkbookLoadedEvent,
  WorkbookErrorEvent,
  WorkbookDataLoadedEvent,
  WorkbookVariableOnChangeEvent,
  WorkbookTableCellSelectEvent,
  WorkbookPublishedEvent,
  WorkbookFullScreenEvent,
  WorkbookPageHeightEvent,
  WorkbookChartValueSelectEvent,
  WorkbookPageSelectedNodeEvent,
  WorkbookPivotTableCellSelectEvent,
  WorkbookCurrentVariablesEvent,
  WorkbookChartErrorEvent,
  WorkbookExploreKeyOnChangeEvent,
  WorkbookBookmarkOnChangeEvent,
  UrlOnChangeEvent,
  WorkbookIdOnChangeEvent,
  WorkbookBookmarkOnCreateEvent,
} from "@sigmacomputing/embed-sdk";
import {
  workbookLoadedListener,
  workbookErrorListener,
  workbookDataLoadedListener,
  workbookVariableChangeListener,
  workbookTableCellSelectListener,
  workbookPublishedListener,
  workbookFullScreenListener,
  workbookPageHeightListener,
  workbookChartValueSelectListener,
  workbookPageSelectedNodeListener,
  workbookPivotTableCellSelectListener,
  workbookBookmarkCreateListener,
  workbookCurrentVariablesListener,
  workbookChartErrorListener,
  workbookExploreKeyOnChangeListener,
  workbookBookmarkOnChangeListener,
  urlOnChangeListener,
  workbookIdOnChangeListener,
} from "@sigmacomputing/embed-sdk";
import { useEffect } from "react";

/**
 * Listen for a workbook loaded event, and execute the given callback when it occurs.
 *
 * @example
 * ```
 * function MyEmbed() {
 *   const [loading, setLoading] = useState(true);
 *   const loadingCallback = useCallback(() => setLoading(false), []);
 *   const iframeRef = useRef<HTMLIFrameElement>(null);
 *   useWorkbookLoaded(iframeRef, loadingCallback);
 *   return (
 *    <iframe
 *      className{loading ? "hidden" : "show"}
 *      ref={iframeRef}
 *      src="https://app.sigmacomputing.com/embed"
 *    />
 *   );
 * }
 * ```
 *
 */
export function useWorkbookLoaded(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onLoaded: (event: WorkbookLoadedEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookLoadedListener(event, iframeRef.current, onLoaded);
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onLoaded]);
}

/**
 * Listen for a workbook error event, and execute the given callback when it occurs.
 *
 * @example
 * ```
 * function MyEmbed() {
 *   const [error, setError] = useState<string | null>(null);
 *   const onError = useCallback((event: WorkbookErrorEvent) => {
 *     sendToErrorReporting(event.message);
 *     setError(event.message);
 *   }, []);
 *   const iframeRef = useRef<HTMLIFrameElement>(null);
 *   return (
 *    <iframe
 *      ref={iframeRef}
 *      src="https://app.sigmacomputing.com/embed"
 *    />
 *   );
 * }
 * ```
 *
 */
export function useWorkbookError(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onError: (event: WorkbookErrorEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookErrorListener(event, iframeRef.current, onError);
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onError]);
}

/**
 * Listen for a workbook data loaded event, and execute the given callback when it occurs.
 *
 * @example
 * ```
 * function MyEmbed() {
 *   const [dataLoaded, setDataLoaded] = useState(false);
 *   const onDataLoaded = useCallback(() => setDataLoaded(true), []);
 *   const iframeRef = useRef<HTMLIFrameElement>(null);
 *   return (
 *    <iframe
 *      ref={iframeRef}
 *      src="https://app.sigmacomputing.com/embed"
 *    />
 *   );
 * }
 * ```
 */
export function useWorkbookDataLoaded(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onDataLoaded: (event: WorkbookDataLoadedEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookDataLoadedListener(event, iframeRef.current, onDataLoaded);
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onDataLoaded]);
}

export function useVariableChange(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onVariableChange: (event: WorkbookVariableOnChangeEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookVariableChangeListener(
        event,
        iframeRef.current,
        onVariableChange,
      );
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onVariableChange]);
}

export function useTableCellSelect(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onTableCellSelect: (event: WorkbookTableCellSelectEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookTableCellSelectListener(
        event,
        iframeRef.current,
        onTableCellSelect,
      );
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onTableCellSelect]);
}

export function useWorkbookPublished(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onWorkbookPublished: (event: WorkbookPublishedEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookPublishedListener(event, iframeRef.current, onWorkbookPublished);
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onWorkbookPublished]);
}

export function useWorkbookFullScreen(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onFullScreen: (event: WorkbookFullScreenEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookFullScreenListener(event, iframeRef.current, onFullScreen);
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onFullScreen]);
}

export function useWorkbookPageHeight(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onPageHeight: (event: WorkbookPageHeightEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookPageHeightListener(event, iframeRef.current, onPageHeight);
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onPageHeight]);
}

export function useWorkbookPageSelectedNode(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onPageSelectedNode: (event: WorkbookPageSelectedNodeEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookPageSelectedNodeListener(
        event,
        iframeRef.current,
        onPageSelectedNode,
      );
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onPageSelectedNode]);
}

export function useWorkbookPivotTableCellSelect(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onPivotTableCellSelect: (event: WorkbookPivotTableCellSelectEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookPivotTableCellSelectListener(
        event,
        iframeRef.current,
        onPivotTableCellSelect,
      );
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onPivotTableCellSelect]);
}

export function useWorkbookChartValueSelect(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onChartValueSelect: (event: WorkbookChartValueSelectEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookChartValueSelectListener(
        event,
        iframeRef.current,
        onChartValueSelect,
      );
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onChartValueSelect]);
}

export function useWorkbookCurrentVariables(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onCurrentVariables: (event: WorkbookCurrentVariablesEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookCurrentVariablesListener(
        event,
        iframeRef.current,
        onCurrentVariables,
      );
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onCurrentVariables]);
}

export function useWorkbookBookmarkOnCreate(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onBookmarkCreate: (event: WorkbookBookmarkOnCreateEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookBookmarkCreateListener(
        event,
        iframeRef.current,
        onBookmarkCreate,
      );
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onBookmarkCreate]);
}

export function useWorkbookChartError(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onChartError: (event: WorkbookChartErrorEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookChartErrorListener(event, iframeRef.current, onChartError);
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onChartError]);
}

export function useWorkbookExploreKeyOnChange(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onExploreKeyChange: (event: WorkbookExploreKeyOnChangeEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookExploreKeyOnChangeListener(
        event,
        iframeRef.current,
        onExploreKeyChange,
      );
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onExploreKeyChange]);
}

export function useWorkbookBookmarkOnChange(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onBookmarkChange: (event: WorkbookBookmarkOnChangeEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookBookmarkOnChangeListener(
        event,
        iframeRef.current,
        onBookmarkChange,
      );
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onBookmarkChange]);
}

export function useUrlOnChange(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onUrlChange: (event: UrlOnChangeEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      urlOnChangeListener(event, iframeRef.current, onUrlChange);
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onUrlChange]);
}

export function useWorkbookIdOnChange(
  iframeRef: React.RefObject<HTMLIFrameElement>,
  onIdChange: (event: WorkbookIdOnChangeEvent) => void,
) {
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (!iframeRef.current) {
        return;
      }
      workbookIdOnChangeListener(event, iframeRef.current, onIdChange);
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, [iframeRef, onIdChange]);
}
