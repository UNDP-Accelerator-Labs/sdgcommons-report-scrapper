"""
SDG Commons Report Scraper - Flask Application

A modular Flask web service for scraping UNDP country reports,
extracting content from PDFs/web pages, and storing in PostgreSQL.
"""

import os
import logging
from flask import Flask, send_from_directory, redirect
from flask_swagger_ui import get_swaggerui_blueprint
from flask_cors import CORS

# Import modular components
from src.api import health_bp, scraper_bp, upload_bp
from src.scheduler import init_scheduler

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Register blueprints
app.register_blueprint(health_bp)
app.register_blueprint(scraper_bp)
app.register_blueprint(upload_bp)

# Swagger UI configuration
SWAGGER_URL = "/docs"
API_YAML_URL = "/openapi.yaml"

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_YAML_URL,
    config={"app_name": "SDG Commons Reports Scraper API"}
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)


@app.route('/openapi.yaml', methods=['GET'])
def serve_openapi_yaml():
    """Serve the OpenAPI specification"""
    root_dir = os.path.dirname(__file__)
    return send_from_directory(root_dir, 'openapi.yaml', mimetype='text/yaml')


@app.route('/', methods=['GET'])
def root():
    """Root endpoint redirects to API documentation"""
    return redirect('/docs')


# Initialize scheduler for production
init_scheduler()

if __name__ == '__main__':
    # This only runs in development mode
    logger.warning("Running in DEVELOPMENT mode - do not use in production!")
    
    # Start Flask development server
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
