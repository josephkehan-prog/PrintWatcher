```markdown
# PrintWatcher Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill introduces the development patterns and workflows used in the PrintWatcher Python codebase. You'll learn about file naming conventions, import/export styles, commit message standards, and how to contribute updates—especially to documentation—using structured workflows and commands.

## Coding Conventions

### File Naming
- **Style:** camelCase
- **Example:**  
  ```plaintext
  printWatcher.py
  jobManager.py
  ```

### Import Style
- **Style:** Relative imports
- **Example:**
  ```python
  from .utils import formatJobStatus
  from .printer import PrinterManager
  ```

### Export Style
- **Style:** Named exports (explicitly listing what is exported)
- **Example:**
  ```python
  __all__ = ['PrinterManager', 'formatJobStatus']
  ```

### Commit Messages
- **Style:** Conventional commits
- **Prefixes:**  
  - `docs:` for documentation changes  
  - `fix:` for bug fixes
- **Example:**
  ```
  docs: update usage instructions in CLAUDE.md
  fix: handle printer disconnect edge case
  ```

## Workflows

### Update Documentation File
**Trigger:** When you need to add, update, or correct documentation  
**Command:** `/update-docs`

1. Edit the relevant documentation file (e.g., `CLAUDE.md`).
2. Save your changes.
3. Commit the changes using a message with the `docs:` prefix.  
   **Example:**  
   ```
   docs: clarify setup instructions in CLAUDE.md
   ```
4. Push your commit to the repository.

## Testing Patterns

- **Test File Pattern:** `*.test.*` (e.g., `printer.test.py`)
- **Testing Framework:** Not explicitly defined; check for test files matching the pattern.
- **Example Test File:**
  ```python
  # printer.test.py

  from .printer import PrinterManager

  def test_printer_initialization():
      pm = PrinterManager()
      assert pm.status == "idle"
  ```

## Commands
| Command       | Purpose                                      |
|---------------|----------------------------------------------|
| /update-docs  | Start the documentation update workflow      |
```
