import os
import sys
import fnmatch # For gitignore style pattern matching
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QGroupBox, QCheckBox, QScrollArea,
    QRadioButton, QSpinBox, QStatusBar, QTabWidget, QProgressBar, QComboBox, QSplitter,
    QTextEdit, QTreeView, QFileSystemModel, QMainWindow, QAction, QToolBar,
    QFrame, QStyle, QStyleFactory, QMenu, QToolButton, QSizePolicy, QDialog,
    QListWidget, QListWidgetItem, QStackedWidget
)
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette, QPixmap, QCursor
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QSettings, QTimer, QDir

# --- Configuration ---
DEFAULT_EXCLUDE_DIRS = ['.git', 'node_modules', 'venv', '__pycache__', 'build', 'dist', '.svn', 'env', '.idea', '.vscode', 'target', 'out'] # Added target, out
DEFAULT_EXCLUDE_FILES = ['package-lock.json', 'yarn.lock', '*.pyc', '*.pyo', '*.exe', '*.dll', '*.so', '*.dylib', '*.o', '*.a', '*.class', '*.jar'] # Added Java related
DEFAULT_EXCLUDE_EXTENSIONS = [
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.ico', '.tif', '.tiff',
    # Videos
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv',
    # Audio
    '.mp3', '.wav', '.ogg', '.aac', '.flac',
    # Fonts
    '.ttf', '.otf', '.woff', '.woff2', '.eot',
    # Archives
    '.zip', '.rar', '.tar', '.gz', '.7z', '.bz2', '.iso',
    # Documents
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp',
    # Data/Logs/Temp
    '.db', '.sqlite', '.sqlite3', '.log', '.tmp', '.bak', '.swp',
    # Other Binary/Compiled
    '.bin', '.dat', '.cache', '.img', '.dmg', '.pkl', '.joblib'
]
DEFAULT_MAX_LINES_PER_CHUNK = 15000

# --- Worker Thread for Processing ---
class ProcessWorker(QThread):
    progress_update = pyqtSignal(str, int)  # Add percentage
    file_processed = pyqtSignal(str, str)   # filename and content
    finished = pyqtSignal(str, str, list) # structure_summary, combined_content, errors
    error = pyqtSignal(str)

    def __init__(self, root_dir, exclude_dirs, exclude_files, exclude_extensions, use_gitignore, include_structure, structure_only):
        super().__init__()
        self.root_dir = root_dir
        self.exclude_dirs = set(exclude_dirs)
        self.exclude_files = set(exclude_files)
        self.exclude_extensions = set(exclude_extensions)
        self.use_gitignore = use_gitignore
        self.include_structure = include_structure
        self.structure_only = structure_only # Added structure_only attribute
        self.gitignore_patterns = [] # Initialize gitignore_patterns

    def _load_gitignore(self):
        gitignore_path = os.path.join(self.root_dir, '.gitignore')
        patterns = []
        if self.use_gitignore and os.path.exists(gitignore_path):
            self.progress_update.emit("Reading .gitignore...", 0)
            try:
                with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f: # Added errors='ignore'
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            patterns.append(line)
                self.gitignore_patterns = patterns
                self.progress_update.emit(f"Loaded {len(patterns)} patterns from .gitignore.", 0)
            except Exception as e:
                self.progress_update.emit(f"Warning: Could not read .gitignore: {e}", 0)
        elif self.use_gitignore:
            self.progress_update.emit(".gitignore not found.", 0)


    def _is_excluded(self, path):
        """Checks if a file or directory should be excluded based on all exclusion rules."""
        # Get the relative path from the root directory
        rel_path = os.path.relpath(path, self.root_dir)
        if rel_path == '.': rel_path = ''  # Normalize root path

        # Get the basename for simple name checks
        basename = os.path.basename(path)

        # Check if it's a directory
        is_dir = os.path.isdir(path)

        # 1. Check simple directory name exclusion
        if is_dir and basename in self.exclude_dirs:
            return True

        # 2. Check file name/pattern exclusion
        if not is_dir:
            if basename in self.exclude_files:
                return True
            if any(fnmatch.fnmatchcase(basename, pattern) for pattern in self.exclude_files):
                return True

            # 3. Check file extension exclusion
            _, ext = os.path.splitext(basename)
            if ext.lower() in self.exclude_extensions:
                return True

        # 4. Check gitignore patterns
        if self.use_gitignore and self._is_excluded_by_gitignore(rel_path):
            return True

        # Not excluded by any rule
        return False

    def _is_excluded_by_gitignore(self, rel_path):
        """Checks if a relative path matches any gitignore pattern."""
        path_to_check = rel_path.replace(os.sep, '/')
        is_dir = os.path.isdir(os.path.join(self.root_dir, rel_path))

        # Optimization: Pre-compile or process patterns if many? For now, direct matching is fine.
        # Note: This basic implementation doesn't handle all complexities like negation precedence.

        for pattern in self.gitignore_patterns:
            original_pattern = pattern # Keep original for logging if needed

            # Handle negation patterns first (simplistic: if it matches negation, it's NOT excluded by *this* rule)
            # This doesn't handle complex cases like a later non-negation rule overriding a negation rule.
            is_negation = pattern.startswith('!')
            if is_negation:
                 pattern = pattern[1:]
                 if not pattern: continue # Ignore "!<empty>"

            # Basic handling for directory patterns ending with /
            is_dir_pattern = pattern.endswith('/')
            pattern = pattern.rstrip('/')
            if not pattern: continue # Ignore "/" or "!/" after stripping

            match = False
            # Handle patterns starting with / (match from root)
            if pattern.startswith('/'):
                pattern = pattern.lstrip('/')
                # Need match at the beginning
                # Check exact match or if it's a directory prefix
                if fnmatch.fnmatchcase(path_to_check, pattern) or \
                   (is_dir and path_to_check.startswith(pattern + '/')) or \
                   (not is_dir and path_to_check.startswith(pattern + '/')): # Also check files within root-matched dir
                    match = True

            # Handle patterns without leading / (match anywhere)
            else:
                # Check if the pattern matches the basename or any component
                components = path_to_check.split('/')
                if fnmatch.fnmatchcase(os.path.basename(path_to_check), pattern) or \
                    any(fnmatch.fnmatchcase(comp, pattern) for comp in components):
                    match = True


            # Apply match result based on pattern type (dir/file) and negation
            if match:
                # Check directory-specific matching (/ at end)
                if is_dir_pattern and not is_dir:
                    match = False # Rule is for a directory, but this is a file

            # If it matches, determine final exclusion based on negation
            if match:
                if is_negation:
                    # print(f"Path {rel_path} matches negation pattern {original_pattern}, keeping.")
                    return False # Match negation means "not excluded (by this rule)" - may be excluded by another
                else:
                    # print(f"Path {rel_path} excluded by pattern {original_pattern}")
                    return True # Excluded by a standard pattern

        # If no standard pattern matched, it's not excluded
        # If a negation pattern matched, it means it wasn't excluded *by that rule*,
        # but could still be excluded by a standard rule later (handled above).
        # So if we reach here, it's not excluded by any rule.
        return False

    def process_file(self, file_path):
        """Enhanced file processing with better encoding detection"""
        try:
            # Try to detect encoding
            import chardet
            with open(file_path, 'rb') as f:
                raw_data = f.read()
            detected = chardet.detect(raw_data)
            encoding = detected['encoding'] or 'utf-8'

            # Read with detected encoding
            content = raw_data.decode(encoding)
            return content
        except Exception as e:
            return f"[Error reading file: {e}]"

    def estimate_total_files(self):
        """Count total files for progress tracking"""
        total = 0
        for root, _, files in os.walk(self.root_dir):
            for file in files:
                if not self._is_excluded(os.path.join(root, file)):
                    total += 1
        return total

    def run(self):
        try:
            self._load_gitignore()

            structure_lines = []
            file_contents = []
            included_files_count = 0
            errors = []

            self.progress_update.emit("Starting directory scan...", 10)

            collected_items = []
            processed_paths = set() # To avoid processing duplicates if walk yields variations

            for root, dirs, files in os.walk(self.root_dir, topdown=True):
                rel_root = os.path.relpath(root, self.root_dir)
                if rel_root == '.': rel_root = '' # Avoid './' prefix

                # --- Directory Exclusion ---
                excluded_by_rule = set()
                original_dirs = list(dirs) # Keep original list for gitignore check

                # Apply simple name exclusion first
                dirs[:] = [d for d in dirs if d not in self.exclude_dirs]

                # Apply gitignore exclusion (more complex)
                final_dirs = []
                for d in dirs:
                    rel_path_dir = os.path.join(rel_root, d) if rel_root else d
                    if self._is_excluded_by_gitignore(rel_path_dir):
                        excluded_by_rule.add(d)
                    else:
                        final_dirs.append(d)
                dirs[:] = final_dirs # Modify dirs in place for os.walk

                # Store potentially included directories for structure summary
                for d in dirs:
                    rel_path = os.path.join(rel_root, d) if rel_root else d
                    norm_path = rel_path.replace(os.sep, '/')
                    if norm_path not in processed_paths:
                         collected_items.append((norm_path, True)) # Mark as directory
                         processed_paths.add(norm_path)


                # --- File Exclusion ---
                for file in files:
                    rel_path_file = os.path.join(rel_root, file) if rel_root else file
                    norm_path = rel_path_file.replace(os.sep, '/')

                    if norm_path in processed_paths:
                        continue # Should not happen often with os.walk but safety check

                    # Check standard name/pattern exclusions
                    if file in self.exclude_files or \
                       any(fnmatch.fnmatchcase(file, pattern) for pattern in self.exclude_files): # Use fnmatch for patterns
                        processed_paths.add(norm_path)
                        continue

                    # Check extension exclusions
                    _, ext = os.path.splitext(file)
                    if ext.lower() in self.exclude_extensions:
                        processed_paths.add(norm_path)
                        continue

                    # Check gitignore exclusions
                    if self._is_excluded_by_gitignore(rel_path_file):
                        processed_paths.add(norm_path)
                        continue

                    # If not excluded, add to collection
                    collected_items.append((norm_path, False)) # Mark as file
                    processed_paths.add(norm_path)

            # Sort collected items for predictable structure output
            collected_items.sort()

            # Generate structure summary (if requested) and process file contents
            self.progress_update.emit("Processing files...", 30)
            structure_summary = "Directory Structure:\n====================\n" if (self.include_structure or self.structure_only) else ""

            processed_items_count = 0
            total_items_to_process = len([item for item in collected_items if not item[1]]) # Count only files for processing

            for rel_path, is_dir in collected_items:
                if (self.include_structure or self.structure_only):
                    indent = rel_path.count('/')
                    # Adjust indent if it's a root file/dir (no slashes)
                    if indent == 0 and '/' in rel_path: # This handles cases where root might have had slashes normalized
                         pass # Keep indent 0
                    elif rel_path and '/' not in rel_path: # Root level item
                         indent = 0
                    else: # Increase indent for subitems
                        indent = rel_path.count('/')

                    prefix = "  " * indent + ("📁 " if is_dir else "📄 ")
                    base_name = os.path.basename(rel_path) if rel_path else os.path.basename(self.root_dir) # Handle root edge case
                    structure_lines.append(f"{prefix}{base_name}")

                if not is_dir and not self.structure_only: # Skip reading content if structure_only is true
                    processed_items_count += 1
                    if processed_items_count % 20 == 0: # Update progress periodically
                        # Calculate progress percentage (30% to 70% range for file processing)
                        progress_percent = 30 + int((processed_items_count / max(1, total_items_to_process)) * 40)
                        self.progress_update.emit(f"Processing file {processed_items_count}/{total_items_to_process}: {rel_path}", progress_percent)

                    file_path = os.path.join(self.root_dir, rel_path.replace('/', os.sep)) # Revert to OS separator for reading
                    try:
                        # Try reading as UTF-8 first, fallback to latin-1 for binary-like data
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                        except UnicodeDecodeError:
                            try:
                                with open(file_path, 'r', encoding='latin-1') as f:
                                    content = f.read()
                                content = f"[Warning: File read as latin-1, may not be correct]\n{content}"
                            except Exception as inner_e:
                                raise inner_e # Re-raise if latin-1 also fails

                        file_contents.append(f">>>File: {rel_path}\n\n{content}\n\n{'='*40}\n") # Add separator
                        included_files_count += 1

                    except Exception as e:
                        error_msg = f"Error reading file {rel_path}: {e}"
                        file_contents.append(f">>>File: {rel_path}\n\n[Error reading file: {e}]\n\n{'='*40}\n")
                        errors.append(error_msg)

            if (self.include_structure or self.structure_only):
                structure_summary += "\n".join(structure_lines) + "\n\n"
            else:
                structure_summary = "" # Ensure it's empty if not included

            combined_content = "".join(file_contents) if not self.structure_only else "" # Empty content for structure_only

            self.progress_update.emit(f"Scan complete. Included {included_files_count} files.", 70)
            self.finished.emit(structure_summary, combined_content, errors)

        except Exception as e:
            import traceback
            self.error.emit(f"An unexpected error occurred during processing:\n{traceback.format_exc()}")


