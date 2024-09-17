export type Value_t = unknown;
export enum CellType_t {
  Value = "valueCell",
  RowHeader = "rowHeader",
  ColumnHeader = "columnHeader",
  Total = "total",
}
export type DataRow_t = Record<string, Value_t>;
export type DataRows_t = DataRow_t[];
export interface Data_t {
  rows: DataRows_t;
  isTruncated: boolean;
  length: number;
}

export interface Cell_t {
  value: Value_t;
  cellType: CellType_t;
  columnName: string;
}
export interface LevelTableValueCell_t extends Cell_t {
  cellType: CellType_t.Value;
  underlyingData: Data_t;
}
export interface LevelTableColumnCell_t extends Cell_t {
  cellType: CellType_t.ColumnHeader;
}
export type LevelTableCell_t = LevelTableValueCell_t | LevelTableColumnCell_t;
export type LevelTableCells = LevelTableCell_t[];

export interface PathChunk_t {
  name: string;
  value: Value_t;
}
export type PivotPath_t = PathChunk_t[];
export interface PivotTableCell_t extends Cell_t {
  rowPath: PivotPath_t | null;
  columnPath: PivotPath_t | null;
}
export type PivotTableCells_t = PivotTableCell_t[];
export type ChartValue_t = Record<string, Value_t>;
export type ChartValues_t = ChartValue_t[];

export const WorkbookLoadedEventName = "workbook:loaded" as const;
export const WorkbookErrorEventName = "workbook:error" as const;
export const WorkbookVariableEventOnChangeName =
  "workbook:variables:onchange" as const;
export const WorkbookTableCellSelectEventName =
  "workbook:table:oncellselect" as const;
export const WorkbookPublishedEventName = "workbook:published" as const;
export const WorkbookFullScreenEventName =
  "workbook:fullscreen:onchange" as const;
export const WorkbookPageHeightEventName =
  "workbook:pageheight:onchange" as const;
export const WorkbookPageSelectedNodeEventName =
  "workbook:selectednodeid:onchange" as const;
export const WorkbookPivotTableCellSelectEventName =
  "workbook:pivottable:oncellselect" as const;
export const WorkbookChartValueSelectEventName =
  "workbook:chart:onvalueselect" as const;
export const WorkbookCurrentVariablesEventName =
  "workbook:variables:current" as const;
export const WorkbookBookmarkOnCreateEventName =
  "workbook:bookmark:oncreate" as const;
export const WorkbookDataLoadedEventName = "workbook:dataloaded" as const;
export const WorkbookChartErrorEventName = "workbook:chart:error" as const;
export const WorkbookExploreKeyOnChangeEventName =
  "workbook:exploreKey:onchange" as const;
export const WorkbookBookmarkOnChangeEventName =
  "workbook:bookmark:onchange" as const;
export const UrlOnChangeEventName = "url:onchange" as const;
export const WorkbookIdOnChangeEventName = "workbook:id:onchange" as const;
export const WorkbookBookmarkCreateEventName =
  "workbook:bookmark:create" as const;
export const WorkbookBookmarkUpdateEventName =
  "workbook:bookmark:update" as const;
export const WorkbookFullscreenUpdateEventName =
  "workbook:fullscreen:update" as const;

export const WorkbookSelectedNodeIdUpdateEventName =
  "workbook:selectednodeid:update" as const;

export const WorkbookVariablesListEventName =
  "workbook:variables:list" as const;

export const WorkbookVariablesUpdateEventName =
  "workbook:variables:update" as const;

export const WorkbookVariablesCurrentEventName =
  "workbook:variables:current" as const;

export const WorkbookSharingLinkUpdateEventName =
  "workbook:sharinglink:update" as const;

export interface WorkbookLoadedEvent {
  type: typeof WorkbookLoadedEventName;
  workbook: {
    variables: Record<string, string>;
  };
}

export interface WorkbookErrorEvent {
  type: typeof WorkbookErrorEventName;
  code: string;
  message: string;
}

export interface WorkbookVariableOnChangeEvent {
  type: typeof WorkbookVariableEventOnChangeName;
  variables: Record<string, string>;
}

export interface WorkbookVariableCurrentEvent {
  type: typeof WorkbookVariablesCurrentEventName;
  variables: Record<string, string>;
}

export interface WorkbookSharingLinkUpdateEvent {
  type: typeof WorkbookSharingLinkUpdateEventName;
  variables: Record<string, string>;
}

export interface WorkbookTableCellSelectEvent {
  type: typeof WorkbookTableCellSelectEventName;
  nodeId: string;
  title: string;
  cells: LevelTableCells;
}

export type WorkbookPublishedEvent = {
  type: typeof WorkbookPublishedEventName;
  workbookId: string;
};
export type WorkbookFullScreenEvent = {
  type: typeof WorkbookFullScreenEventName;
  fullScreen: boolean;
};
export type WorkbookPageHeightEvent = {
  type: typeof WorkbookPageHeightEventName;
  pageHeight: number;
};
export type WorkbookPageSelectedNodeEvent = {
  type: typeof WorkbookPageSelectedNodeEventName;
  selectedNodeId: string | null;
};

export type WorkbookPivotTableCellSelectEvent = {
  type: typeof WorkbookPivotTableCellSelectEventName;
  nodeId: string;
  title: string;
  cells: PivotTableCells_t;
};

export type WorkbookChartValueSelectEvent = {
  type: typeof WorkbookChartValueSelectEventName;
  nodeId: string;
  title: string;
  values: ChartValues_t;
};

export type WorkbookCurrentVariablesEvent = {
  type: typeof WorkbookCurrentVariablesEventName;
  variables: Record<string, string>;
};

export type WorkbookBookmarkOnCreateEvent = {
  type: typeof WorkbookBookmarkOnCreateEventName;
  bookmarkName: string;
  workbookId: string;
  versionTagName: string | null;
  bookmarkId: string;
};

export type WorkbookDataLoadedEvent = {
  type: typeof WorkbookDataLoadedEventName;
};

export type WorkbookChartErrorEvent = {
  type: typeof WorkbookChartErrorEventName;
  message: string | undefined;
  code: string;
  nodeId: string;
};

export type WorkbookExploreKeyOnChangeEvent = {
  type: typeof WorkbookExploreKeyOnChangeEventName;
  exploreKey: string | null;
};

export type WorkbookBookmarkOnChangeEvent = {
  type: typeof WorkbookBookmarkOnChangeEventName;
  bookmarkName: string | null;
  workbookId: string;
  versionTagName: string | null;
  bookmarkId: string | null;
};

export type UrlOnChangeEvent = {
  type: typeof UrlOnChangeEventName;
  url: string;
};

export type WorkbookIdOnChangeEvent = {
  type: typeof WorkbookIdOnChangeEventName;
  id: string;
};

export type WorkbookBookmarkCreateEvent = {
  name: string;
  isDefault: boolean;
  isShared: boolean;
};
