# Contributing to vLLM Router

Thank you for your interest in contributing to vLLM Router! This document provides guidelines and instructions for contributors.

## Development Setup

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/mvllm.git
   cd mvllm
   ```

3. **Set up the development environment**:
   ```bash
   # Install dependencies
   uv sync

   # Install development dependencies
   uv add --dev pytest pytest-asyncio httpx black isort flake8
   ```

4. **Create a virtual environment** (if not using uv):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```

## Code Style and Quality

We follow Python code style guidelines:

- **Code formatting**: Use `black` for code formatting
- **Import sorting**: Use `isort` for import organization
- **Linting**: Use `flake8` for linting
- **Type hints**: Use type hints where appropriate

### Running Code Quality Tools

```bash
# Format code
black app/
isort app/

# Lint code
flake8 app/

# Run tests
uv run pytest

# Run all quality checks
uv run pytest && black --check app/ && isort --check-only app/ && flake8 app/
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest test.py

# Run with coverage
uv run pytest --cov=app

# Run tests with verbose output
uv run pytest -v
```

### Test Coverage

We aim to maintain high test coverage. New features should include appropriate tests.

## Submitting Changes

1. **Create a feature branch**:
   ```bash
   git checkout -b feature-name
   ```

2. **Make your changes** and ensure they pass all tests

3. **Commit your changes** with a clear message:
   ```bash
   git commit -m "Add feature: description of changes"
   ```

4. **Push to your fork**:
   ```bash
   git push origin feature-name
   ```

5. **Create a Pull Request** to the main repository

## Pull Request Guidelines

- **Title**: Use a clear and descriptive title
- **Description**: Provide a detailed description of changes
- **Tests**: Ensure all tests pass
- **Documentation**: Update documentation as needed
- **Breaking Changes**: Clearly indicate any breaking changes

## Code Review Process

1. All pull requests must be reviewed by at least one maintainer
2. Continuous Integration (CI) must pass
3. Code quality checks must pass
4. Tests must pass with adequate coverage

## Issue Reporting

When reporting issues, please include:

- **Bug reports**: Steps to reproduce, expected behavior, actual behavior
- **Feature requests**: Clear description of the requested feature
- **Environment**: Python version, OS, relevant dependencies

## Development Guidelines

### Architecture Principles

- **Modularity**: Keep components loosely coupled
- **Async/Await**: Use async patterns throughout
- **Error Handling**: Provide meaningful error messages
- **Logging**: Use structured logging
- **Configuration**: Support configuration via environment variables and files

### API Design

- Follow RESTful principles
- Use appropriate HTTP status codes
- Provide clear error responses
- Include API documentation

### Performance Considerations

- Minimize blocking operations
- Use connection pooling
- Implement proper caching strategies
- Monitor resource usage

## Security Considerations

- Never commit secrets or API keys
- Validate all input data
- Use HTTPS in production
- Implement proper authentication/authorization
- Keep dependencies updated

## Documentation

- Keep README up to date
- Document public APIs
- Include examples for complex features
- Maintain changelog for significant changes

Thank you for contributing to vLLM Router! 🚀