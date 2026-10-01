# pytribeam MCP

This describes the usage, structure, and roadmap for MCP development within the `pytribeam` python package.

## Installation

pytribeam includes an MCP server, `pytribeam_mcp`, that lets an AI agent work with the microscope. Which tools the agent can see depends on the configured tier, and the default is tier 0 (read-only). Install it with the `mcp` extra:

```bash
# with pip
pip install "pytribeam[mcp]"

# with uv
uv add "pytribeam[mcp]"

# uv from git clone / repo root folder
uv sync --extra mcp
```

The server is configured through environment variables:

| Variable | Purpose | Default |
|---|---|---|
| `PYTRIBEAM_MCP_MICROSCOPE_HOST` | Host name or IP of the microscope PC | none |
| `PYTRIBEAM_MCP_MICROSCOPE_PORT` | AutoScript port | AutoScript default |
| `PYTRIBEAM_MCP_MAX_TIER` | Highest tier exposed to the agent (0–3) | `0` |
| `PYTRIBEAM_MCP_LOG_DIR` | Location of server and audit logs | `%LOCALAPPDATA%/pytribeam/logs/mcp` |

Settings can also live in a file of `KEY=VALUE` lines. The server reads
`%LOCALAPPDATA%/pytribeam/mcp.env` if it exists, or the file named by `--env-file`
or `PYTRIBEAM_MCP_ENV_FILE`. Command-line flags and real environment variables
take precedence over the file. It is recommended to create a `.env` file in the project root directory with the above variables for easier management and consistency across different environments.

## Usage

MCP servers can be connected to an MCP client (such as claude code) or ran in standalone mode permitting manual interactions.

### Manual usage

Manual usage is quite simple and crucial for development and monitoring. To simply test the MCP server and interact with it manually in a browser, run the following (assumes Node.js is installed on your computer):

```bash
npx @modelcontextprotocol/inspector pytribeam_mcp -e PYTRIBEAM_MCP_ENV_FILE="C:\path\to\.env"
```

What this command does is starts a the MCP server using our CLI entrypoint `pytribeam_mcp` and launches a webpage that acts as an inspector for the server. It will open up the web UI to the landing page, where you can connect to the server and peruse the tools, resources, and prompts that we have added to the server.

**This is the primary method of debugging the MCP server. When changes are made, it is important to run the inspector and verify that everything functions properly.**


### Agentic usage

For claude code or codex:

```bash
claude mcp add pytribeam -- pytribeam_mcp
codex mcp add pytribeam -- pytribeam_mcp
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