# --- Settings Class ---
class AppSettings:
    def __init__(self):
        self.settings = QSettings("CodeCondenser", "CodeBaseCondenser")
        self.dark_mode = self.settings.value("dark_mode", False, type=bool)
        self.last_directory = self.settings.value("last_directory", "", type=str)
        self.last_output = self.settings.value("last_output", "", type=str)

    def save_settings(self):
        self.settings.setValue("dark_mode", self.dark_mode)
        self.settings.setValue("last_directory", self.last_directory)
        self.settings.setValue("last_output", self.last_output)

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self.save_settings()
        return self.dark_mode

# --- Main Application Window ---
class CodeBaseAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.settings = AppSettings()
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Initialize variables for download functionality
        self.last_output_path = None
        self.last_output_is_chunked = False

        self.initUI()
        self.apply_theme(self.settings.dark_mode)

    def initUI(self):
        self.setWindowTitle('Code Base Condenser')
        self.setGeometry(100, 100, 1000, 750)

        # Create toolbar
        self.create_toolbar()

        # Create main layout
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # Create stacked widget for multi-step interface
        self.stacked_widget = QStackedWidget()

        # Create pages
        self.create_project_selection_page()
        self.create_exclusion_page()
        self.create_output_options_page()
        self.create_summary_page()

        # Add pages to stacked widget
        self.stacked_widget.addWidget(self.project_page)
        self.stacked_widget.addWidget(self.exclusion_page)
        self.stacked_widget.addWidget(self.output_page)
        self.stacked_widget.addWidget(self.summary_page)

        # Add navigation buttons
        nav_layout = QHBoxLayout()

        self.back_button = QPushButton("Back")
        self.back_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.back_button.clicked.connect(self.go_back)
        self.back_button.setEnabled(False)

        self.next_button = QPushButton("Next")
        self.next_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        self.next_button.clicked.connect(self.go_next)

        self.run_button = QPushButton('Generate Condensed Code')
        self.run_button.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        self.run_button.clicked.connect(self.run_analysis)
        self.run_button.setVisible(False)

        nav_layout.addWidget(self.back_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_button)
        nav_layout.addWidget(self.run_button)

        # Add progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)

        # Add status bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready.")

        # Add widgets to main layout
        main_layout.addWidget(self.stacked_widget)
        main_layout.addWidget(self.progress_bar)
        main_layout.addLayout(nav_layout)
        main_layout.addWidget(self.status_bar)

    def create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Theme toggle action
        self.theme_action = QAction(QIcon(), "Toggle Dark Mode", self)
        self.theme_action.setCheckable(True)
        self.theme_action.setChecked(self.settings.dark_mode)
        self.theme_action.triggered.connect(self.toggle_theme)
        toolbar.addAction(self.theme_action)

        # Add spacer to push the following items to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        toolbar.addWidget(spacer)

        # Help action
        help_action = QAction(self.style().standardIcon(QStyle.SP_MessageBoxQuestion), "Help", self)
        help_action.triggered.connect(self.show_help)
        toolbar.addAction(help_action)

        # About action
        about_action = QAction(self.style().standardIcon(QStyle.SP_FileDialogInfoView), "About", self)
        about_action.triggered.connect(self.show_about)
        toolbar.addAction(about_action)

    def toggle_theme(self):
        dark_mode = self.settings.toggle_dark_mode()
        self.apply_theme(dark_mode)

    def apply_theme(self, dark_mode):
        if dark_mode:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #2d2d2d;
                    color: #e0e0e0;
                    font-family: 'Segoe UI', Arial, sans-serif;
                }
                QLabel, QCheckBox, QRadioButton {
                    font-size: 13px;
                    color: #e0e0e0;
                }
                QLineEdit, QSpinBox, QComboBox, QTextEdit {
                    padding: 8px;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    font-size: 13px;
                    background-color: #3d3d3d;
                    color: #e0e0e0;
                    selection-background-color: #0078d7;
                }
                QSpinBox:disabled {
                    background-color: #353535;
                    color: #777777;
                }
                QPushButton {
                    background-color: #0078d7;
                    color: white;
                    padding: 8px 16px;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #0063b1;
                }
                QPushButton:disabled {
                    background-color: #444444;
                    color: #777777;
                }
                QGroupBox {
                    border: 1px solid #555555;
                    border-radius: 5px;
                    margin-top: 15px;
                    padding-top: 10px;
                    font-weight: bold;
                    color: #e0e0e0;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 10px;
                    padding: 0 3px 0 3px;
                    color: #e0e0e0;
                }
                QScrollArea, QListWidget, QTreeView {
                    border: 1px solid #555555;
                    background-color: #3d3d3d;
                }
                QScrollArea > QWidget > QWidget {
                    background-color: #3d3d3d;
                }
                QStatusBar {
                    font-size: 12px;
                    color: #b0b0b0;
                }
                QTabWidget::pane {
                    border: 1px solid #555555;
                    background-color: #2d2d2d;
                }
                QTabBar::tab {
                    background-color: #3d3d3d;
                    color: #e0e0e0;
                    padding: 8px 12px;
                    border: 1px solid #555555;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #0078d7;
                }
                QProgressBar {
                    border: 1px solid #555555;
                    border-radius: 4px;
                    background-color: #3d3d3d;
                    text-align: center;
                    color: #e0e0e0;
                }
                QProgressBar::chunk {
                    background-color: #0078d7;
                    width: 10px;
                    margin: 0.5px;
                }
                QToolBar {
                    background-color: #2d2d2d;
                    border-bottom: 1px solid #555555;
                    spacing: 5px;
                }
                QToolButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 4px;
                    padding: 4px;
                }
                QToolButton:hover {
                    background-color: #3d3d3d;
                }
                QMenu {
                    background-color: #2d2d2d;
                    border: 1px solid #555555;
                }
                QMenu::item {
                    padding: 6px 20px;
                    color: #e0e0e0;
                }
                QMenu::item:selected {
                    background-color: #0078d7;
                }
            """)
            # Set dark mode icon
            self.theme_action.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #f5f5f5;
                    color: #333333;
                    font-family: 'Segoe UI', Arial, sans-serif;
                }
                QLabel, QCheckBox, QRadioButton {
                    font-size: 13px;
                    color: #333333;
                }
                QLineEdit, QSpinBox, QComboBox, QTextEdit {
                    padding: 8px;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    font-size: 13px;
                    background-color: #ffffff;
                    color: #333333;
                    selection-background-color: #0078d7;
                }
                QSpinBox:disabled {
                    background-color: #f0f0f0;
                    color: #888888;
                }
                QPushButton {
                    background-color: #0078d7;
                    color: white;
                    padding: 8px 16px;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #0063b1;
                }
                QPushButton:disabled {
                    background-color: #dddddd;
                    color: #888888;
                }
                QGroupBox {
                    border: 1px solid #cccccc;
                    border-radius: 5px;
                    margin-top: 15px;
                    padding-top: 10px;
                    font-weight: bold;
                    color: #333333;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 10px;
                    padding: 0 3px 0 3px;
                    color: #555555;
                }
                QScrollArea, QListWidget, QTreeView {
                    border: 1px solid #cccccc;
                    background-color: #ffffff;
                }
                QScrollArea > QWidget > QWidget {
                    background-color: #ffffff;
                }
                QStatusBar {
                    font-size: 12px;
                    color: #666666;
                }
                QTabWidget::pane {
                    border: 1px solid #cccccc;
                    background-color: #f5f5f5;
                }
                QTabBar::tab {
                    background-color: #e0e0e0;
                    color: #333333;
                    padding: 8px 12px;
                    border: 1px solid #cccccc;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background-color: #0078d7;
                    color: white;
                }
                QProgressBar {
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    background-color: #f0f0f0;
                    text-align: center;
                    color: #333333;
                }
                QProgressBar::chunk {
                    background-color: #0078d7;
                    width: 10px;
                    margin: 0.5px;
                }
                QToolBar {
                    background-color: #f5f5f5;
                    border-bottom: 1px solid #cccccc;
                    spacing: 5px;
                }
                QToolButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 4px;
                    padding: 4px;
                }
                QToolButton:hover {
                    background-color: #e0e0e0;
                }
                QMenu {
                    background-color: #f5f5f5;
                    border: 1px solid #cccccc;
                }
                QMenu::item {
                    padding: 6px 20px;
                    color: #333333;
                }
                QMenu::item:selected {
                    background-color: #0078d7;
                    color: white;
                }
            """)
            # Set light mode icon
            self.theme_action.setIcon(self.style().standardIcon(QStyle.SP_DialogCancelButton))

    def show_help(self):
        help_text = """
        <h2>Code Base Condenser Help</h2>
        <p>This tool helps you prepare your codebase for analysis by Large Language Models (LLMs).</p>

        <h3>Basic Steps:</h3>
        <ol>
            <li><b>Select Project Directory</b> - Choose the root folder of your project</li>
            <li><b>Configure Exclusions</b> - Specify which files and directories to exclude</li>
            <li><b>Choose Output Options</b> - Select output format and chunking options</li>
            <li><b>Generate Code</b> - Process your codebase and save the results</li>
        </ol>

        <h3>Tips:</h3>
        <ul>
            <li>Use structure-only mode first to get an overview of your project</li>
            <li>For large projects, use chunking to stay within LLM context limits</li>
            <li>Include the directory structure in the first chunk for better context</li>
            <li>Consider excluding test files, documentation, or other non-essential code</li>
        </ul>
        """

        help_dialog = QDialog(self)
        help_dialog.setWindowTitle("Help")
        help_dialog.setMinimumSize(600, 400)

        layout = QVBoxLayout(help_dialog)

        help_text_edit = QTextEdit()
        help_text_edit.setReadOnly(True)
        help_text_edit.setHtml(help_text)

        close_button = QPushButton("Close")
        close_button.clicked.connect(help_dialog.accept)

        layout.addWidget(help_text_edit)
        layout.addWidget(close_button, alignment=Qt.AlignCenter)

        help_dialog.exec_()

    def show_about(self):
        about_text = """
        <h2>Code Base Condenser</h2>
        <p>Version 2.0</p>
        <p>A tool designed to help developers prepare their codebase for Large Language Model (LLM) analysis.</p>
        <p>This application condenses multiple source files into a single readable format or structured chunks.</p>
        <p>Created by David Oppenheim (GitHub: <a href="https://github.com/Sqygey">Sqygey</a>)</p>
        <p>&copy; 2023 - Open Source under MIT License</p>
        """

        # Create a custom dialog for the about box
        about_dialog = QDialog(self)
        about_dialog.setWindowTitle("About Code Base Condenser")
        about_dialog.setMinimumWidth(450)

        layout = QVBoxLayout(about_dialog)

        # Add icon
        icon_label = QLabel()
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor("#0078d7"))  # Blue color
        icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        # Add text
        text_label = QLabel()
        text_label.setOpenExternalLinks(True)  # Allow opening links
        text_label.setTextFormat(Qt.RichText)
        text_label.setText(about_text)
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        # Add OK button
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(about_dialog.accept)
        layout.addWidget(ok_button, alignment=Qt.AlignCenter)

        about_dialog.exec_()

    def create_project_selection_page(self):
        self.project_page = QWidget()
        layout = QVBoxLayout(self.project_page)
        layout.setSpacing(15)

        # Header
        header_label = QLabel("Step 1: Select Project Directory")
        header_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)

        # Description
        desc_label = QLabel("Select the root directory of your project to analyze. This should be the main folder containing your source code.")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Directory selection
        dir_group = QGroupBox("Project Directory")
        dir_layout = QVBoxLayout(dir_group)

        dir_select_layout = QHBoxLayout()
        self.directory_entry = QLineEdit()
        self.directory_entry.setPlaceholderText("Select the root directory of your project")
        if self.settings.last_directory:
            self.directory_entry.setText(self.settings.last_directory)

        dir_button = QPushButton('Browse...')
        dir_button.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
        dir_button.clicked.connect(self.choose_directory)

        dir_select_layout.addWidget(self.directory_entry)
        dir_select_layout.addWidget(dir_button)
        dir_layout.addLayout(dir_select_layout)

        # File browser
        file_browser_label = QLabel("Project Structure Preview:")
        dir_layout.addWidget(file_browser_label)

        self.file_model = QFileSystemModel()
        self.file_model.setRootPath("")

        self.tree_view = QTreeView()
        self.tree_view.setModel(self.file_model)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(20)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setColumnWidth(0, 250)
        self.tree_view.setMinimumHeight(300)

        dir_layout.addWidget(self.tree_view)

        layout.addWidget(dir_group)

        # Output file selection
        output_group = QGroupBox("Output File")
        output_layout = QVBoxLayout(output_group)

        output_desc = QLabel("Specify where to save the condensed code output:")
        output_layout.addWidget(output_desc)

        output_select_layout = QHBoxLayout()
        self.output_entry = QLineEdit()
        self.output_entry.setPlaceholderText("Specify output .txt file (e.g., project_code.txt)")
        if self.settings.last_output:
            self.output_entry.setText(self.settings.last_output)

        output_button = QPushButton('Save As...')
        output_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        output_button.clicked.connect(self.choose_output_file)

        output_select_layout.addWidget(self.output_entry)
        output_select_layout.addWidget(output_button)
        output_layout.addLayout(output_select_layout)

        layout.addWidget(output_group)
        layout.addStretch()

    def create_exclusion_page(self):
        self.exclusion_page = QWidget()
        layout = QVBoxLayout(self.exclusion_page)
        layout.setSpacing(15)

        # Header
        header_label = QLabel("Step 2: Configure Exclusions")
        header_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)

        # Description
        desc_label = QLabel("Configure which files and directories to exclude from the analysis. This helps focus on relevant code and reduces output size.")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Exclude directories
        dirs_group = QGroupBox("Exclude Directories")
        dirs_layout = QVBoxLayout(dirs_group)

        dirs_desc = QLabel("Specify directories to exclude (comma-separated):")
        dirs_layout.addWidget(dirs_desc)

        self.exclude_dirs_entry = QLineEdit()
        self.exclude_dirs_entry.setText(','.join(DEFAULT_EXCLUDE_DIRS))
        self.exclude_dirs_entry.setToolTip("List of directory names to completely ignore (case-sensitive).")
        dirs_layout.addWidget(self.exclude_dirs_entry)

        layout.addWidget(dirs_group)

        # Exclude files
        files_group = QGroupBox("Exclude Files")
        files_layout = QVBoxLayout(files_group)

        files_desc = QLabel("Specify files or patterns to exclude (comma-separated):")
        files_layout.addWidget(files_desc)

        self.exclude_files_entry = QLineEdit()
        self.exclude_files_entry.setText(','.join(DEFAULT_EXCLUDE_FILES))
        self.exclude_files_entry.setToolTip("List of specific file names or wildcard patterns (e.g., *.log, setup.?) to ignore (case-sensitive).")
        files_layout.addWidget(self.exclude_files_entry)

        # Use .gitignore
        self.use_gitignore_checkbox = QCheckBox("Use .gitignore rules found in the project directory")
        self.use_gitignore_checkbox.setChecked(True)
        self.use_gitignore_checkbox.setToolTip("If checked, rules from a .gitignore file in the root directory will also be applied (basic pattern support).")
        files_layout.addWidget(self.use_gitignore_checkbox)

        layout.addWidget(files_group)

        # Exclude extensions
        ext_group = QGroupBox("Exclude File Extensions")
        ext_layout = QVBoxLayout(ext_group)

        ext_desc = QLabel("Select file extensions to exclude:")
        ext_layout.addWidget(ext_desc)

        # Create a scrollable area for extensions
        ext_scroll = QScrollArea()
        ext_scroll.setWidgetResizable(True)
        ext_scroll.setMinimumHeight(200)

        ext_content = QWidget()
        ext_grid = QHBoxLayout(ext_content)

        col_layouts = [QVBoxLayout(), QVBoxLayout(), QVBoxLayout()]

        self.extension_checkboxes = {}
        col_count = len(col_layouts)
        sorted_extensions = sorted(DEFAULT_EXCLUDE_EXTENSIONS, key=str.lower)
        items_per_col = (len(sorted_extensions) + col_count - 1) // col_count

        for i, ext in enumerate(sorted_extensions):
            checkbox = QCheckBox(ext)
            checkbox.setChecked(True)
            self.extension_checkboxes[ext] = checkbox
            col_index = i // items_per_col
            col_layouts[col_index].addWidget(checkbox)

        for col_layout in col_layouts:
            col_layout.addStretch()
            ext_grid.addLayout(col_layout)

        ext_scroll.setWidget(ext_content)
        ext_layout.addWidget(ext_scroll)

        # Custom extensions
        custom_ext_layout = QHBoxLayout()
        custom_ext_layout.addWidget(QLabel("Custom extensions to exclude:"))
        self.custom_exclude_extensions_entry = QLineEdit()
        self.custom_exclude_extensions_entry.setPlaceholderText("E.g., .custom, .generated")
        self.custom_exclude_extensions_entry.setToolTip("Additional file extensions to exclude (comma-separated, with or without dots).")
        custom_ext_layout.addWidget(self.custom_exclude_extensions_entry)
        ext_layout.addLayout(custom_ext_layout)

        layout.addWidget(ext_group)
        layout.addStretch()

    def create_output_options_page(self):
        self.output_page = QWidget()
        layout = QVBoxLayout(self.output_page)
        layout.setSpacing(15)

        # Header
        header_label = QLabel("Step 3: Output Options")
        header_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)

        # Description
        desc_label = QLabel("Configure how the output should be formatted and organized.")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Output format options
        format_group = QGroupBox("Output Format")
        format_layout = QVBoxLayout(format_group)

        # File format options
        file_format_layout = QVBoxLayout()
        self.single_file_radio = QRadioButton("Single File Output")
        self.single_file_radio.setChecked(True)
        self.single_file_radio.toggled.connect(self.toggle_chunk_options)

        self.chunked_file_radio = QRadioButton("Split into Multiple Chunks (for large projects)")
        self.chunked_file_radio.toggled.connect(self.toggle_chunk_options)

        file_format_layout.addWidget(self.single_file_radio)
        file_format_layout.addWidget(self.chunked_file_radio)

        # Chunk size options
        self.chunk_options_widget = QWidget()
        chunk_size_layout = QHBoxLayout(self.chunk_options_widget)
        chunk_size_layout.setContentsMargins(20, 0, 0, 0)

        self.max_lines_label = QLabel("Maximum lines per chunk:")
        self.max_lines_spinbox = QSpinBox()
        self.max_lines_spinbox.setRange(1000, 100000)
        self.max_lines_spinbox.setValue(DEFAULT_MAX_LINES_PER_CHUNK)
        self.max_lines_spinbox.setToolTip(f"Approximate maximum number of lines per chunk file (Default: {DEFAULT_MAX_LINES_PER_CHUNK}). Splits occur between files.")

        chunk_size_layout.addWidget(self.max_lines_label)
        chunk_size_layout.addWidget(self.max_lines_spinbox)
        chunk_size_layout.addStretch()

        file_format_layout.addWidget(self.chunk_options_widget)
        format_layout.addLayout(file_format_layout)

        layout.addWidget(format_group)

        # Structure options
        structure_group = QGroupBox("Structure Options")
        structure_layout = QVBoxLayout(structure_group)

        self.include_structure_checkbox = QCheckBox("Include directory structure in output")
        self.include_structure_checkbox.setChecked(True)
        self.include_structure_checkbox.toggled.connect(self.toggle_structure_options)
        structure_layout.addWidget(self.include_structure_checkbox)

        self.structure_only_checkbox = QCheckBox("Generate structure-only output (no file contents)")
        self.structure_only_checkbox.setChecked(False)
        structure_layout.addWidget(self.structure_only_checkbox)

        layout.addWidget(structure_group)

        # Preview section
        preview_group = QGroupBox("Output Preview")
        preview_layout = QVBoxLayout(preview_group)

        preview_desc = QLabel("Example of how the output will be formatted:")
        preview_layout.addWidget(preview_desc)

        preview_text = QTextEdit()
        preview_text.setReadOnly(True)
        preview_text.setMinimumHeight(150)
        preview_text.setText("""Directory Structure:
====================
📁 root
  📁 src
    📄 main.py
  📁 tests
    📄 test_main.py
  📄 README.md

>>>File: src/main.py

def hello_world():
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()

========================================

>>>File: tests/test_main.py

import unittest
from src.main import hello_world

class TestMain(unittest.TestCase):
    def test_hello_world(self):
        # Just a placeholder test
        self.assertTrue(True)

========================================
""")
        preview_layout.addWidget(preview_text)

        layout.addWidget(preview_group)
        layout.addStretch()

        # Initialize chunk options visibility
        self.toggle_chunk_options()

    def create_summary_page(self):
        self.summary_page = QWidget()
        layout = QVBoxLayout(self.summary_page)
        layout.setSpacing(15)

        # Header
        header_label = QLabel("Step 4: Summary & Generate")
        header_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)

        # Description
        desc_label = QLabel("Review your settings and generate the condensed code.")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Summary group
        summary_group = QGroupBox("Configuration Summary")
        summary_layout = QVBoxLayout(summary_group)

        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMinimumHeight(300)
        summary_layout.addWidget(self.summary_text)

        layout.addWidget(summary_group)

        # Results group (initially empty)
        self.results_group = QGroupBox("Results")
        self.results_group.setVisible(False)
        self.results_layout = QVBoxLayout(self.results_group)

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_layout.addWidget(self.results_text)

        layout.addWidget(self.results_group)
        layout.addStretch()

    def go_back(self):
        current_index = self.stacked_widget.currentIndex()
        if current_index > 0:
            self.stacked_widget.setCurrentIndex(current_index - 1)
            self.update_navigation_buttons()

    def go_next(self):
        current_index = self.stacked_widget.currentIndex()
        if current_index < self.stacked_widget.count() - 1:
            # Validate current page
            if current_index == 0 and not self.validate_project_page():
                return

            self.stacked_widget.setCurrentIndex(current_index + 1)

            # If moving to summary page, update the summary
            if current_index + 1 == 3:  # Summary page index
                self.update_summary()

            self.update_navigation_buttons()

    def update_navigation_buttons(self):
        current_index = self.stacked_widget.currentIndex()

        # Enable/disable back button
        self.back_button.setEnabled(current_index > 0)

        # Show/hide next and run buttons
        is_last_page = current_index == self.stacked_widget.count() - 1
        self.next_button.setVisible(not is_last_page)
        self.run_button.setVisible(is_last_page)

    def validate_project_page(self):
        # Check if directory is selected
        if not self.directory_entry.text() or not os.path.isdir(self.directory_entry.text()):
            QMessageBox.warning(self, "Input Error", "Please select a valid project directory.")
            return False

        # Check if output file is specified
        if not self.output_entry.text():
            QMessageBox.warning(self, "Input Error", "Please specify an output file name/path.")
            return False

        # Check if output directory exists
        output_dir = os.path.dirname(self.output_entry.text())
        if output_dir and not os.path.isdir(output_dir):
            QMessageBox.warning(self, "Input Error", f"The output directory does not exist:\n{output_dir}")
            return False

        # Save settings
        self.settings.last_directory = self.directory_entry.text()
        self.settings.last_output = self.output_entry.text()
        self.settings.save_settings()

        # Update file browser
        self.file_model.setRootPath(self.directory_entry.text())
        self.tree_view.setRootIndex(self.file_model.index(self.directory_entry.text()))

        return True

    def update_summary(self):
        # Get all settings
        project_dir = self.directory_entry.text()
        output_path = self.output_entry.text()
        exclude_dirs = self.exclude_dirs_entry.text()
        exclude_files = self.exclude_files_entry.text()
        use_gitignore = self.use_gitignore_checkbox.isChecked()

        # Count checked extensions
        checked_exts = [ext for ext, checkbox in self.extension_checkboxes.items() if checkbox.isChecked()]
        custom_exts = self.custom_exclude_extensions_entry.text()

        output_type = "Single file" if self.single_file_radio.isChecked() else "Multiple chunks"
        max_lines = self.max_lines_spinbox.value() if self.chunked_file_radio.isChecked() else "N/A"
        include_structure = self.include_structure_checkbox.isChecked()
        structure_only = self.structure_only_checkbox.isChecked()

        # Format summary
        summary = f"""<h3>Project Information</h3>
<p><b>Project Directory:</b> {project_dir}</p>
<p><b>Output Path:</b> {output_path}</p>

<h3>Exclusion Rules</h3>
<p><b>Excluded Directories:</b> {exclude_dirs}</p>
<p><b>Excluded Files/Patterns:</b> {exclude_files}</p>
<p><b>Use .gitignore:</b> {"Yes" if use_gitignore else "No"}</p>
<p><b>Excluded Extensions:</b> {len(checked_exts)} selected</p>
<p><b>Custom Extensions:</b> {custom_exts if custom_exts else "None"}</p>

<h3>Output Options</h3>
<p><b>Output Type:</b> {output_type}</p>
<p><b>Max Lines Per Chunk:</b> {max_lines}</p>
<p><b>Include Directory Structure:</b> {"Yes" if include_structure else "No"}</p>
<p><b>Structure-Only Output:</b> {"Yes" if structure_only else "No"}</p>
"""

        self.summary_text.setHtml(summary)

    def toggle_chunk_options(self):
        self.chunk_options_widget.setVisible(self.chunked_file_radio.isChecked())
        self.max_lines_spinbox.setEnabled(self.chunked_file_radio.isChecked())

    def toggle_structure_options(self):
        self.structure_only_checkbox.setEnabled(self.include_structure_checkbox.isChecked())
        if not self.include_structure_checkbox.isChecked():
            self.structure_only_checkbox.setChecked(False)

    def choose_directory(self):
        # Try to start in the currently entered directory or user's home
        start_dir = self.directory_entry.text() or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(self, "Select Project Directory", start_dir)
        if directory:
            self.directory_entry.setText(directory)
            # Auto-suggest output file name based on directory if output is empty
            if not self.output_entry.text().strip():
                base_name = os.path.basename(directory)
                # Suggest output in the *parent* directory of the selected project, or home if no parent
                parent_dir = os.path.dirname(directory) or os.path.expanduser("~")
                suggested_path = os.path.join(parent_dir, f"{base_name}_codebase.txt")
                self.output_entry.setText(suggested_path)

            # Update file browser
            self.file_model.setRootPath(directory)
            self.tree_view.setRootIndex(self.file_model.index(directory))

            # Save to settings
            self.settings.last_directory = directory
            self.settings.save_settings()

    def choose_output_file(self):
        # Suggest a directory based on the input directory or output entry
        current_output = self.output_entry.text()
        default_dir = os.path.dirname(current_output) or os.path.dirname(self.directory_entry.text()) or os.path.expanduser("~")
        suggested_filename = current_output or os.path.join(default_dir, "project_codebase.txt")

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Output File", suggested_filename, "Text Files (*.txt);;All Files (*)")
        if file_path:
            # Ensure it has a .txt extension if none provided and filter was txt
            if not os.path.splitext(file_path)[1] and 'Text Files' in _:
                file_path += '.txt'
            self.output_entry.setText(file_path)

            # Save to settings
            self.settings.last_output = file_path
            self.settings.save_settings()

    def _parse_exclusions(self):
        """Parses exclusion lists from the GUI, handling whitespace."""
        # Use case-sensitive matching for dirs/files by default, as gitignore often is
        dirs = {d.strip() for d in self.exclude_dirs_entry.text().split(',') if d.strip()}
        files = {f.strip() for f in self.exclude_files_entry.text().split(',') if f.strip()}

        # Extensions are typically case-insensitive
        checked_exts = {ext.lower() for ext, checkbox in self.extension_checkboxes.items() if checkbox.isChecked()}
        custom_exts_raw = self.custom_exclude_extensions_entry.text().split(',')
        custom_exts = {ext.strip().lower() for ext in custom_exts_raw if ext.strip()}
        # Ensure extensions start with a dot
        custom_exts_dotted = {ext if ext.startswith('.') else '.' + ext for ext in custom_exts}

        all_extensions = checked_exts.union(custom_exts_dotted)
        return dirs, files, all_extensions

    def run_analysis(self):
        # Get values from UI
        root_dir = self.directory_entry.text()
        output_path = self.output_entry.text()

        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # Disable navigation
        self.back_button.setEnabled(False)
        self.run_button.setEnabled(False)

        # Update status
        self.status_bar.showMessage("Starting analysis...")

        # Parse exclusions
        exclude_dirs, exclude_files, exclude_extensions = self._parse_exclusions()
        use_gitignore = self.use_gitignore_checkbox.isChecked()
        include_structure = self.include_structure_checkbox.isChecked()
        structure_only = self.structure_only_checkbox.isChecked()

        # Start worker thread
        self.worker = ProcessWorker(
            root_dir,
            exclude_dirs,
            exclude_files,
            exclude_extensions,
            use_gitignore,
            include_structure,
            structure_only
        )

        # Connect signals
        self.worker.progress_update.connect(self.update_status)
        self.worker.finished.connect(self.handle_results)
        self.worker.error.connect(self.handle_error)

        # Start processing
        self.worker.start()

    def update_status(self, message, percent=0):
        """Update the status bar and progress bar with the current status"""
        self.status_bar.showMessage(message)
        if percent > 0:
            self.progress_bar.setValue(percent)
            # Make sure progress bar is visible
            self.progress_bar.setVisible(True)

    def handle_error(self, error_message):
        # Log detailed error to console
        print(f"Error signal received:\n{error_message}")

        # Show a simpler message in the dialog
        short_error = "\n".join(error_message.splitlines()[:5])
        if len(error_message.splitlines()) > 5:
            short_error += "\n..."

        QMessageBox.critical(self, "Error During Processing",
                            f"An error occurred:\n{short_error}\n\nCheck console for details.")

        # Update UI
        self.status_bar.showMessage("Processing failed. See console for details.")
        self.progress_bar.setVisible(False)
        self.back_button.setEnabled(True)
        self.run_button.setEnabled(True)

    def handle_results(self, structure_summary, combined_content, errors):
        # Get values from worker and UI
        structure_only = self.worker.structure_only
        output_path = self.output_entry.text()
        is_chunked = self.chunked_file_radio.isChecked()
        max_lines = self.max_lines_spinbox.value() if is_chunked else -1

        # Debug print
        print(f"DEBUG: handle_results called with output_path={output_path}, is_chunked={is_chunked}")

        self.status_bar.showMessage("Processing finished. Saving results...")
        self.progress_bar.setValue(75)  # 75% complete

        # Store output information for the download button
        self.last_output_path = output_path
        self.last_output_is_chunked = is_chunked

        try:
            # Combine content
            full_content_to_write = structure_summary + combined_content

            # Check if content is empty
            if not full_content_to_write.strip() and not structure_only:
                QMessageBox.warning(self, "No Content",
                                   "No text content was found or generated after applying exclusions.")
                self.status_bar.showMessage("Ready. No content generated.")
                self.progress_bar.setVisible(False)
                self.back_button.setEnabled(True)
                self.run_button.setEnabled(True)
                return

            # Prepare output path
            output_dir = os.path.dirname(output_path)
            base_name, extension = os.path.splitext(output_path)
            if not extension:
                extension = '.txt'
                output_path = base_name + extension

            # Create output directory if needed
            if output_dir and not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir)
                except OSError as e:
                    raise OSError(f"Failed to create output directory '{output_dir}': {e}")

            # Save content
            if is_chunked:
                parts = self.split_content_smart(full_content_to_write, max_lines)
                num_files = len(parts)

                if num_files == 0:
                    # No content to save
                    pass
                elif num_files == 1:
                    # Only one chunk, save as single file
                    self.status_bar.showMessage(f"Saving single file: {os.path.basename(output_path)}")
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(parts[0])
                    self.show_success_message(f"Analysis complete. Output saved to:\n{output_path}", output_path)
                else:
                    # Save multiple chunk files
                    output_dir_display = output_dir if output_dir else os.getcwd()
                    base_filename = os.path.basename(base_name)
                    self.status_bar.showMessage(f"Saving {num_files} chunk files...")

                    saved_files = []
                    for i, part in enumerate(parts, 1):
                        if structure_only:
                            chunk_filename = f"{base_filename}-structure-PART-{i}{extension}"
                        else:
                            chunk_filename = f"{base_filename}-PART-{i}{extension}"

                        part_file_path = os.path.join(output_dir, chunk_filename)
                        self.update_status(f"Saving chunk {i}/{num_files}: {chunk_filename}",
                                          75 + (i / num_files * 25))  # Progress from 75% to 100%

                        with open(part_file_path, 'w', encoding='utf-8') as f:
                            f.write(part)
                        saved_files.append(part_file_path)

                    self.show_success_message(
                        f"Analysis complete. Output split into {num_files} files in directory:\n{output_dir_display}",
                        output_dir_display, True)
            else:
                # Single file output
                if structure_only:
                    output_path_structure = base_name + "-structure" + extension
                    output_path = output_path_structure

                self.status_bar.showMessage(f"Saving single file: {os.path.basename(output_path)}")
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(full_content_to_write)

                self.show_success_message(f"Analysis complete. Output saved to:\n{output_path}", output_path)

            # Report any non-critical errors
            if errors:
                error_details = "\n".join(errors[:10])
                if len(errors) > 10:
                    error_details += f"\n... and {len(errors) - 10} more."
                QMessageBox.warning(self, "File Reading Issues",
                                   f"Some files could not be read properly or were skipped due to encoding issues:\n{error_details}")

            # Update results in the UI
            print(f"DEBUG: Calling show_results with output_path={output_path}, num_files={num_files if is_chunked and num_files > 1 else 1}")
            self.show_results(output_path, num_files if is_chunked and num_files > 1 else 1)

        except Exception as e:
            import traceback
            self.handle_error(f"An error occurred while saving the file(s):\n{traceback.format_exc()}")
        finally:
            # Reset UI
            if not self.status_bar.currentMessage().startswith("Processing failed"):
                self.status_bar.showMessage("Ready.")
            self.progress_bar.setValue(100)
            self.back_button.setEnabled(True)
            self.run_button.setEnabled(True)

    def open_file(self, file_path):
        """Opens a file using the system's default application"""
        try:
            # Use the appropriate method based on the operating system
            if sys.platform.startswith('darwin'):  # macOS
                os.system(f'open "{file_path}"')
            elif sys.platform.startswith('win'):   # Windows
                os.system(f'start "" "{file_path}"')
            else:  # Linux and other Unix-like systems
                os.system(f'xdg-open "{file_path}"')
            self.status_bar.showMessage(f"Opened file: {file_path}")
        except Exception as e:
            self.status_bar.showMessage(f"Error opening file: {e}")

    def open_directory(self, dir_path):
        """Opens a directory using the system's file explorer"""
        try:
            # Use the appropriate method based on the operating system
            if sys.platform.startswith('darwin'):  # macOS
                os.system(f'open "{dir_path}"')
            elif sys.platform.startswith('win'):   # Windows
                os.system(f'explorer "{dir_path}"')
            else:  # Linux and other Unix-like systems
                os.system(f'xdg-open "{dir_path}"')
            self.status_bar.showMessage(f"Opened directory: {dir_path}")
        except Exception as e:
            self.status_bar.showMessage(f"Error opening directory: {e}")

    def download_file(self, file_path):
        """Allows the user to download/save a copy of the generated file to a new location"""
        try:
            # Get the file name for the default save name
            file_name = os.path.basename(file_path)

            # Open a save dialog to let the user choose where to save the file
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Download File",
                file_name,
                "Text Files (*.txt);;All Files (*)"
            )

            if save_path:
                # Ensure it has a .txt extension if none provided and filter was txt
                if not os.path.splitext(save_path)[1] and 'Text Files' in _:
                    save_path += '.txt'

                # Copy the file to the new location
                import shutil
                shutil.copy2(file_path, save_path)

                self.status_bar.showMessage(f"File downloaded to: {save_path}")

                # Ask if the user wants to open the downloaded file
                reply = QMessageBox.question(
                    self,
                    "Download Complete",
                    f"File downloaded to:\n{save_path}\n\nWould you like to open it now?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply == QMessageBox.Yes:
                    self.open_file(save_path)
        except Exception as e:
            self.status_bar.showMessage(f"Error downloading file: {e}")
            QMessageBox.critical(self, "Download Error", f"Failed to download file:\n{e}")

    def download_directory(self, dir_path, base_name):
        """Allows the user to download/save a copy of all generated files to a new location"""
        try:
            # Open a directory selection dialog
            save_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Download Directory",
                os.path.expanduser("~")
            )

            if save_dir:
                # Get all files in the source directory that match the base name pattern
                import glob
                import shutil

                # Get the base name without extension
                base_name_no_ext = os.path.splitext(base_name)[0]

                # Find all files matching the pattern
                file_pattern = os.path.join(dir_path, f"{base_name_no_ext}*")
                files_to_copy = glob.glob(file_pattern)

                if not files_to_copy:
                    QMessageBox.warning(self, "No Files Found", f"No files matching {base_name_no_ext}* were found in {dir_path}")
                    return

                # Copy each file to the destination directory
                for file_path in files_to_copy:
                    file_name = os.path.basename(file_path)
                    dest_path = os.path.join(save_dir, file_name)
                    shutil.copy2(file_path, dest_path)

                self.status_bar.showMessage(f"{len(files_to_copy)} files downloaded to: {save_dir}")

                # Ask if the user wants to open the download directory
                reply = QMessageBox.question(
                    self,
                    "Download Complete",
                    f"{len(files_to_copy)} files downloaded to:\n{save_dir}\n\nWould you like to open this directory now?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply == QMessageBox.Yes:
                    self.open_directory(save_dir)
        except Exception as e:
            self.status_bar.showMessage(f"Error downloading files: {e}")
            QMessageBox.critical(self, "Download Error", f"Failed to download files:\n{e}")

    def toolbar_download_handler(self):
        """Handles download button clicks from the toolbar"""
        try:
            # Check if we have output information
            if not hasattr(self, 'last_output_path') or not self.last_output_path:
                QMessageBox.warning(self, "No File Available", "No generated file is available for download.")
                return

            # Call the appropriate download function based on the output type
            if hasattr(self, 'last_output_is_chunked') and self.last_output_is_chunked:
                # For chunked output, download all files
                dir_path = os.path.dirname(self.last_output_path)
                base_name = os.path.basename(self.last_output_path)
                self.download_directory(dir_path, base_name)
            else:
                # For single file output, download the file
                self.download_file(self.last_output_path)
        except Exception as e:
            self.status_bar.showMessage(f"Error handling download: {e}")
            QMessageBox.critical(self, "Download Error", f"Failed to download file(s):\n{e}")

    def show_success_message(self, message, file_path=None, is_directory=False):
        """Shows a success message with options to open the file or directory"""
        # Debug print
        print(f"DEBUG: show_success_message called with file_path={file_path}, is_directory={is_directory}")

        # Create a custom dialog instead of QMessageBox for better button control
        dialog = QDialog(self)
        dialog.setWindowTitle("Success")
        dialog.setMinimumWidth(400)

        # Create layout
        layout = QVBoxLayout(dialog)

        # Add icon and message
        icon_label = QLabel()
        icon_label.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxInformation).pixmap(32, 32))

        message_label = QLabel(message)
        message_label.setWordWrap(True)

        header_layout = QHBoxLayout()
        header_layout.addWidget(icon_label)
        header_layout.addWidget(message_label, 1)

        layout.addLayout(header_layout)

        # Add buttons
        button_layout = QHBoxLayout()

        # Add Open button if path is provided
        if file_path:
            open_button = QPushButton("Open Now")
            if is_directory:
                open_button.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
                open_button.clicked.connect(lambda: self.open_directory(file_path))
            else:
                open_button.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
                open_button.clicked.connect(lambda: self.open_file(file_path))

            open_button.clicked.connect(dialog.accept)
            button_layout.addWidget(open_button)

        # Add OK button
        ok_button = QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_button)

        layout.addLayout(button_layout)

        # Show dialog
        dialog.exec_()

    def show_results(self, output_path, num_files):
        """Updates the results section in the summary page"""
        # Debug print
        print(f"DEBUG: show_results called with output_path={output_path}, num_files={num_files}")

        self.results_group.setVisible(True)

        # Clear any existing layout in the results group
        if hasattr(self, 'results_layout'):
            # Remove old widgets
            while self.results_layout.count():
                item = self.results_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        else:
            # Create a new layout for the results group
            self.results_layout = QVBoxLayout(self.results_group)

        # Update the results text
        if num_files == 1:
            results_html = f"""
            <h3>Processing Complete</h3>
            <p>Your code has been successfully condensed into a single file.</p>
            <p><b>Output File:</b> {output_path}</p>
            <p>You can now use this file with your preferred LLM for code analysis.</p>
            """
        else:
            results_html = f"""
            <h3>Processing Complete</h3>
            <p>Your code has been successfully condensed into {num_files} chunk files.</p>
            <p><b>Output Directory:</b> {os.path.dirname(output_path)}</p>
            <p>You can now use these files with your preferred LLM for code analysis.</p>
            <p>Tip: Start with the first chunk which contains the directory structure.</p>
            """

        # Update the text widget
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setHtml(results_html)
        self.results_layout.addWidget(self.results_text)

        # Create a frame for the buttons with a different background
        button_frame = QFrame()
        button_frame.setFrameShape(QFrame.StyledPanel)
        button_frame.setStyleSheet("background-color: #f0f0f0; border-radius: 5px; padding: 10px;")

        button_layout = QVBoxLayout(button_frame)
        button_layout.setSpacing(10)

        # Add a label
        action_label = QLabel("<b>Actions:</b>")
        button_layout.addWidget(action_label)

        # Add buttons based on output type
        if num_files == 1:
            # Add a button to open the file
            open_file_button = QPushButton("  Open Generated File")
            open_file_button.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
            open_file_button.setIconSize(QSize(24, 24))
            open_file_button.setMinimumHeight(40)
            open_file_button.setStyleSheet("""
                QPushButton {
                    font-size: 14px;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 15px;
                }
            """)
            open_file_button.clicked.connect(lambda: self.open_file(output_path))
            button_layout.addWidget(open_file_button)

            # Add a download button for the file
            download_button = QPushButton("  Download Generated File")
            download_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
            download_button.setIconSize(QSize(24, 24))
            download_button.setMinimumHeight(40)
            download_button.setStyleSheet("""
                QPushButton {
                    font-size: 14px;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 15px;
                }
            """)
            download_button.clicked.connect(lambda: self.download_file(output_path))
            button_layout.addWidget(download_button)
        else:
            # Add a button to open the directory
            open_dir_button = QPushButton("  Open Output Directory")
            open_dir_button.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
            open_dir_button.setIconSize(QSize(24, 24))
            open_dir_button.setMinimumHeight(40)
            open_dir_button.setStyleSheet("""
                QPushButton {
                    font-size: 14px;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 15px;
                }
            """)
            open_dir_button.clicked.connect(lambda: self.open_directory(os.path.dirname(output_path)))
            button_layout.addWidget(open_dir_button)

            # Add a download button for the directory
            download_button = QPushButton("  Download All Files")
            download_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
            download_button.setIconSize(QSize(24, 24))
            download_button.setMinimumHeight(40)
            download_button.setStyleSheet("""
                QPushButton {
                    font-size: 14px;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 15px;
                }
            """)
            download_button.clicked.connect(lambda: self.download_directory(os.path.dirname(output_path), os.path.basename(output_path)))
            button_layout.addWidget(download_button)

        # Add the button frame to the results layout
        self.results_layout.addWidget(button_frame)

    def split_content_smart(self, content, max_lines):
        """Splits content into chunks, trying to keep files intact."""
        self.update_status(f"Splitting content into chunks (max {max_lines} lines each)...")
        if not content: return [] # Handle empty content to avoid split errors
        lines = content.splitlines(keepends=True) # Keep newlines
        if not lines: return []

        parts = []
        current_part_lines = []
        current_line_count = 0
        file_marker = ">>>File: "

        # Find line indices of file markers
        marker_indices = [-1] # Add dummy index for content before the first marker
        marker_indices.extend([i for i, line in enumerate(lines) if line.startswith(file_marker)])

        for i in range(len(marker_indices)):
            start_index = marker_indices[i] + 1 # Start after the previous marker (or from beginning)
            # If it's the *first* block (before any file marker), start_index will be 0
            if i == 0 and start_index == 0 and marker_indices[0] == -1 : start_index = 0

            # Find the end of the current block (start of the next marker or end of content)
            end_index = marker_indices[i+1] if i + 1 < len(marker_indices) else len(lines)

            block_lines = lines[start_index:end_index]
            block_line_count = len(block_lines)

            # Include the marker line itself in the block if it's not the first dummy marker
            if i > 0:
                marker_line_index = marker_indices[i]
                block_lines.insert(0, lines[marker_line_index])
                block_line_count += 1


            if not block_lines: continue # Skip if block is somehow empty

            # If the current block *itself* is larger than max_lines, it needs special handling
            # For now, we just put it in its own chunk (or append if current chunk is empty)
            if block_line_count > max_lines:
                # If there's content in the current part, finalize it first
                if current_part_lines:
                    parts.append("".join(current_part_lines))
                    current_part_lines = []
                    current_line_count = 0

                # Add the huge block as its own part (potentially oversized)
                parts.append("".join(block_lines))
                # Continue to next block, skipping normal append logic for this one
                continue

            # Check if adding this block exceeds the limit
            if current_line_count > 0 and current_line_count + block_line_count > max_lines:
                # Current block doesn't fit, finalize the previous part
                parts.append("".join(current_part_lines))
                current_part_lines = [] # Start new part
                current_line_count = 0

            # Add the current block to the current part
            current_part_lines.extend(block_lines)
            current_line_count += block_line_count

        # Add the last remaining part
        if current_part_lines:
            parts.append("".join(current_part_lines))

        self.update_status(f"Splitting complete. Generated {len(parts)} chunks.")
        return parts

    # Override closeEvent to stop the worker thread if running
    def closeEvent(self, event):
        # Save settings
        self.settings.save_settings()

        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, 'Confirm Exit',
                                        "Processing is in progress. Are you sure you want to exit?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.status_bar.showMessage("Attempting to stop worker thread...")
                self.worker.terminate() # Request termination
                if not self.worker.wait(2000): # Wait up to 2 seconds
                    self.status_bar.showMessage("Worker did not stop gracefully. Forcing exit.")
                else:
                    self.status_bar.showMessage("Worker stopped.")
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

