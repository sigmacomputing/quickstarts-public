// Canvas presets. Sigma workbook pages use a 24-column grid; each zone is
// [startColumn, endColumn, startRow, endRow] in grid lines.
const presets = [
  {
    id: '4x1',
    name: '4 x 1',
    columns: 4,
    rows: 1,
    zones: [
      [1, 7, 1, 13],
      [7, 13, 1, 13],
      [13, 19, 1, 13],
      [19, 25, 1, 13],
    ],
  },
  {
    id: '2x2',
    name: '2 x 2',
    columns: 2,
    rows: 2,
    zones: [
      [1, 13, 1, 15],
      [13, 25, 1, 15],
      [1, 13, 15, 29],
      [13, 25, 15, 29],
    ],
  },
  {
    id: '3x2',
    name: '3 x 2',
    columns: 3,
    rows: 2,
    zones: [
      [1, 9, 1, 15],
      [9, 17, 1, 15],
      [17, 25, 1, 15],
      [1, 9, 15, 29],
      [9, 17, 15, 29],
      [17, 25, 15, 29],
    ],
  },
];

module.exports = { presets };
