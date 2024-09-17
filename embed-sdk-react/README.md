# embed-sdk

SDK for Sigma Computing Embeds. They are a wrapper over postmessage APIs.

## Getting Started

This repo uses pnpm and node18+. To get started

```sh
corepack enable
pnpm i
```

The repo uses turbo for its build system. It currently has 3 packages:

- embed-sdk: "barebones" wrappers over postMessages
- react-embed-sdk: React hooks to easily use the embed-sdk
- docs: Some barebone documentation / examples.

To build:

```
pnpm run build
```

## Publish flow:

Publishes are handled by changesets. To add a changeset, in your PR run:

```
pnpm changeset
```

This will prompt you to add a changeset. Once merged, a PR will be opened to bump the version and publish the package.

## Add iframe events

- [Example](https://github.com/sigmacomputing/embed-sdk/pull/31) for adding an inbound event
- Add a changeset for both the embed-sdk and react-embed-sdk.
