# Hosted Editor preview

The Blacknode hosted preview provides the visual workflow canvas and Blacknode
Cloud execution at `https://app.blacknoderobotics.com`. Each browser receives
an isolated, process-local graph workspace. The preview supports core node
schemas, graph editing, templates, Cloud account access, GPU-second credits,
job submission, progress, logs, and artifact downloads.

Set these values only on the hosted Editor server:

```text
BLACKNODE_HOSTED_MODE=1
BLACKNODE_HOSTED_PUBLIC_ORIGIN=https://app.blacknoderobotics.com
BLACKNODE_CLOUD_URL=https://cloud.blacknoderobotics.com
```

Hosted workspaces expire after 24 hours and reset when the Editor server
restarts. Durable Cloud jobs and artifacts remain attached to the signed-in
Blacknode Cloud account.

## Security boundary

Hosted mode uses a strict backend allowlist. It accepts graph editing, template,
read-only package metadata, and Cloud routes. It rejects local cook and live
runtime operations, console execution, filesystem browsing, custom-node and
package mutation, device and SSH management, drivers, local imports, and local
workflow execution. Unsafe HTTP methods require the configured same-origin
`Origin` header. Workspace and Cloud credentials use separate HttpOnly,
Secure, SameSite=Strict cookies.

Customer workflows execute through the Blacknode Cloud job boundary. They do
not execute in the hosted Editor service.

The installed Editor remains the operator surface for local files, packages,
devices, ROS 2, cameras, local CUDA, and managed robot hardware.
