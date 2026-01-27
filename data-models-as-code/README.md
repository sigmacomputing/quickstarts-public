# Data Models as Code

This folder contains example JSON specifications for creating and managing Sigma data models programmatically via the API.

## Contents

- **specs/bikes-stations-basic.json** - Basic data model example using Sigma Sample Database (BIKES.STATIONS)
- **specs/bikes-stations-updated.json** - Updated version showing how to modify an existing data model

## Usage

These JSON files are referenced in the [Data Models as Code QuickStart](https://quickstarts.sigmacomputing.com/).

### Prerequisites

- Sigma account with API access
- API credentials (Client ID and Secret)
- Folder ID where data model will be created
- Connection ID for your data warehouse

### Workflow

1. Replace placeholder values (`YOUR_FOLDER_ID_HERE`, `YOUR_CONNECTION_ID_HERE`) with your actual IDs
2. Use the POST endpoint to create: `POST /v2/dataModels/spec`
3. Use the PUT endpoint to update: `PUT /v2/dataModels/{dataModelId}/spec`

## Documentation

- [Create and Manage Data Models from Code](https://help.sigmacomputing.com/reference/create-and-manage-data-models-from-code)
- [Sigma API Reference](https://help.sigmacomputing.com/reference/get-started-sigma-api)
