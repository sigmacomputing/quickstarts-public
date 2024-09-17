import {
  WorkbookLoadedEventName,
  WorkbookErrorEventName,
  WorkbookVariableEventOnChangeName,
  WorkbookTableCellSelectEventName,
  WorkbookPublishedEventName,
  WorkbookFullScreenEventName,
  WorkbookPageHeightEventName,
  WorkbookLoadedEvent,
  WorkbookErrorEvent,
  WorkbookVariableOnChangeEvent,
  WorkbookTableCellSelectEvent,
  WorkbookPublishedEvent,
  WorkbookFullScreenEvent,
  WorkbookPageHeightEvent,
  WorkbookPageSelectedNodeEvent,
  WorkbookPageSelectedNodeEventName,
  WorkbookPivotTableCellSelectEvent,
  WorkbookPivotTableCellSelectEventName,
  WorkbookChartValueSelectEvent,
  WorkbookChartValueSelectEventName,
  WorkbookCurrentVariablesEvent,
  WorkbookCurrentVariablesEventName,
  WorkbookBookmarkOnCreateEvent,
  WorkbookBookmarkOnCreateEventName,
  WorkbookDataLoadedEvent,
  WorkbookDataLoadedEventName,
  WorkbookChartErrorEvent,
  WorkbookChartErrorEventName,
  WorkbookExploreKeyOnChangeEvent,
  WorkbookExploreKeyOnChangeEventName,
  WorkbookBookmarkOnChangeEvent,
  WorkbookBookmarkOnChangeEventName,
  UrlOnChangeEvent,
  UrlOnChangeEventName,
  WorkbookIdOnChangeEvent,
  WorkbookIdOnChangeEventName,
  WorkbookSharingLinkUpdateEvent,
  WorkbookSharingLinkUpdateEventName,
  WorkbookVariableCurrentEvent,
  WorkbookVariablesCurrentEventName,
} from "./types";

const checkEventOrigin = (url: string) => {
  const hostname = new URL(url).hostname;
  const hostnameSplit = hostname.split(".");
  const domain = hostnameSplit.slice(-2).join(".");
  return ["sigmacomputing.io", "sigmacomputing.com"].includes(domain);
};

export const workbookLoadedListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onLoaded: (event: WorkbookLoadedEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookLoadedEventName) {
      onLoaded(event.data);
    }
  }
};

export const workbookErrorListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onError: (event: WorkbookErrorEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookErrorEventName) {
      onError(event.data);
    }
  }
};

export const workbookVariableChangeListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onVariable: (event: WorkbookVariableOnChangeEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookVariableEventOnChangeName) {
      onVariable(event.data);
    }
  }
};

export const workbookVariableCurrentListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onVariable: (event: WorkbookVariableCurrentEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookVariablesCurrentEventName) {
      onVariable(event.data);
    }
  }
};

export const workbookLinkSharingUpdateListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onVariable: (event: WorkbookSharingLinkUpdateEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookSharingLinkUpdateEventName) {
      onVariable(event.data);
    }
  }
};

export const workbookTableCellSelectListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onTableCellSelect: (event: WorkbookTableCellSelectEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookTableCellSelectEventName) {
      onTableCellSelect(event.data);
    }
  }
};

export const workbookPublishedListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onPublished: (event: WorkbookPublishedEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookPublishedEventName) {
      onPublished(event.data);
    }
  }
};

export const workbookFullScreenListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onFullScreen: (event: WorkbookFullScreenEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookFullScreenEventName) {
      onFullScreen(event.data);
    }
  }
};

export const workbookPageHeightListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onPageHeight: (event: WorkbookPageHeightEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookPageHeightEventName) {
      onPageHeight(event.data);
    }
  }
};

export const workbookPageSelectedNodeListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onPageSelectedNode: (event: WorkbookPageSelectedNodeEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookPageSelectedNodeEventName) {
      onPageSelectedNode(event.data);
    }
  }
};

export const workbookPivotTableCellSelectListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onPivotTableCellSelect: (event: WorkbookPivotTableCellSelectEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookPivotTableCellSelectEventName) {
      onPivotTableCellSelect(event.data);
    }
  }
};

export const workbookChartValueSelectListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onChartValueSelect: (event: WorkbookChartValueSelectEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookChartValueSelectEventName) {
      onChartValueSelect(event.data);
    }
  }
};

export const workbookCurrentVariablesListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onCurrentVariables: (event: WorkbookCurrentVariablesEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookCurrentVariablesEventName) {
      onCurrentVariables(event.data);
    }
  }
};

export const workbookBookmarkCreateListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onBookmarkCreate: (event: WorkbookBookmarkOnCreateEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookBookmarkOnCreateEventName) {
      onBookmarkCreate(event.data);
    }
  }
};
export const workbookDataLoadedListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onWorkbookDataLoaded: (event: WorkbookDataLoadedEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookDataLoadedEventName) {
      onWorkbookDataLoaded(event.data);
    }
  }
};

export const workbookChartErrorListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onChartError: (event: WorkbookChartErrorEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookChartErrorEventName) {
      onChartError(event.data);
    }
  }
};

export const workbookExploreKeyOnChangeListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onExploreKeyOnChange: (event: WorkbookExploreKeyOnChangeEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookExploreKeyOnChangeEventName) {
      onExploreKeyOnChange(event.data);
    }
  }
};

export const workbookBookmarkOnChangeListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onBookmarkChange: (event: WorkbookBookmarkOnChangeEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookBookmarkOnChangeEventName) {
      onBookmarkChange(event.data);
    }
  }
};

export const urlOnChangeListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onUrlChange: (event: UrlOnChangeEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === UrlOnChangeEventName) {
      onUrlChange(event.data);
    }
  }
};

export const workbookIdOnChangeListener = (
  event: MessageEvent,
  iframe: HTMLIFrameElement,
  onWorkbookIdChange: (event: WorkbookIdOnChangeEvent) => void,
) => {
  if (event.source === iframe.contentWindow && checkEventOrigin(event.origin)) {
    if (event.data.type === WorkbookIdOnChangeEventName) {
      onWorkbookIdChange(event.data);
    }
  }
};
