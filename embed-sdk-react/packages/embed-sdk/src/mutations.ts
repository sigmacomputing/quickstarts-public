import {
  WorkbookBookmarkCreateEvent,
  WorkbookBookmarkCreateEventName,
  WorkbookBookmarkUpdateEventName,
  WorkbookFullscreenUpdateEventName,
  WorkbookSelectedNodeIdUpdateEventName,
  WorkbookSharingLinkUpdateEventName,
  WorkbookVariablesListEventName,
  WorkbookVariablesUpdateEventName,
} from "./types";

const sendIframeMessage = (
  iframe: HTMLIFrameElement,
  message: { type: string; [key: string]: any },
) => {
  if (!iframe.contentWindow) {
    throw new Error("iframe contentWindow is not available");
  }
  iframe.contentWindow.postMessage(
    message,
    "https://staging.sigmacomputing.io",
  );
};

export const workbookBookmarkCreate = (
  iframe: HTMLIFrameElement,
  bookmark: WorkbookBookmarkCreateEvent,
) => {
  sendIframeMessage(iframe, {
    type: WorkbookBookmarkCreateEventName,
    ...bookmark,
  });
};

export const workbookBookmarkUpdate = (iframe: HTMLIFrameElement) => {
  sendIframeMessage(iframe, {
    type: WorkbookBookmarkUpdateEventName,
  });
};

export const workbookFullscreenUpdate = (
  iframe: HTMLIFrameElement,
  nodeId: string | null,
) => {
  sendIframeMessage(iframe, {
    type: WorkbookFullscreenUpdateEventName,
    nodeId: nodeId,
  });
};

export const workbookSelectedNodeIdUpdate = (
  iframe: HTMLIFrameElement,
  nodeId: string,
  nodeType: "element" | "page",
) => {
  sendIframeMessage(iframe, {
    type: WorkbookSelectedNodeIdUpdateEventName,
    nodeId: nodeId,
    nodeType: nodeType,
  });
};

export const workbookVariablesList = (iframe: HTMLIFrameElement) => {
  sendIframeMessage(iframe, {
    type: WorkbookVariablesListEventName,
  });
};

export const workbookVariablesUpdate = (
  iframe: HTMLIFrameElement,
  variables: Record<string, string>,
) => {
  sendIframeMessage(iframe, {
    type: WorkbookVariablesUpdateEventName,
    variables: variables,
  });
};

export const workbookSharingLinkUpdate = (
  iframe: HTMLIFrameElement,
  sharingLink: string | null,
  sharingExplorationLink: string | null,
) => {
  sendIframeMessage(iframe, {
    type: WorkbookSharingLinkUpdateEventName,
    sharingLink: sharingLink,
    sharingExplorationLink: sharingExplorationLink,
  });
};
