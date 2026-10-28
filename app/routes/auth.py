import hashlib
from flask import Blueprint, jsonify, request, session, redirect, url_for, render_template_string
from app.services.config_service import ConfigService

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        if request.is_json:
            data = request.json or {}
            username = data.get('username')
            password = data.get('password')
        else:
            username = request.form.get('username')
            password = request.form.get('password')
            
        users_cfg = ConfigService.load_users()
        pw_hash = hashlib.sha256((password or '').encode('utf-8')).hexdigest()
        
        # Check against multi-user list
        matched_user = None
        for u in users_cfg.get('users', []):
            if u.get('username') == username and u.get('password_hash') == pw_hash:
                matched_user = u
                break
                
        # Legacy fallback
        if not matched_user and username == users_cfg.get('username') and pw_hash == users_cfg.get('password_hash'):
            matched_user = {"username": username, "role": "admin", "name": username}

        if matched_user:
            session['logged_in'] = True
            session['username'] = matched_user.get('username')
            session['user_role'] = matched_user.get('role', 'admin')
            if request.is_json:
                return jsonify({"success": True})
            return redirect(url_for('dashboard'))
        else:
            error_msg = "Usuario ou senha incorretos."
            if request.is_json:
                return jsonify({"success": False, "error": error_msg}), 401
            
            import os
            templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'templates')
            login_path = os.path.join(templates_dir, 'login.html')
            with open(login_path, 'r', encoding='utf-8') as f:
                return render_template_string(f.read(), error=error_msg)
                
    import os
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'templates')
    login_path = os.path.join(templates_dir, 'login.html')
    with open(login_path, 'r', encoding='utf-8') as f:
        return render_template_string(f.read())

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login_page'))

@auth_bp.route('/api/auth/recovery-question', methods=['GET'])
def get_recovery_question():
    users_cfg = ConfigService.load_users()
    return jsonify({
        "success": True,
        "question": users_cfg.get("security_question", "Qual e o nome da empresa?")
    })

@auth_bp.route('/api/auth/recover-password', methods=['POST'])
def recover_password():
    data = request.json or {}
    answer = data.get('answer', '').strip().lower()
    new_password = data.get('new_password', '').strip()
    
    if not answer or not new_password:
        return jsonify({"success": False, "error": "Resposta e nova senha sao obrigatorias."}), 400
        
    users_cfg = ConfigService.load_users()
    answer_hash = hashlib.sha256(answer.encode('utf-8')).hexdigest()
    
    if answer_hash == users_cfg.get('security_answer_hash'):
        new_pw_hash = hashlib.sha256(new_password.encode('utf-8')).hexdigest()
        users_cfg['password_hash'] = new_pw_hash
        ConfigService.save_users(users_cfg)
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Resposta de seguranca incorreta."}), 401
