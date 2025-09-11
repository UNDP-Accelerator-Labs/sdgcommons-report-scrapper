# SDG Commons Reports Scraper

An automated web scraper that extracts UNDP country reports from AILA (Artificial Intelligence Landscape Assessment) and DRA (Digital Readiness Assessment) programs. The application runs as a Flask web service with scheduled scraping, health monitoring, and comprehensive data extraction capabilities.

## 🚀 Features

### Core Functionality

- **Automated Scraping**: Scheduled to run every Monday at 00:00 UTC
- **Multi-Source Content**: Extracts from both web pages and PDF documents
- **Country Detection**: Automatically identifies and geocodes country information
- **Language Detection**: Determines content language using AI
- **Health Monitoring**: Built-in health checks for Azure deployment
- **Manual Triggers**: On-demand scraping via REST API

### Technical Capabilities

- **Headless Browser**: Selenium with Chrome for JavaScript-heavy pages
- **PDF Processing**: Direct PDF extraction with fallback methods
- **Database Integration**: Full PostgreSQL schema with relationships
- **Geocoding**: Automatic country coordinates via OpenStreetMap
- **Production Ready**: Gunicorn WSGI server with proper logging

## 📋 Prerequisites

### Required Software

- Python 3.11+
- Docker & Docker Compose
- Azure CLI (for deployment)
- PostgreSQL 11+ (local development)

### Azure Resources

- Azure Web App Service
- Azure Database for PostgreSQL
- Azure Container Registry (optional)

## 🛠️ Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/UNDP-Accelerator-Labs/sdgcommons-report-scrapper.git
cd sdgcommons-report-scrapper
```

### 2. Local Development Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your database credentials
```

### 3. Local Testing

```bash
# Start with development server
./run-dev.sh

# OR start with production server locally
./run-prod.sh

# Check health
curl http://localhost:8000/health
```

## 🔧 API Endpoints

### Health Monitoring

```bash
GET /health
# Returns: system status, database health, scraper status

GET /scraper/status
# Returns: detailed scraper information

GET /docs
# OpenAPI documentation
```

### Manual Operations

```bash
POST /scraper/run
# Manually trigger scraping job

```

### Example Health Response

```json
{
  "status": "healthy",
  "timestamp": "2025-08-27T18:16:28Z",
  "database": "healthy",
  "server": "gunicorn",
  "environment": "production",
  "scraper": {
    "last_run": "2025-08-26T08:00:15Z",
    "last_status": "Success - 12 reports processed",
    "currently_running": false
  }
}
```

## 📊 Database Schema

### Tables Structure

```sql
-- Main articles table
articles (
  id, url, language, title, posted_date, article_type,
  country, lat, lng, iso3, relevance, tags, ...
)

-- Full content storage
article_content (
  article_id, content, created_at, updated_at
)

-- Raw HTML for debugging
raw_html (
  article_id, raw_html, created_at, updated_at
)
```

### Data Flow

1. **Discovery**: Find report cards on UNDP pages
2. **Extraction**: Extract country, URL, and content
3. **Processing**: Geocode locations, detect language
4. **Storage**: Save to database with full relationships

### Performance Monitoring

- Health endpoint shows last run status
- Database contains processing timestamps
- Azure Application Insights for detailed metrics

## 🚧 Development

```bash
# Run manual scrape
curl -X POST http://localhost:8000/scraper/run

# Test health endpoint
curl http://localhost:8000/health | jq
```

## 📝 Configuration

### Schedule Configuration

The scraper runs every Monday at 00:00 UTC. To modify:

```python
# In app.py, modify this line:
schedule.every().monday.at("00:00").do(run_scheduled_scraper)
```

## 📚 Dependencies

### Core Libraries

- **Flask**: Web framework and API
- **Selenium**: Web browser automation
- **BeautifulSoup**: HTML parsing
- **psycopg2**: PostgreSQL adapter
- **pdfminer**: PDF text extraction
- **geopy**: Geocoding services
- **langdetect**: Language detection

### Production Stack

- **Gunicorn**: WSGI HTTP server
- **Chrome**: Headless browser
- **PostgreSQL**: Database storage
- **Azure Web Apps**: Cloud hosting

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
