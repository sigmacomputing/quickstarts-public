# Update Member

## API Endpoints Used

- `PATCH /v2/members/{memberId}` → [Update Member](https://help.sigmacomputing.com/reference/updatemember)

## Expected Output

- Confirmation of successful account type change
- Updated member profile showing new account type
- Before and after account type comparison

## Use Cases

- Promote users from Viewer to Creator or Admin
- Adjust user permissions based on role changes
- Bulk account type updates for organizational changes
- Downgrade permissions for security compliance

## Important Notes

- Changes take effect immediately
- Account type affects user's permissions and access levels
- Valid account types: Admin, Creator, Viewer