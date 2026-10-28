import os
from flask import Flask, session, redirect, url_for, request, jsonify, render_template_string, send_from_directory
from app.services.config_service import ConfigService
from app.clients import is_mock_mode

def create_app(test_config=None):
    root_dir = os.path.dirname(os.path.dirname(__file__))
    static_dir = os.path.join(root_dir, 'static')
    app = Flask(__name__, instance_relative_config=True, static_folder=static_dir)
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-only-insecure-change-in-production')

    if test_config:
        app.config.from_mapping(test_config)

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.status import status_bp
    from app.routes.links import links_bp
    from app.routes.vlans import vlans_bp
    from app.routes.topology import topology_bp
    from app.routes.bottlenecks import bottlenecks_bp
    from app.routes.ports import ports_bp
    from app.routes.alerts import alerts_bp
    from app.routes.reports import reports_bp
    from app.routes.jobs import jobs_bp
    from app.routes.config import config_bp
    from app.routes.dell import dell_bp
    from app.routes.intent_routes import intent_bp
    from app.routes.provisioning import provisioning_bp
    from app.routes.admin import admin_bp
    from app.routes.inventory import inventory_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(status_bp)
    app.register_blueprint(links_bp)
    app.register_blueprint(vlans_bp)
    app.register_blueprint(topology_bp)
    app.register_blueprint(bottlenecks_bp)
    app.register_blueprint(ports_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(dell_bp)
    app.register_blueprint(intent_bp)
    app.register_blueprint(provisioning_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(inventory_bp)


    # Initialize high-frequency latency monitor thread safely (idempotent no-op if already running)
    from app.routes.alerts import ping_monitor
    ping_monitor.start()

    # Execute Job Engine crash recovery for orphan QUEUED/RUNNING jobs
    from app.services.job_engine import JobEngine
    JobEngine.recover()

    # Global Authentication middleware
    @app.before_request
    def check_authentication():
        path = request.path
        if (path.startswith('/static/') or 
            path == '/favicon.ico' or 
            path == '/login' or 
            path == '/api/auth/recovery-question' or 
            path == '/api/auth/recover-password'):
            return None
            
        if not session.get('logged_in'):
            if path.startswith('/api/'):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for('auth.login_page'))

    @app.route('/favicon.ico')
    def favicon():
        static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
        return send_from_directory(static_dir, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

    # Dashboard root page
    @app.route('/')
    def dashboard():
        templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
        index_path = os.path.join(templates_dir, 'index.html')
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                return render_template_string(f.read(), is_mock=is_mock_mode())
        return "Template index.html nao localizado. Aguarde a finalizacao da escrita."

    @app.after_request
    def add_header(response):
        if request.path == '/' or request.path.endswith('.html'):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    return app
