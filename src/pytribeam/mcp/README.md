# pytribeam MCP

This describes the usage, structure, and roadmap for MCP development within the `pytribeam` python package.


## Usage

MCP servers can be connected to an MCP client (such as claude code) or ran in standalone mode permitting manual interactions.

### Manual usage

Manual usage is quite simple and crucial for development and monitoring. To simply test the MCP server and interact with it manually in a browser, run the following (assumes Node.js is installed on your computer):

```bash
npx @modelcontextprotocol/inspector pytribeam_mcp -e PYTRIBEAM_MCP_MICROSCOPE_HOST=localhost
```

What this command does is starts a the MCP server using our CLI entrypoint `pytribeam_mcp` and launches a webpage that acts as an inspector for the server. It will open up the web UI to the landing page, where you can connect to the server and peruse the tools, resources, and prompts that we have added to the server.

**This is the primary method of debugging the MCP server. When changes are made, it is important to run the inspector and verify that everything functions properly.**


### Agentic usage

For claude code:

```bash
claude mcp add pytribeam -e PYTRIBEAM_MCP_MICROSCOPE_HOST=localhost -- pytribeam_mcp
```

For codex:

```bash
codex mcp add pytribeam --env PYTRIBEAM_MCP_MICROSCOPE_HOST=localhost -- pytribeam_mcp
```

For other MCP clients, most clients that use a JSON config (Claude Desktop, Cursor, and others) accept this format:

```json
{
    "mcpServers": {
        "pytribeam": {
            "command": "pytribeam_mcp",
            "env": {"PYTRIBEAM_MCP_MICROSCOPE_HOST": "localhost"}
        }
    }
}
```


## Roadmap

Below is the target codebase structure:

```
src/pytribeam/mcp/
├── __main__.py
├── server.py
├── config.py
│
└── capabilities/
    ├── diagnostics.py
    ├── stage.py
    ├── imaging.py
    └── ...
```
