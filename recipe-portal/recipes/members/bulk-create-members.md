# Bulk Create Members

This script creates multiple new members in Sigma from a list of email addresses.

## Prerequisites

- Valid authentication credentials with member management permissions
- Email list file containing the email addresses of members to create

## Setup

1. **Create email list file**: Create a file named `.member-emails` in the `/recipes` directory
2. **Format the file**: Add email addresses separated by commas:
   ```
   user1@company.com,user2@company.com,user3@company.com
   ```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEW_MEMBER_TYPE` | No | `view` | Default account type for all created members (`admin`, `build`, `view`, `analyze`, `act`) |

## Features

- **Duplicate Prevention**: Automatically checks if members already exist and skips them
- **Smart Naming**: Extracts first/last names from email addresses (e.g., `john.doe@company.com` → `John Doe`)
- **Batch Processing**: Processes multiple emails with rate limiting to avoid API throttling
- **Detailed Reporting**: Provides summary of created, skipped, and failed members
- **Error Handling**: Continues processing even if individual member creation fails

## Usage

1. Set up your `.member-emails` file with comma-separated email addresses
2. Configure `NEW_MEMBER_TYPE` in your `.env` file (optional, defaults to `view`)
3. Run the script

## Output

The script provides detailed progress for each email and a final summary:

```
Processing 1/3: user1@company.com
  Created: Member ID abc123xyz
Processing 2/3: user2@company.com  
  Skipped: Member already exists
Processing 3/3: user3@company.com
  Failed: Invalid email format

=== BULK MEMBER CREATION SUMMARY ===
Total processed: 3
Successfully created: 1
Skipped (already exist): 1
Failed: 1
```

## Common Use Cases

- **Initial Setup**: Create multiple team members during organization setup
- **Team Onboarding**: Add new team members in bulk
- **Testing**: Create test users for team assignment workflows

## Related Scripts

After creating members in bulk, you can use:
- `bulk-assign-team.js` - Assign the newly created members to teams
- `master-script.js` - Complete individual member onboarding with workspace and connection permissions

## Notes

- Members are created with basic information derived from their email addresses
- For more detailed member setup (custom names, individual permissions), use the individual member creation scripts
- The script uses the same `.member-emails` file as the team bulk assignment script for consistency