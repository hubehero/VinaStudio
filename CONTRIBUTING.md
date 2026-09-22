# Contributing to VinaStudio

Thank you for your interest in contributing! This document provides guidelines for contributing to VinaStudio.

## Getting Started

1. Fork the repository
2. Clone your fork
3. Create a feature branch (`git checkout -b feature/amazing-feature`)
4. Make your changes
5. Commit your changes (`git commit -m 'feat: add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Development Setup

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and [pnpm](https://pnpm.io/)

### Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/vina_simple.git
cd vina_simple

# Install Python dependencies
uv sync --extra dev

# Install frontend dependencies
pnpm -C web install

# Build frontend
pnpm -C web build

# Run tests
uv run pytest -q

# Run linter
uv run ruff check .

# Run type checker
pnpm -C web typecheck
```

## Code Style

### Python

- Follow PEP 8
- Use type hints
- Run `ruff check .` before committing
- Keep functions focused and small

### TypeScript/Vue

- Follow the existing code style
- Use Composition API with `<script setup>`
- Run `pnpm -C web typecheck` before committing

## Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation changes
- `style:` formatting changes
- `refactor:` code refactoring
- `test:` adding tests
- `chore:` maintenance tasks

Examples:
```
feat: add SMILES input support
fix: correct metal ion detection
docs: update installation guide
```

## Pull Request Guidelines

1. **One feature per PR** — keep changes focused
2. **Write clear descriptions** — explain what and why
3. **Add tests** — for new features and bug fixes
4. **Update documentation** — if changing user-facing behavior
5. **Ensure CI passes** — all checks must be green

## Reporting Issues

When reporting bugs, please include:

1. **Operating system** and version
2. **Python version** (`python --version`)
3. **Steps to reproduce** the issue
4. **Expected behavior**
5. **Actual behavior**
6. **Error messages** or screenshots

## Feature Requests

We welcome feature requests! Please:

1. **Check existing issues** to avoid duplicates
2. **Describe the use case** — why is this needed?
3. **Propose a solution** if you have one in mind

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help newcomers learn
- Celebrate successes together

## Questions?

Feel free to open an issue for questions or join discussions in existing issues.
