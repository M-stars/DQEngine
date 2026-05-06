<p align="center">
  <h1 align="center">DQEngine</h1>
  <p align="center">
    <strong>A lightweight, automated, developer-friendly data quality governance framework.</strong>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT">
  <img src="https://img.shields.io/badge/status-mvp-orange.svg" alt="Status: MVP">
</p>

---

## Overview

**DQEngine** (Data Quality Engine) is a CLI-first data quality governance tool designed for data engineers and analysts who need to **profile, validate, auto-repair, and score** datasets — without writing scripts.

It is not a notebook-based cleaning tool. It is an **engineering-grade framework** with a modular, extensible architecture.

### Key Features

- **CLI-first**: Run `dq profile`, `dq auto`, `dq validate` directly from the terminal.
- **Data Profiling**: Column statistics, null rates, uniqueness, distributions.
- **Quality Scoring**: Multi-dimensional quality assessment (completeness, uniqueness, validity) with a 0–100 score.
- **Auto-Repair**: Missing value imputation, duplicate removal, date standardization, outlier detection (IQR).
- **YAML Rule Validation**: Define column-level validation rules with range, regex, not-null, and allowed-value checks.
- **HTML Reports**: Professional Jinja2-generated reports with score gauges and repair summaries.
- **Rich Terminal Output**: Colorized tables, progress indicators, and quality score visualizations.

---

## Architecture

```
                     ┌──────────────────────────┐
                     │       CLI (Typer)         │
                     │  dq profile | auto | validate │
                     └────────────┬─────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
   ┌──────▼──────┐        ┌──────▼──────┐        ┌──────▼──────┐
   │   Core      │        │   Repair    │        │   Rules     │
   │ ─────────── │        │ ─────────── │        │ ─────────── │
   │ Profiler    │        │ MV Cleaner  │        │ Validator   │
   │ Scorer      │        │ Dup Cleaner │        │ YAML Parser │
   │ Loader      │        │ Date Std    │        │             │
   └──────┬──────┘        │ Outlier Det │        └──────┬──────┘
          │               └──────┬──────┘               │
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                        ┌────────▼────────┐
                        │    Report       │
                        │ ─────────────── │
                        │ Jinja2 HTML     │
                        └────────┬────────┘
                                 │
                        ┌────────▼────────┐
                        │    Models       │
                        │ ─────────────── │
                        │ Pydantic        │
                        └─────────────────┘
```

### Design Philosophy

- **Modular**: Each concern (profiling, repair, validation, reporting) is an isolated module with minimal coupling.
- **Typed**: Full type annotations with Pydantic models for all data structures.
- **Extensible**: New repair strategies, validators, or quality dimensions can be added by implementing the corresponding interface.
- **Composable**: Every module works standalone — you can use the Profiler without the repair pipeline.

---

## Installation

### Prerequisites

- Python 3.11 or higher
- pip 23.0+

### Install from source

```bash
git clone https://github.com/dqengine/dqengine.git
cd dqengine
pip install -e .
```

### Install with dev dependencies

```bash
pip install -e ".[dev]"
```

Verify installation:

```bash
dq version
```

---

## Quick Start

### 1. Profile a Dataset

```bash
dq profile examples/sample.csv
```

Output includes:
- Row/column counts, memory usage, duplicate rate
- Per-column statistics (type, null rate, uniqueness, min/max/mean)
- Overall data quality score with dimension breakdown

### 2. Auto-Clean a Dataset

```bash
dq auto examples/sample.csv --output cleaned_data.csv --report report.html
```

Performs automatically:
1. Duplicate row removal
2. Missing value imputation (mean for numeric, mode for categorical)
3. Date column standardization (→ `YYYY-MM-DD`)
4. Outlier detection (IQR method)
5. Generates `cleaned_data.csv` and `report.html`

Skip outlier removal:

```bash
dq auto examples/sample.csv --no-outlier-removal
```

### 3. Validate Against Rules

```bash
dq validate examples/sample.csv --rules configs/rules.yaml
```

Example rules file (`configs/rules.yaml`):

```yaml
columns:
  age:
    min: 0
    max: 120

  email:
    regex: email      # named patterns: email, phone, url, date

  name:
    not_null: true

  gender:
    allowed_values:
      - Male
      - Female
      - Other

  salary:
    min: 0
    max: 500000
```

### 4. Save Profile as JSON

```bash
dq profile examples/sample.csv --output profile.json
```

---

## Project Structure

