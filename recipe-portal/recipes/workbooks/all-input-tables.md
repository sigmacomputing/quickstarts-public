# All Input Tables

## API Endpoints Used

- `GET /v2/workbooks` → [List Workbooks](https://help.sigmacomputing.com/reference/listworkbooks)
- `GET /v2/workbooks/{workbookId}` → [Get Workbook](https://help.sigmacomputing.com/reference/getworkbook)

## Expected Output

- Complete inventory of all input tables across all workbooks
- Location information showing which workbook contains each input table
- Input table configuration details and data source information

## Use Cases

- Audit all input tables in the organization
- Track data input dependencies across workbooks
- Monitor input table usage and configuration
- Generate input table inventory reports

## Important Notes

- Scans all workbooks to find input table instances
- Shows input table locations and configurations
- Useful for data governance and dependency mapping
- Process time depends on total number of workbooks