# Initiate Materialization

## API Endpoints Used

- `GET /v2/workbooks/{workbookId}/materialization-schedules` → List available schedules
- `POST /v2/workbooks/{workbookId}/materializations` → [Create Materialization](https://help.sigmacomputing.com/reference/creatematerialization)
- `GET /v2/workbooks/{workbookId}/materializations/{materializationId}` → [Get Materialization Status](https://help.sigmacomputing.com/reference/getmaterializationstatus)

## Required Setup

1. **Authentication**: Valid credentials with workbook access permissions
2. **Materialization Schedule**: Workbook must have at least one materialization schedule configured
3. **Schedule Selection**: Use the "Schedule Name" dropdown to select which materialization to run

## Expected Output

- List of all available materialization schedules with timing details
- Selected schedule confirmation and job initiation
- Real-time status monitoring (`pending` → `building` → `ready`)
- Final completion message with job performance details

## Use Cases

- Pre-compute expensive workbook calculations for faster loading
- Run on-demand materializations outside of scheduled times
- Test materialization performance for different workbook elements
- Refresh materialized views before important presentations or reports

## Important Notes

- **UI Interface**: Recipe Portal displays user-friendly schedule names but sends sheet IDs to the API
- **Execution Time**: Jobs typically complete in 1-3 minutes with 5-minute timeout
- **Log Display**: All execution logs shown after completion (not real-time streaming)
- **Status Flow**: Monitor progress through `pending` → `building` → `ready` (successful) or `failed`
- **Schedule Availability**: Only non-paused schedules appear in dropdown options