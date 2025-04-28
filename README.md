# Code Base Condenser

A modern GUI tool designed to help developers prepare their codebase for Large Language Model (LLM) analysis by condensing multiple source files into a single readable format or structured chunks.

![Code Base Condenser](https://github.com/Sqygey/CodeCondenser/raw/main/screenshot.png)

## Purpose

When working with LLMs like ChatGPT or Claude, there's often a need to share large portions of a codebase for analysis or discussion. However, copying files individually or managing multiple uploads can be cumbersome. Code Base Condenser solves this by:

- Combining multiple source files into a single organized text file
- Maintaining clear file boundaries and structure
- Excluding unnecessary files (binaries, dependencies, etc.)
- Supporting smart file chunking for large projects
- Respecting `.gitignore` rules
- Providing directory structure visualization

## Features

- 📁 Interactive directory selection with file browser preview
- 🎨 Modern UI with dark mode support
- 🔍 Smart file filtering:
  - Built-in exclusion lists for common non-code files
  - Custom extension filtering
  - `.gitignore` support
  - Pattern-based file exclusion
- 📊 Output options:
  - Single file or automatic chunking
  - Directory structure visualization
  - Structure-only mode for project overview
- ⚙️ Configurable chunk sizes
- 🔄 Visual progress tracking with detailed status updates
- 📂 One-click file opening after generation
- 🧩 Step-by-step wizard interface for easier workflow
- 💻 Cross-platform GUI

## Requirements

- Python 3.6 or higher
- PyQt5

Install dependencies using pip:
```bash
pip install PyQt5
```

## New in Version 2.0 (Apr 25, 2025)

- Completely redesigned user interface with dark mode support
- New step-by-step wizard interface for easier workflow
- Added file browser preview for better project navigation
- Improved progress visualization with detailed status updates
- Added one-click file opening after generation
- Enhanced error handling and user feedback
- Added settings persistence between sessions

## Running the Application

1. Clone or download the repository
2. Install dependencies
3. Run the application:
```bash
python code-condenser.py
```

## Usage

The application now features a step-by-step wizard interface that guides you through the process:

1. **Step 1: Select Project Directory**
   - Click "Browse" to select your project's root directory
   - The tool will automatically suggest an output filename
   - Preview your project structure in the file browser

2. **Step 2: Configure Exclusions**
   - Modify the pre-configured exclusion lists as needed
   - Enable/disable `.gitignore` rules
   - Check/uncheck file extensions to exclude
   - Add custom extensions to exclude

3. **Step 3: Choose Output Options**
   - Select between single file or chunked output
   - Enable/disable directory structure inclusion
   - Configure maximum lines per chunk (if chunking)
   - Preview how the output will be formatted

4. **Step 4: Review & Generate**
   - Review your configuration summary
   - Click "Generate Condensed Code"
   - Monitor progress with the visual progress bar
   - Review any warnings about unreadable files
   - Open generated files directly from the application

## Output Format

The generated output file(s) will have the following structure:

```
Directory Structure: (if enabled)
====================
📁 root
  📁 src
    📄 main.py
  📁 tests
    📄 test_main.py
  📄 README.md

>>>File: src/main.py

[content of main.py]

========================================

>>>File: tests/test_main.py

[content of test_main.py]

========================================
```

## Tips for LLM Usage

- Use structure-only mode first to get an overview of your project
- For large projects, use chunking to stay within LLM context limits
- Include the directory structure in the first chunk for better context
- Consider excluding test files, documentation, or other non-essential code to focus the LLM's attention

## Default Exclusions

The tool comes with pre-configured exclusions for common non-code files:

- **Directories**: `.git`, `node_modules`, `venv`, `__pycache__`, etc.
- **Files**: `package-lock.json`, `*.pyc`, `*.exe`, etc.
- **Extensions**: Images, videos, binaries, etc.

These can be customized through the GUI.

## Known Limitations

- Large binary files might cause memory issues
- Basic `.gitignore` pattern support (complex patterns might not work)
- UTF-8 encoding is assumed (falls back to latin-1)
- Very large files might need manual chunking

## Contributing

Contributions are welcome! Please feel free to submit pull requests or create issues for bugs and feature requests.

## Author

Created by David Oppenheim (GitHub: [Sqygey](https://github.com/Sqygey))

## License

This project is open source and available under the MIT License. See the [LICENSE](LICENSE) file for details.