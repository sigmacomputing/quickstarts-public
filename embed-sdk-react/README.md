# Sigma Embed-SDK for React
Sigma provides several methods to allow users and developers to interact with its systems including web-ui, REST API, Javascript Embed API and an SDK for the React framework.

The Embed-SDK for React provides an addition avenue, targeted at software developers who prefer to use a software development kit (SDK), as opposed to using the Sigmas JavaScript Embed-API, which can require writing additional code. 

If the basic instructions below are not sufficient, please review the [QuickStart here.](https://quickstarts.sigmacomputing.com/guide/embedding_15_embed_sdk/index.html?index=..%2F..index#0)

## Getting Started
1: Clone the repository

2: Setup your local environment for project dependencies:
- Node.js (version 18+)
- pnpm
- corepack (needs to be enabled)

3: Start the development server
```code
pnpm run dev
```

4: Browse to http://localhost:3000

## Building
The repo uses turbo for its build system. It currently has 3 packages:

- embed-sdk: "barebones" wrappers over postMessages
- react-embed-sdk: React hooks to easily use the embed-sdk
- docs: Some barebone documentation / examples.

To build:
```code
pnpm run build
```

## Publish flow:
Publishes are handled by changesets. To add a changeset, in your PR run:
```code
pnpm changeset
```

This will prompt you to add a changeset. Once merged, a PR will be opened to bump the version and publish the package.

## Adding iframe events
- [Example](https://github.com/sigmacomputing/embed-sdk/pull/31) for adding an inbound event
- Add a changeset for both the embed-sdk and react-embed-sdk.
