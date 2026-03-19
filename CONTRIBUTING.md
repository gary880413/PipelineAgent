# 🤝 Contributing to PipelineAgent

First off, thank you for considering contributing to **PipelineAgent**! This is an open-source AI Agent framework dedicated to exploring "Cloud-Edge Collaboration" and asynchronous DAG orchestration.

We welcome all forms of contributions, including bug reports, feature requests, documentation improvements, and Pull Requests (PRs).

## 🛠️ Development Setup

If you want to modify and test PipelineAgent locally, please follow these steps to set up your development environment:

1. **Fork the repository** and clone it to your local machine:
   ```bash
   git clone https://github.com/gary880413/PipelineAgent.git
   cd PipelineAgent
   ```
2. **Create a virtual environment** (Highly Recommended):
   ```bash
   python -m venv venv
   # On Unix/macOS:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```
3. **Install development dependencies** (includes testing and formatting tools):
   ```bash
   pip install -e ".[dev]"
   ```
4. **Set up environment variables**:
   Copy the environment variable template and insert your OpenAI API Key.
   ```bash
   cp .env.example .env
   ```

## 📝 Coding Guidelines

To maintain the stability and professionalism of the core framework, please ensure the following before submitting your code:

- **No `print()` statements**: As a core framework, please strictly use our encapsulated logging module (located at `pipeline_agent.utils.logger`) to avoid polluting the user's terminal output.
- **Type Hinting First**: Any new functions or methods must include Python Type Hints (e.g., `List`, `Dict`, `Optional`). For core data structures, please use `pydantic.BaseModel`.
- **Async First**: The core engine uses `asyncio`. Any newly added tools or I/O-bound operations must be designed as `async def` to prevent blocking the main event loop.
- **Custom Exceptions**: Do not raise generic `Exception` or `ValueError`. Please use the specific error classes defined in `pipeline_agent.exceptions` (e.g., `ToolExecutionError`, `MCPConnectionError`).

## 🚀 Pull Request (PR) Process

1. Create a new, descriptively named branch from `main` (e.g., `feature/add-rag-retrieval` or `bugfix/mcp-timeout`).
2. Make your changes and commit them.
3. If adding a new feature, please provide a minimal testing script in the `examples/` directory to prove it works properly.
4. Write clear and concise commit messages.
5. Push your branch to your Fork and open a Pull Request on GitHub.
6. The maintainers will review your code and provide feedback as soon as possible!

## 🐛 Reporting Issues

If you find a bug or have an idea for a new feature, please open an issue via the GitHub Issues page. When submitting, please try to include:

- The terminal logs/traceback when the error occurred.
- Your Operating System and Python version.
- A Minimal Reproducible Example (if applicable).

Thank you for helping make PipelineAgent better!
