# Hosted Editor preview

The Blacknode hosted preview provides the visual workflow canvas and Blacknode
Cloud execution at `https://app.blacknoderobotics.com`. Each browser receives
an isolated, process-local graph workspace. The preview supports core node
schemas, graph editing, templates, Cloud account access, GPU-second credits,
compute-provider preference, job submission, progress, logs, and artifact
downloads. Available accounts can choose Auto, NVIDIA, or Nebius in the Cloud
account panel; Auto follows the Cloud service default.

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

## Website account entry

The Blacknode website can present its own account dialog while using the hosted
Editor's existing Cloud account endpoints. Configure the exact HTTPS website
origins in `BLACKNODE_HOSTED_ACCOUNT_ORIGINS`. The hosted server grants those
origins credentialed browser access only to account status, login,
registration, and logout. Graph, package, device, filesystem, and job routes do
not receive cross-origin access.

The website sends account requests directly to the hosted Editor origin with
browser credentials enabled. The Editor continues to keep the Cloud bearer
token in its server-side session behind an HttpOnly, Secure, SameSite cookie;
the website JavaScript cannot read that token. Because the cookie remains
host-only for `app.blacknoderobotics.com`, the same authenticated session is
available when the user opens the Editor.

`https://app.blacknoderobotics.com/?cloud=account` remains available as a
direct account-panel entry and fallback when a trusted website origin is not
configured.