# --- Main Layout ---
        main_layout = QVBoxLayout()

        # --- Input/Output Paths ---
        path_group = QGroupBox("Input & Output")
        path_layout = QVBoxLayout()

        # Directory selection
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel('Project Directory:'))
        self.directory_entry = QLineEdit()
        self.directory_entry.setPlaceholderText("Select the root directory of your project")
        self.directory_entry.setToolTip("The main folder containing the code you want to analyze.")
        dir_layout.addWidget(self.directory_entry)
        dir_button = QPushButton('Browse...')
        dir_button.clicked.connect(self.choose_directory)
        dir_layout.addWidget(dir_button)
        path_layout.addLayout(dir_layout)

        # Output file/base selection
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel('Output File/Base Name:'))
        self.output_entry = QLineEdit()
        self.output_entry.setPlaceholderText("Specify output .txt file (e.g., project_code.txt)")
        self.output_entry.setToolTip("The name for the output file. If chunking, this will be used as a base name (e.g., base-part-1.txt).")
        output_layout.addWidget(self.output_entry)
        output_button = QPushButton('Save As...')
        output_button.clicked.connect(self.choose_output_file)
        output_layout.addWidget(output_button)
        path_layout.addLayout(output_layout)

        path_group.setLayout(path_layout)
        main_layout.addWidget(path_group)

        # --- Exclusion Settings ---
        exclude_group = QGroupBox("Exclusion Rules")
        exclude_layout = QVBoxLayout()

        # Exclude directories
        exclude_dirs_layout = QHBoxLayout()
        exclude_dirs_layout.addWidget(QLabel('Exclude Directories (comma-separated):'))
        self.exclude_dirs_entry = QLineEdit()
        self.exclude_dirs_entry.setText(','.join(DEFAULT_EXCLUDE_DIRS))
        self.exclude_dirs_entry.setToolTip("List of directory names to completely ignore (case-sensitive).")
        exclude_dirs_layout.addWidget(self.exclude_dirs_entry)
        exclude_layout.addLayout(exclude_dirs_layout)

        # Exclude files/patterns
        exclude_files_layout = QHBoxLayout()
        exclude_files_layout.addWidget(QLabel('Exclude Files/Patterns (comma-separated):'))
        self.exclude_files_entry = QLineEdit()
        self.exclude_files_entry.setText(','.join(DEFAULT_EXCLUDE_FILES))
        self.exclude_files_entry.setToolTip("List of specific file names or wildcard patterns (e.g., *.log, setup.?) to ignore (case-sensitive).")
        exclude_files_layout.addWidget(self.exclude_files_entry)
        exclude_layout.addLayout(exclude_files_layout)

        # Use .gitignore
        self.use_gitignore_checkbox = QCheckBox("Use .gitignore rules found in the project directory")
        self.use_gitignore_checkbox.setChecked(True) # <<< Default Checked
        self.use_gitignore_checkbox.setToolTip("If checked, rules from a .gitignore file in the root directory will also be applied (basic pattern support).")
        exclude_layout.addWidget(self.use_gitignore_checkbox)

        # Exclude file extensions group box wrapping the scroll area content
        extensions_outer_group = QGroupBox("Exclude Common Non-Code File Extensions")
        extensions_outer_group.setFlat(True)
        extensions_outer_layout = QVBoxLayout(extensions_outer_group) # Use this layout for content inside group

        # Container widget for the grid inside the scroll area
        extensions_scroll_content_widget = QWidget()
        extensions_grid_layout = QHBoxLayout(extensions_scroll_content_widget) # Use horizontal layout for columns

        col_layouts = [QVBoxLayout(), QVBoxLayout(), QVBoxLayout()] # 3 columns

        self.extension_checkboxes = {}
        col_count = len(col_layouts)
        # Sort extensions alphabetically for display
        sorted_extensions = sorted(DEFAULT_EXCLUDE_EXTENSIONS, key=str.lower)
        items_per_col = (len(sorted_extensions) + col_count - 1) // col_count # Ceiling division

        for i, ext in enumerate(sorted_extensions):
            checkbox = QCheckBox(ext)
            checkbox.setChecked(True) # <<< Default Checked
            self.extension_checkboxes[ext] = checkbox
            col_index = i // items_per_col
            col_layouts[col_index].addWidget(checkbox)

        for col_layout in col_layouts:
            col_layout.addStretch() # Push checkboxes up
            extensions_grid_layout.addLayout(col_layout)

        # Add custom extensions input below the grid
        custom_ext_layout = QHBoxLayout()
        custom_ext_layout.addWidget(QLabel("Other extensions to exclude (e.g., .dat,.bin):"))
        self.custom_exclude_extensions_entry = QLineEdit()
        self.custom_exclude_extensions_entry.setToolTip("Add any other file extensions (comma-separated, include the dot).")
        custom_ext_layout.addWidget(self.custom_exclude_extensions_entry)

        # Add grid and custom input to the outer group's layout
        extensions_outer_layout.addWidget(extensions_scroll_content_widget)
        extensions_outer_layout.addLayout(custom_ext_layout)


        # Add scroll area for the extensions group box
        scroll = QScrollArea()
        scroll.setWidget(extensions_outer_group) # Put the group inside scroll
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(200) # Adjust height as needed
        # scroll.setStyleSheet("background-color: transparent;") # Inherit background from parent
        exclude_layout.addWidget(scroll)


        exclude_group.setLayout(exclude_layout)
        main_layout.addWidget(exclude_group)


        # --- Output Format Options ---
        output_options_group = QGroupBox("Output Options")
        output_options_layout = QVBoxLayout()

        self.include_structure_checkbox = QCheckBox("Include directory structure summary at the beginning")
        self.include_structure_checkbox.setChecked(True) # <<< Default Checked
        self.include_structure_checkbox.setToolTip("Adds a formatted list of included files and directories at the start of the output.")
        output_options_layout.addWidget(self.include_structure_checkbox)

        self.structure_only_checkbox = QCheckBox("Create file/directory structure only")
        self.structure_only_checkbox.setToolTip("If checked, only the directory and file structure will be created, without file contents.")
        self.structure_only_checkbox.toggled.connect(self.toggle_structure_options) # Connect toggle event
        output_options_layout.addWidget(self.structure_only_checkbox)

        # Output type radio buttons
        self.single_file_radio = QRadioButton("Output as a single file")
        self.single_file_radio.setChecked(True) # <<< Default Selected
        self.single_file_radio.toggled.connect(self.toggle_chunk_options)
        output_options_layout.addWidget(self.single_file_radio)

        self.chunked_file_radio = QRadioButton("Chunk output into multiple files")
        self.chunked_file_radio.toggled.connect(self.toggle_chunk_options)
        output_options_layout.addWidget(self.chunked_file_radio)

        # Chunk size options (initially disabled)
        self.chunk_options_widget = QWidget() # Container for chunk options
        chunk_size_layout = QHBoxLayout(self.chunk_options_widget)
        chunk_size_layout.setContentsMargins(20, 0, 0, 0) # Indent chunk options
        self.max_lines_label = QLabel("Max lines per chunk:")
        self.max_lines_spinbox = QSpinBox()
        self.max_lines_spinbox.setRange(100, 1000000) # Set reasonable limits
        self.max_lines_spinbox.setValue(DEFAULT_MAX_LINES_PER_CHUNK)
        self.max_lines_spinbox.setToolTip(f"Approximate maximum number of lines per chunk file (Default: {DEFAULT_MAX_LINES_PER_CHUNK}). Splits occur between files.")
        chunk_size_layout.addWidget(self.max_lines_label)
        chunk_size_layout.addWidget(self.max_lines_spinbox)
        chunk_size_layout.addStretch()
        output_options_layout.addWidget(self.chunk_options_widget)

        output_options_group.setLayout(output_options_layout)
        main_layout.addWidget(output_options_group)

        # --- Run Button ---
        self.run_button = QPushButton('Generate Condensed Code')
        # self.run_button.setIcon(QIcon.fromTheme("system-run")) # Icons can be iffy cross-platform
        self.run_button.clicked.connect(self.run_analysis)
        main_layout.addWidget(self.run_button, alignment=Qt.AlignCenter)

        # --- Status Bar ---
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready.")
        main_layout.addWidget(self.status_bar)

        self.setLayout(main_layout)

        # Initial state update
        self.toggle_chunk_options()
        self.toggle_structure_options() # Initialize structure options state

    def choose_directory(self):
        # Try to start in the currently entered directory or user's home
        start_dir = self.directory_entry.text() or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(self, "Select Project Directory", start_dir)
        if directory:
            self.directory_entry.setText(directory)
            # Auto-suggest output file name based on directory if output is empty
            if not self.output_entry.text().strip():
                 base_name = os.path.basename(directory)
                 # Suggest output in the *parent* directory of the selected project, or home if no parent
                 parent_dir = os.path.dirname(directory) or os.path.expanduser("~")
                 suggested_path = os.path.join(parent_dir, f"{base_name}_codebase.txt")
                 self.output_entry.setText(suggested_path)


    def choose_output_file(self):
        # Suggest a directory based on the input directory or output entry
        current_output = self.output_entry.text()
        default_dir = os.path.dirname(current_output) or os.path.dirname(self.directory_entry.text()) or os.path.expanduser("~")
        suggested_filename = current_output or os.path.join(default_dir, "project_codebase.txt")

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Output File", suggested_filename, "Text Files (*.txt);;All Files (*)")
        if file_path:
            # Ensure it has a .txt extension if none provided and filter was txt
            if not os.path.splitext(file_path)[1] and 'Text Files' in _:
                file_path += '.txt'
            self.output_entry.setText(file_path)

    def toggle_chunk_options(self):
        is_chunked = self.chunked_file_radio.isChecked()
        self.chunk_options_widget.setEnabled(is_chunked)
        # Visually indicate disabled state better
        self.max_lines_label.setEnabled(is_chunked)
        self.max_lines_spinbox.setEnabled(is_chunked)

    def toggle_structure_options(self):
        """Handle mutual exclusivity between structure checkboxes."""
        if self.structure_only_checkbox.isChecked():
            # If structure_only is checked, uncheck and disable include_structure
            self.include_structure_checkbox.setChecked(False)
            self.include_structure_checkbox.setEnabled(False)
        else:
            # If structure_only is unchecked, re-enable include_structure
            self.include_structure_checkbox.setEnabled(True)

    def _parse_exclusions(self):
        """Parses exclusion lists from the GUI, handling whitespace."""
        # Use case-sensitive matching for dirs/files by default, as gitignore often is
        dirs = {d.strip() for d in self.exclude_dirs_entry.text().split(',') if d.strip()}
        files = {f.strip() for f in self.exclude_files_entry.text().split(',') if f.strip()}

        # Extensions are typically case-insensitive
        checked_exts = {ext.lower() for ext, checkbox in self.extension_checkboxes.items() if checkbox.isChecked()}
        custom_exts_raw = self.custom_exclude_extensions_entry.text().split(',')
        custom_exts = {ext.strip().lower() for ext in custom_exts_raw if ext.strip()}
        # Ensure extensions start with a dot
        custom_exts_dotted = {ext if ext.startswith('.') else '.' + ext for ext in custom_exts}

        all_extensions = checked_exts.union(custom_exts_dotted)
        return dirs, files, all_extensions

    def run_analysis(self):
        root_dir = self.directory_entry.text()
        output_path = self.output_entry.text()

        if not root_dir or not os.path.isdir(root_dir):
            QMessageBox.warning(self, "Input Error", "Please select a valid project directory.")
            return
        if not output_path:
            QMessageBox.warning(self, "Input Error", "Please specify an output file name/path.")
            return
        # Check if output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.isdir(output_dir):
             QMessageBox.warning(self, "Input Error", f"The output directory does not exist:\n{output_dir}")
             return


        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Busy", "Processing is already in progress.")
            return

        self.run_button.setEnabled(False)
        self.status_bar.showMessage("Starting analysis...")

        exclude_dirs, exclude_files, exclude_extensions = self._parse_exclusions()
        use_gitignore = self.use_gitignore_checkbox.isChecked()
        include_structure = self.include_structure_checkbox.isChecked()
        structure_only = self.structure_only_checkbox.isChecked() # Get structure_only state

        # --- Start Worker Thread ---
        self.worker = ProcessWorker(
            root_dir,
            exclude_dirs,
            exclude_files,
            exclude_extensions,
            use_gitignore,
            include_structure,
            structure_only
        )
        self.worker.progress_update.connect(self.update_status)
        self.worker.finished.connect(self.handle_results)
        self.worker.error.connect(self.handle_error)
        # Connect finished signal to re-enable button *after* results handled
        self.worker.finished.connect(lambda: self.run_button.setEnabled(True))
        self.worker.error.connect(lambda: self.run_button.setEnabled(True)) # Also re-enable on error
        self.worker.start()

    def update_status(self, message):
        self.status_bar.showMessage(message)

    def handle_error(self, error_message):
        print(f"Error signal received:\n{error_message}") # Log detailed error to console
        # Show a simpler message in the dialog
        short_error = "\n".join(error_message.splitlines()[:5]) # Show first few lines
        if len(error_message.splitlines()) > 5:
            short_error += "\n..."
        QMessageBox.critical(self, "Error During Processing", f"An error occurred:\n{short_error}\n\nCheck console for details.")
        self.status_bar.showMessage("Processing failed. See console for details.")
        # Button re-enabled via connection in run_analysis

    def handle_results(self, structure_summary, combined_content, errors):
        structure_only = self.worker.structure_only # Get structure_only from worker
        self.status_bar.showMessage("Processing finished. Saving results...")
        output_path = self.output_entry.text()
        is_chunked = self.chunked_file_radio.isChecked()
        max_lines = self.max_lines_spinbox.value() if is_chunked else -1

        try:
            full_content_to_write = structure_summary + combined_content
            if not full_content_to_write.strip() and not structure_only: # Check content only if not structure_only
                QMessageBox.warning(self, "No Content", "No text content was found or generated after applying exclusions.")
                self.status_bar.showMessage("Ready. No content generated.")
                # self.run_button.setEnabled(True) # Handled by signal connection
                return # Stop here if no content

            base_name, extension = os.path.splitext(output_path)
            if not extension: # Ensure extension exists if none provided
                extension = ".txt"
                output_path += extension
            # Recalculate base_name in case extension was added
            base_name = output_path[:-len(extension)]

            output_dir = os.path.dirname(output_path)
            # Create output directory if it doesn't exist (should be checked before, but double check)
            if output_dir and not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir)
                except OSError as e:
                    raise OSError(f"Failed to create output directory '{output_dir}': {e}")


            if is_chunked:
                parts = self.split_content_smart(full_content_to_write, max_lines)
                num_files = len(parts)
                if num_files == 0:
                    # This case is already handled by the empty content check above
                    pass
                elif num_files == 1:
                    # Only one chunk, save as single file
                    self.status_bar.showMessage(f"Saving single file: {os.path.basename(output_path)}")
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(parts[0])
                    QMessageBox.information(self, "Success", f"Analysis complete. Output saved to:\n{output_path}")
                else:
                    # Save multiple chunk files
                    output_dir_display = output_dir if output_dir else os.getcwd() # Show current dir if no path given
                    base_filename = os.path.basename(base_name)
                    self.status_bar.showMessage(f"Saving {num_files} chunk files...")
                    for i, part in enumerate(parts, 1):
                        if structure_only:
                            chunk_filename = f"{base_filename}-structure-PART-{i}{extension}" # Distinct name for structure only
                        else:
                            # Format chunk name consistently
                            chunk_filename = f"{base_filename}-PART-{i}{extension}"
                        part_file_path = os.path.join(output_dir, chunk_filename)
                        self.update_status(f"Saving chunk {i}/{num_files}: {chunk_filename}")
                        with open(part_file_path, 'w', encoding='utf-8') as f:
                            f.write(part)
                    QMessageBox.information(self, "Success", f"Analysis complete. Output split into {num_files} files (e.g., {base_filename}-PART-1{extension}) in directory:\n{output_dir_display}")

            else: # Single file output
                if structure_only:
                    output_path_structure = base_name + "-structure" + extension # Distinct name for structure only
                    output_path = output_path_structure

                self.status_bar.showMessage(f"Saving single file: {os.path.basename(output_path)}")
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(full_content_to_write)


                QMessageBox.information(self, "Success", f"Analysis complete. Output saved to:\n{output_path}")

            # Report any non-critical errors during file reading
            if errors:
                error_details = "\n".join(errors[:10]) # Show first 10 errors
                if len(errors) > 10:
                    error_details += f"\n... and {len(errors) - 10} more."
                QMessageBox.warning(self, "File Reading Issues", f"Some files could not be read properly or were skipped due to encoding issues:\n{error_details}")


        except Exception as e:
            import traceback
            self.handle_error(f"An error occurred while saving the file(s):\n{traceback.format_exc()}")
        finally:
            # Set status back to Ready only if no error occurred during saving
            if not self.status_bar.currentMessage().startswith("Processing failed"):
                 self.status_bar.showMessage("Ready.")
            # self.run_button.setEnabled(True) # Handled by signal connection

    def split_content_smart(self, content, max_lines):
        """Splits content into chunks, trying to keep files intact."""
        self.update_status(f"Splitting content into chunks (max {max_lines} lines each)...")
        if not content: return [] # Handle empty content to avoid split errors
        lines = content.splitlines(keepends=True) # Keep newlines
        if not lines: return []

        parts = []
        current_part_lines = []
        current_line_count = 0
        file_marker = ">>>File: "

        # Find line indices of file markers
        marker_indices = [-1] # Add dummy index for content before the first marker
        marker_indices.extend([i for i, line in enumerate(lines) if line.startswith(file_marker)])

        for i in range(len(marker_indices)):
            start_index = marker_indices[i] + 1 # Start after the previous marker (or from beginning)
            # If it's the *first* block (before any file marker), start_index will be 0
            if i == 0 and start_index == 0 and marker_indices[0] == -1 : start_index = 0

            # Find the end of the current block (start of the next marker or end of content)
            end_index = marker_indices[i+1] if i + 1 < len(marker_indices) else len(lines)

            block_lines = lines[start_index:end_index]
            block_line_count = len(block_lines)

            # Include the marker line itself in the block if it's not the first dummy marker
            if i > 0:
                marker_line_index = marker_indices[i]
                block_lines.insert(0, lines[marker_line_index])
                block_line_count += 1


            if not block_lines: continue # Skip if block is somehow empty

            # If the current block *itself* is larger than max_lines, it needs special handling
            # For now, we just put it in its own chunk (or append if current chunk is empty)
            if block_line_count > max_lines:
                # If there's content in the current part, finalize it first
                if current_part_lines:
                    parts.append("".join(current_part_lines))
                    current_part_lines = []
                    current_line_count = 0

                # Add the huge block as its own part (potentially oversized)
                parts.append("".join(block_lines))
                # Continue to next block, skipping normal append logic for this one
                continue

            # Check if adding this block exceeds the limit
            if current_line_count > 0 and current_line_count + block_line_count > max_lines:
                # Current block doesn't fit, finalize the previous part
                parts.append("".join(current_part_lines))
                current_part_lines = [] # Start new part
                current_line_count = 0

            # Add the current block to the current part
            current_part_lines.extend(block_lines)
            current_line_count += block_line_count

        # Add the last remaining part
        if current_part_lines:
            parts.append("".join(current_part_lines))

        self.update_status(f"Splitting complete. Generated {len(parts)} chunks.")
        return parts

    # Override closeEvent to stop the worker thread if running
    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, 'Confirm Exit',
                                         "Processing is in progress. Are you sure you want to exit?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.status_bar.showMessage("Attempting to stop worker thread...")
                self.worker.terminate() # Request termination
                if not self.worker.wait(2000): # Wait up to 2 seconds
                     self.status_bar.showMessage("Worker did not stop gracefully. Forcing exit.")
                else:
                     self.status_bar.showMessage("Worker stopped.")
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    # Enable High DPI scaling for better look on modern displays
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # Set application info
    app.setApplicationName("Code Base Condenser")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("CodeCondenser")

    # Set application icon
    try:
        # Create a simple icon if no custom icon is available
        icon = QIcon()
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor("#0078d7"))  # Blue color
        icon.addPixmap(pixmap)
        app.setWindowIcon(icon)
    except Exception as e:
        print(f"Could not set application icon: {e}")

    # Create and show the main window
    main_window = CodeBaseAnalyzer()
    main_window.show()

    # Start the application event loop
    sys.exit(app.exec_())
