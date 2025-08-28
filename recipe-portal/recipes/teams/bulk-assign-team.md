# Bulk Assign Team

## API Endpoints Used

- `GET /v2/members?search={email}` → [List Members](https://help.sigmacomputing.com/reference/listmembers)
- `PATCH /v2/teams/{teamId}/members` → [Update Team Members](https://help.sigmacomputing.com/reference/updateteammembers)

## Required Setup

1. Create email list file: Create a file named `.member-emails` in the `/recipes` directory
2. Add email addresses: Add one email address per line (plain text format)  
3. Example file content:
   ```
   user1@company.com
   user2@company.com
   admin@company.com
   ```

## Expected Output

- Console log showing search and assignment results for each email
- Success confirmation for members found and assigned to the team
- Error messages for emails that don't match existing Sigma users

## Use Cases

- Onboard multiple new team members at once
- Reassign groups of users to different teams during reorganization
- Bulk team assignments from external user lists (HR systems, etc.)

## Important Notes

- ⚠️ Email matching: Script will skip emails that don't match existing Sigma users
- Performance: Bulk operations may take time with large email lists due to individual API calls