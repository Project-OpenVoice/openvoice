# Contributing to OpenVoice

Thank you for your interest in contributing to **OpenVoice**!

OpenVoice is a fully local, privacy-first personal operating system designed to execute user intents with deterministic reliability, audited memory, and sub-50ms hardware acceleration.

To maintain architectural integrity, all contributions must strictly adhere to the project's phase gates and architectural rules.

---

## 1. Architectural Non-Negotiables

Before writing code, please read and respect our core tenets defined in `plan.md`:

- **Rule R1: The Router Never Executes.**
  The Decision Engine (`app/decision/`) only classifies intent. It must never execute shell commands, touch the filesystem directly, or call system APIs.
- **Rule R2: No AI-Generated Shell Commands.**
  Every OS action maps to a predefined, audited Python function (`app/tools/`). We do not generate raw shell scripts via LLMs.
- **Rule R3: The Human Owns Memory.**
  Obsidian (markdown) is the canonical source of truth for knowledge. SQLite stores structured state (tasks, events), and ChromaDB stores vector embeddings for semantic lookup. Never duplicate canonical text across databases.
- **Rule R4: Respect Phase Gating.**
  OpenVoice develops in strict phases. Do not submit PRs for features belonging to future phases (e.g., wake words, microphone audio, speech-to-text, tray UI, Home Assistant) until the current phase is complete.

---

## 2. Development Setup

### Prerequisites
- Python 3.12+ (tested on Python 3.14)
- Git
- NVIDIA GPU with CUDA drivers (optional, but recommended for sub-50ms inference)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/arzeck/openvoice.git
   cd openvoice
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   # Windows PowerShell:
   .\venv\Scripts\Activate.ps1
   # Linux / macOS:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```

4. **GPU Acceleration Setup (Optional, recommended for NVIDIA GPUs)**:
   Install PyTorch with CUDA support matching your GPU architecture:
   - For Blackwell (RTX 50-series / sm_120):
     ```bash
     pip install --no-deps --force-reinstall torch --index-url https://download.pytorch.org/whl/cu130
     ```
   - For Ada Lovelace / Ampere (RTX 40 / 30-series):
     ```bash
     pip install --no-deps --force-reinstall torch --index-url https://download.pytorch.org/whl/cu126
     ```

5. **Configure environment**:
   ```bash
   cp .env.example .env
   ```

---

## 3. Verification & Testing

Every pull request must pass the automated test suite and maintain benchmark standards.

### Running Unit & Integration Tests
```bash
python -m pytest tests/ -v
```
All tests must pass (`100%` pass rate).

### Running the Decision Engine Benchmark
```bash
python scripts/benchmark.py
```
- **Accuracy**: Must achieve $\ge 95.0\%$ across all 504 benchmark samples.
- **Latency**: P95 latency must stay $\le 50\text{ ms}$ on GPU or $\le 500\text{ ms}$ on CPU.
- **Malformed Outputs**: Must remain strictly `0`.

### Linting & Formatting
We use [Ruff](https://astral.sh/ruff) for linting and code formatting:
```bash
# Check formatting
ruff format --check .

# Apply auto-formatting
ruff format .

# Run linter
ruff check .
```

---

## 4. Coding Standards

- **Type Hints**: All functions and methods must have complete Python type annotations.
- **Async-First**: All I/O operations (file access, database queries, network calls) must use `asyncio`.
- **Data Schemas**: Use `pydantic.BaseModel` for all structured payloads and configs.
- **Structured Logging**: Use `get_logger()` from `app.core.logging` for structured timing and audit logs. Never use raw `print()` statements in library code.
- **Error Resilience**: Adapter functions must catch exceptions, log errors, and return safe fallback schemas rather than crashing the orchestrator loop.

---

## 5. Pull Request Guidelines

1. **Create a topic branch**:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. **Follow Conventional Commits**:
   - `feat(scope): add new capability`
   - `fix(scope): resolve bug or misclassification`
   - `docs(scope): update documentation`
   - `test(scope): add or improve tests`
   - `refactor(scope): internal code cleanup`
3. **Verify locally**:
   Ensure `pytest` and `scripts/benchmark.py` both pass before opening a PR.
4. **Submit your PR**:
   Provide a concise description of your changes, reference any relevant issues, and include test output summaries.

---

## 6. Questions & Community

Have questions or ideas? Open an issue on GitHub or reach out to the maintainers at **aneeshshukla.tech@gmail.com**.
