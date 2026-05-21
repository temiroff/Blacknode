# Public Preview Checklist

This checklist is for a soft launch, not paid advertising. The goal is to get useful technical feedback from people who can actually try Blacknode.

## Repo Readiness

- [x] Public repository
- [x] Apache-2.0 license
- [x] README explains local setup
- [x] Screenshots included
- [x] CI workflow for Python tests, editor build, and Rust check
- [x] MCP smoke test script
- [x] No API keys or local run artifacts tracked
- [x] GitHub release `v0.1.0-preview`
- [x] GitHub repository topics added
- [x] Short demo video linked from README
- [x] Issues enabled with a clear feedback request

Suggested topics:

```text
ai-agents
mcp
workflow-automation
node-editor
python
nvidia-nim
llm
react-flow
visual-programming
ai-tools
agent-workflows
```

## Product Readiness

- [x] No-API-key CLI demo
- [x] Visual editor demo
- [x] MCP workflow-building demo
- [x] NVIDIA NIM template demo
- [x] Run history and event timeline
- [x] Python export
- [x] Fresh-clone test on a second machine
- [ ] First-run troubleshooting notes tested by someone else
- [x] Known limitations documented in the release notes

## Soft Launch Channels

Use technical channels first:

- GitHub repo and release
- Personal X/LinkedIn post with a demo clip
- Relevant Discord or community channels where agent/MCP builders gather
- Carefully written Reddit post only where self-promotion is allowed
- Later: Show HN once the demo is easy to try
- Later: Product Hunt once there is a short video and a cleaner landing page

Do not buy ads for this stage. The project needs feedback, not traffic volume.

## Launch Message

Short version:

```text
I built Blacknode, a visual workflow builder for AI agents. It has a React node editor, Python runtime, workflow JSON, Python export, and an MCP server so agents can build and run graphs through typed tools.
```

Longer version:

```text
Blacknode is an experiment in making agent workflows visible and portable. You can build graphs manually in the browser, run them from the CLI, or let an MCP-connected agent create, validate, run, save, inspect, and export them. The public preview includes templates for chat, NVIDIA NIM, Python tools, research flows, and subnets.
```

## Feedback Questions

Ask users concrete questions:

- Did the setup work on your machine?
- Was the first useful demo obvious?
- Which workflow would you want to build first?
- Does MCP control feel useful or too indirect?
- Is Python export important for your use case?
- What would make this trustworthy enough for real work?

## Useful References

- Show HN guidelines: https://news.ycombinator.com/showhn.html
- Product Hunt launch guide: https://www.producthunt.com/launch/
- GitHub release docs: https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository
- GitHub topics docs: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics
