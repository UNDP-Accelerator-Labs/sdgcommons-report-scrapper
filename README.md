# SDG Commons Data Parser

A Flask web service for scraping and analyzing UNDP content with two main modules:

1. **Report Scraper** - Extracts UNDP country reports (AILA/DRA) and stores them in PostgreSQL
2. **AcceleratorLab Scanner** - Discovers and classifies AcceleratorLab content across UNDP country offices

## Features

### Report Scraper

- Automated weekly scraping (Mondays at 00:00 UTC)
- PDF and web content extraction with fallback strategies
- Country detection and geocoding
- Language detection
- PostgreSQL storage with NLP embedding support

### AcceleratorLab Scanner

- Scans all UNDP country offices for AcceleratorLab content
- AI-powered classification (high/medium/low confidence)
- Real-time progress dashboard
- Resume capability after interruptions
- Azure Blob Storage support for multi-instance deployments

## Quick Start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 11+ (for Report Scraper)
- Chrome/Chromium (for web scraping)

### 2. Installation

```bash
# Clone repository
git clone https://github.com/UNDP-Accelerator-Labs/sdgcommons-report-scrapper.git
cd sdgcommons-report-scrapper

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your configuration
```

### 3. Configuration

Edit `.env` file:

```bash
# Database (required for Report Scraper)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=sdg_commons
DB_USER=postgres
DB_PASSWORD=your_password

# API Protection
SAVE_API_KEY=your_secret_key

# Azure Blob Storage (optional, for AcceleratorLab multi-instance)
AZURE_STORAGE_CONNECTION_STRING=your_connection_string
```

### 4. Run

```bash
# Development mode (port 8080)
./run-dev.sh

# Production mode (port 8000)
./run-prod.sh
```

## API Endpoints

### Report Scraper

```bash
# Health check
GET /health

# Get scraper status
GET /scraper/status

# Trigger manual scrape (requires API key)
POST /scraper/run
Header: X-API-KEY: your_secret_key

# Upload and parse file
POST /scraper/upload

# Scrape URL
POST /scraper/scrape
```

### AcceleratorLab Scanner

```bash
# Start country scan
POST /acceleratorlab/scan/start

# Get scan progress
GET /acceleratorlab/scan/status

# View results dashboard
Open: http://localhost:8000/static/acceleratorlab_dashboard.html

# Get country results
GET /acceleratorlab/country/{country_code}

# List all countries
GET /acceleratorlab/countries

# Get global summary
GET /acceleratorlab/summary

# Reset scan data (requires API key)
POST /acceleratorlab/scan/reset

# Delete country for re-processing (requires API key)
DELETE /acceleratorlab/country/{country_code}
```

### API Documentation

Interactive OpenAPI documentation available at:

```bash
GET /docs
```

## Storage

### Local Development

Data is stored in `data/acceleratorlab/` directory by default.

### Azure Production

When deployed to Azure Web Apps, the system automatically detects the environment (via `WEBSITE_INSTANCE_ID`) and uses Azure Blob Storage if configured. This ensures data consistency across multiple instances.

## Docker Deployment

```bash
# Build image
docker build -t sdg-parser .

# Run container
docker run -p 8000:8000 --env-file .env sdg-parser
```

## Architecture

```
src/
├── config/          # Configuration management
├── database/        # PostgreSQL operations
├── scraper/         # Report scraping logic
├── acceleratorlab/  # AcceleratorLab scanner module
├── api/            # Flask REST API routes
└── utils/          # Shared utilities

app.py              # Main Flask application
main.py             # Legacy compatibility wrapper
```

## Key Technologies

- **Flask** - Web framework
- **Selenium** - Browser automation
- **BeautifulSoup** - HTML parsing
- **pdfminer.six** - PDF extraction
- **psycopg2** - PostgreSQL adapter
- **azure-storage-blob** - Azure Blob Storage
- **transformers** - AI classification
- **Gunicorn** - Production WSGI server

## License

MIT License - see LICENSE file for details.