```
dqengine/
├── dqengine/                    # Main package
│   ├── __init__.py
│   ├── cli/                     # Typer CLI commands
│   │   ├── __init__.py
│   │   └── commands.py
│   ├── core/                    # Core engine
│   │   ├── __init__.py
│   │   ├── loader.py            # Data loading (CSV, Excel, auto-encoding)
│   │   ├── profiler.py          # Column statistics & profiling
│   │   └── scorer.py            # Multi-dimensional quality scoring
│   ├── repair/                  # Data repair modules
│   │   ├── __init__.py
│   │   ├── missing_value.py     # Null imputation (mean/mode)
│   │   ├── duplicate.py         # Duplicate row removal
│   │   ├── date_standardizer.py # Date format normalization
│   │   └── outlier.py           # IQR-based outlier detection
│   ├── rules/                   # Rule-based validation
│   │   ├── __init__.py
│   │   └── validator.py         # YAML rule parser & executor
│   ├── report/                  # HTML report generation
│   │   ├── __init__.py
│   │   ├── generator.py         # Jinja2 report renderer
│   │   └── templates/
│   │       └── report.html      # Report template
│   ├── utils/                   # Utilities
│   │   ├── __init__.py
│   │   └── console.py           # Rich console helpers
│   └── models/                  # Pydantic data models
│       ├── __init__.py
│       └── schemas.py           # All data structures
├── configs/                     # Configuration files
│   └── rules.yaml               # Example validation rules
├── examples/                    # Example data
│   └── sample.csv               # Sample dataset (25 rows, 8 columns)
├── tests/                       # Test suite
│   ├── __init__.py
│   ├── test_loader.py
│   ├── test_profiler.py
│   └── test_validator.py
├── docs/                        # Documentation (future)
├── pyproject.toml               # Project configuration & dependencies
├── README.md
└── LICENSE
```

---

## Core Modules

### `core.loader` — Data Loading

- Supports CSV (`.csv`) and Excel (`.xlsx`, `.xls`).
- Automatic encoding detection: UTF-8 → GBK → GB2312 → Latin-1 → ISO-8859-1.

### `core.profiler` — Data Profiling

`Profiler.profile(df)` returns a `ProfileResult` containing per-column statistics:
- Column name, dtype, null count/rate, unique count/rate
- For numeric columns: mean, std, min, Q25, Q50, Q75, max

### `core.scorer` — Quality Scoring

`QualityScorer.score(df, profile)` evaluates data quality across three dimensions:

| Dimension    | Weight | Description                                  |
|------------- |--------|----------------------------------------------|
| Completeness | 40%    | Non-null value ratio across all columns      |
| Uniqueness   | 30%    | Row uniqueness + column value diversity      |
| Validity     | 30%    | Type consistency and value plausibility      |

### `repair` — Auto-Repair Pipeline

| Module             | Strategy                                                |
|--------------------|--------------------------------------------------------|
| MissingValueCleaner | Mean fill (numeric), mode fill (categorical)            |
| DuplicateCleaner    | Row deduplication with configurable keep policy         |
| DateStandardizer    | Heuristic date column detection + `YYYY-MM-DD` normalization |
| OutlierDetector     | IQR method: mild (1.5×IQR), extreme (3×IQR)            |

### `rules.validator` — Rule-Based Validation

Supported rule types:

| Rule Type       | YAML Key        | Description                           |
|-----------------|-----------------|---------------------------------------|
| Range           | `min`, `max`    | Numeric value bounds                  |
| Regex           | `regex`         | Pattern matching (named: email/phone/url/date) |
| Not Null        | `not_null: true` | Required field check                  |
| Allowed Values  | `allowed_values`| Discrete value set membership         |

### `report.generator` — HTML Reports

Jinja2-powered report template with:
- Circular score gauge (CSS conic-gradient)
- Dimension breakdown bars
- Full column statistics table
- Outlier summary by column and severity
- Repair operation log

---

## Running Tests

```bash
# Run all tests
pytest

# With coverage
pytest --cov=dqengine --cov-report=term-missing

# Run specific test file
pytest tests/test_profiler.py -v
```

---

## Technology Stack

| Component      | Library     | Purpose                        |
|----------------|-------------|--------------------------------|
| CLI            | Typer       | Command-line interface         |
| Terminal UI    | Rich        | Colorized tables & formatting  |
| Data           | Pandas      | DataFrame operations           |
| Validation     | Pydantic    | Type-safe data models         |
| Config         | PyYAML      | YAML rule parsing             |
| Templates      | Jinja2      | HTML report rendering         |
| Excel Support  | openpyxl    | `.xlsx` read/write            |
| Testing        | pytest      | Unit test framework           |

---

## Roadmap

### v0.2.0
- [ ] JSON/Parquet/Feather file support
- [ ] Custom repair strategy injection
- [ ] Streaming mode for large files
- [ ] `dq diff` — compare two datasets

### v0.3.0
- [ ] Anomaly detection (isolation forest, Z-score)
- [ ] Data lineage tracking
- [ ] Slack/email alert integration
- [ ] `dq watch` — file watcher mode

### v1.0.0
- [ ] Web dashboard
- [ ] REST API
- [ ] Database connectors (PostgreSQL, MySQL, BigQuery)
- [ ] CI/CD integration plugins (GitHub Actions, GitLab CI)

---

## Contributing

Contributions are welcome. Please open an issue or draft a pull request.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Write tests for your changes
5. Ensure tests pass: `pytest`
6. Submit a PR

---

## License

MIT © DQEngine Team
