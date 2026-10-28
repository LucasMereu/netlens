import os
from app import create_app
from app.services.config_service import ConfigService

app = create_app()

if __name__ == '__main__':
    config = ConfigService.load_config()
    port = config.get("settings", {}).get("port", 5000)
    
    # Environment-based debug configuration
    flask_env = os.environ.get("FLASK_ENV", "production").lower()
    debug_mode = (flask_env == "development")
    
    print(f"\n[HTTP] Inicializando Dashboard do Analisador de Redes em http://localhost:{port} (debug={debug_mode})\n")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
