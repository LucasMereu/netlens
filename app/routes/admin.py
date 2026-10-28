import uuid
import hashlib
import re
import logging
from flask import Blueprint, jsonify, request, session
from app.services.config_service import ConfigService
from app.models.provision_profile import BUILTIN_PROFILES
from app.utils.sanitizer import SecretSanitizer
import dataclasses

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.before_request
def check_auth():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401

@admin_bp.route('/api/admin/profiles', methods=['GET'])
def get_profiles():
    try:
        config = ConfigService.load_config()
        custom = config.get("custom_profiles", {})
        
        # Merge builtin and custom
        all_profiles = []
        for name, profile in BUILTIN_PROFILES.items():
            p_dict = dataclasses.asdict(profile)
            p_dict["builtin"] = True
            all_profiles.append(p_dict)
            
        for name, profile in custom.items():
            p_dict = profile.copy()
            p_dict["builtin"] = False
            all_profiles.append(p_dict)
            
        resp = jsonify({"success": True, "data": all_profiles})
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500

@admin_bp.route('/api/admin/profile-options', methods=['GET'])
def get_profile_options():
    try:
        config = ConfigService.load_config()
        
        # 1. NetBox Roles & Clusters
        netbox_cfg = config.get('netbox', {})
        nb_url = netbox_cfg.get('url', '').rstrip('/')
        nb_token = netbox_cfg.get('api_token', '')
        
        netbox_roles = []
        netbox_clusters = []
        if nb_url and nb_token:
            try:
                import requests
                requests.packages.urllib3.disable_warnings()
                headers = {"Authorization": f"Token {nb_token}", "Content-Type": "application/json"}
                
                # Roles
                roles_res = requests.get(f"{nb_url}/api/dcim/device-roles/?limit=100", headers=headers, verify=False, timeout=6)
                if roles_res.status_code == 200:
                    for r in roles_res.json().get('results', []):
                        netbox_roles.append({
                            "id": r.get("id"),
                            "name": r.get("name"),
                            "slug": r.get("slug")
                        })
                
                # Clusters
                cluster_res = requests.get(f"{nb_url}/api/virtualization/clusters/?limit=100", headers=headers, verify=False, timeout=6)
                if cluster_res.status_code == 200:
                    for c in cluster_res.json().get('results', []):
                        netbox_clusters.append({
                            "id": c.get("id"),
                            "name": c.get("name")
                        })
            except Exception as nb_err:
                logger.warning(f"Erro ao consultar roles/clusters no NetBox: {nb_err}")
                
        if not netbox_roles:
            netbox_roles = [
                {"id": 2, "name": "Switch", "slug": "switch"},
                {"id": 8, "name": "Link / Roteador", "slug": "link"},
                {"id": 3, "name": "Firewall", "slug": "firewall"},
                {"id": 1, "name": "Servidores", "slug": "servidores"},
                {"id": 5, "name": "Virtualizador", "slug": "virtualizador"},
                {"id": 9, "name": "VM", "slug": "vm"}
            ]

        # 2. Zabbix Templates & Host Groups
        zabbix_cfg = config.get('zabbix', {})
        zb_url = zabbix_cfg.get('url', '').rstrip('/')
        zb_user = zabbix_cfg.get('user', '')
        zb_pass = zabbix_cfg.get('password', '')
        
        zabbix_templates = []
        zabbix_groups = []
        
        if zb_url and zb_user and zb_pass:
            try:
                import requests
                api_url = f"{zb_url}/api_jsonrpc.php" if not zb_url.endswith('.php') else zb_url
                auth_res = requests.post(api_url, json={
                    "jsonrpc": "2.0",
                    "method": "user.login",
                    "params": {"username": zb_user, "password": zb_pass},
                    "id": 1
                }, timeout=6).json()
                token = auth_res.get("result")
                
                if token:
                    # Templates
                    tpl_res = requests.post(api_url, json={
                        "jsonrpc": "2.0",
                        "method": "template.get",
                        "params": {"output": ["templateid", "name"], "limit": 250, "sortfield": "name"},
                        "auth": token,
                        "id": 2
                    }, timeout=6).json()
                    for t in tpl_res.get("result", []):
                        zabbix_templates.append({
                            "id": t.get("templateid"),
                            "name": t.get("name")
                        })
                        
                    # Host Groups
                    grp_res = requests.post(api_url, json={
                        "jsonrpc": "2.0",
                        "method": "hostgroup.get",
                        "params": {"output": ["groupid", "name"], "limit": 250, "sortfield": "name"},
                        "auth": token,
                        "id": 3
                    }, timeout=6).json()
                    for g in grp_res.get("result", []):
                        zabbix_groups.append({
                            "id": g.get("groupid"),
                            "name": g.get("name")
                        })
            except Exception as zb_err:
                logger.warning(f"Erro ao consultar Zabbix templates/groups: {zb_err}")
                
        if not zabbix_templates:
            zabbix_templates = [
                {"id": "10001", "name": "Template Net Network Generic SNMP"},
                {"id": "10002", "name": "Template Net Cisco IOS SNMP"},
                {"id": "10003", "name": "Template Net Sophos XGS SNMP"},
                {"id": "10004", "name": "Linux by Zabbix agent"},
                {"id": "10005", "name": "Windows by Zabbix agent"}
            ]
            
        if not zabbix_groups:
            zabbix_groups = [
                {"id": "1", "name": "Network Devices"},
                {"id": "2", "name": "Firewalls"},
                {"id": "3", "name": "Linux servers"},
                {"id": "4", "name": "Virtual machines"},
                {"id": "5", "name": "Discovered hosts"}
            ]
            
        resp = jsonify({
            "success": True,
            "data": {
                "netbox_roles": netbox_roles,
                "netbox_clusters": netbox_clusters,
                "zabbix_templates": zabbix_templates,
                "zabbix_groups": zabbix_groups
            }
        })
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500

@admin_bp.route('/api/admin/profiles', methods=['POST'])
def create_profile():
    try:
        data = request.json
        name = data.get("name")
        if not name:
            return jsonify({"error": "Name is required"}), 400
        name = name.upper()
            
        config = ConfigService.load_config()
        if name in BUILTIN_PROFILES:
            return jsonify({"error": "Cannot overwrite builtin profile"}), 403
            
        custom = config.setdefault("custom_profiles", {})
        if name in custom:
            return jsonify({"error": "Profile already exists"}), 409
            
        custom[name] = data
        ConfigService.save_config(config)
        ConfigService.reload_config()
        
        return jsonify({"success": True, "message": "Profile created", "profile": data}), 201
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500

@admin_bp.route('/api/admin/profiles/<name>', methods=['PUT'])
def update_profile(name):
    try:
        name = name.upper()
        if name in BUILTIN_PROFILES:
            return jsonify({"error": "Cannot edit builtin profile"}), 403
            
        data = request.json or {}
        config = ConfigService.load_config()
        custom = config.setdefault("custom_profiles", {})
        
        if name not in custom:
            return jsonify({"error": "Profile not found"}), 404

        raw_new_name = data.get("name", name)
        new_name = re.sub(r'[^A-Z0-9_]', '_', raw_new_name.upper().strip()) if raw_new_name else name
        
        if new_name != name:
            if new_name in BUILTIN_PROFILES:
                return jsonify({"error": f"Não é permitido renomear para o nome de um perfil nativo ('{new_name}')"}), 400
            if new_name in custom:
                return jsonify({"error": f"Já existe outro perfil customizado com o nome '{new_name}'"}), 400
            
            # Remove old key and store under new key
            del custom[name]
            data["name"] = new_name
            custom[new_name] = data
            
            # Update any device_models referencing this profile
            for m in config.get("device_models", []):
                if m.get("default_profile") == name:
                    m["default_profile"] = new_name
        else:
            data["name"] = name
            custom[name] = data
            
        ConfigService.save_config(config)
        ConfigService.reload_config()
        
        return jsonify({"success": True, "message": f"Perfil '{new_name}' atualizado com sucesso!", "profile": data})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500

@admin_bp.route('/api/admin/profiles/<name>', methods=['DELETE'])
def delete_profile(name):
    try:
        name = name.upper()
        if name in BUILTIN_PROFILES:
            return jsonify({"error": "Cannot delete builtin profile"}), 403
            
        config = ConfigService.load_config()
        custom = config.get("custom_profiles", {})
        
        if name not in custom:
            return jsonify({"error": "Profile not found"}), 404
            
        del custom[name]
        ConfigService.save_config(config)
        ConfigService.reload_config()
        
        return jsonify({"success": True, "message": "Profile deleted"})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500

@admin_bp.route('/api/admin/sites', methods=['GET'])
def get_sites():
    try:
        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        local_sites = config.get("sites", [])

        if base_url and token:
            try:
                import requests
                requests.packages.urllib3.disable_warnings()
                headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
                res = requests.get(f"{base_url}/api/dcim/sites/", headers=headers, verify=False, timeout=6)
                if res.status_code == 200:
                    netbox_sites = []
                    for s in res.json().get('results', []):
                        status_val = s.get("status")
                        if isinstance(status_val, dict):
                            status_str = status_val.get("label") or status_val.get("value", "Active")
                        else:
                            status_str = str(status_val or "Active")

                        netbox_sites.append({
                            "id": s.get("id"),
                            "name": s.get("name"),
                            "slug": s.get("slug"),
                            "status": status_str,
                            "description": s.get("description", ""),
                            "device_count": s.get("device_count", 0),
                            "vm_count": s.get("virtualmachine_count", 0)
                        })
                    resp = jsonify({"success": True, "data": netbox_sites})
                    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                    resp.headers['Pragma'] = 'no-cache'
                    resp.headers['Expires'] = '0'
                    return resp
            except Exception as netbox_err:
                logger.warning(f"Falha ao consultar sites no NetBox: {netbox_err}. Usando fallback local.")

        resp = jsonify({"success": True, "data": local_sites})
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/sites', methods=['POST'])
def create_site():
    try:
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Name is required"}), 400

        description = data.get("description", "").strip()
        slug = data.get("slug")
        if not slug:
            slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        created_site = None
        if base_url and token:
            try:
                import requests
                requests.packages.urllib3.disable_warnings()
                headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
                payload = {
                    "name": name,
                    "slug": slug,
                    "status": "active",
                    "description": description
                }
                res = requests.post(f"{base_url}/api/dcim/sites/", json=payload, headers=headers, verify=False, timeout=6)
                if res.status_code in [200, 201]:
                    s = res.json()
                    status_val = s.get("status")
                    status_str = status_val.get("label", "Active") if isinstance(status_val, dict) else str(status_val or "Active")
                    created_site = {
                        "id": s.get("id"),
                        "name": s.get("name"),
                        "slug": s.get("slug"),
                        "status": status_str,
                        "description": s.get("description", ""),
                        "device_count": s.get("device_count", 0),
                        "vm_count": s.get("virtualmachine_count", 0)
                    }
                else:
                    return jsonify({"error": f"Erro do NetBox ({res.status_code}): {res.text}"}), 400
            except Exception as netbox_err:
                logger.warning(f"Falha ao criar site no NetBox: {netbox_err}. Gravando localmente.")

        if not created_site:
            site_id = data.get("id") or uuid.uuid4().hex[:8]
            created_site = {
                "id": site_id,
                "name": name,
                "slug": slug,
                "status": "active",
                "description": description,
                "device_count": 0,
                "vm_count": 0
            }

        # Also maintain config["sites"] for offline fallback
        sites = config.setdefault("sites", [])
        sites.append(created_site)
        ConfigService.save_config(config)
        ConfigService.reload_config()

        return jsonify({"success": True, "message": f"Site '{name}' criado com sucesso no NetBox!", "site": created_site}), 201
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/sites/<site_id>', methods=['PUT'])
def update_site(site_id):
    try:
        data = request.json or {}
        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        name = (data.get("name") or "").strip()
        description = data.get("description", "")
        if not name:
            return jsonify({"error": "Nome do site é obrigatório"}), 400

        if base_url and token:
            try:
                import requests
                requests.packages.urllib3.disable_warnings()
                headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
                payload = {}
                if name: payload["name"] = name
                if description is not None: payload["description"] = description
                res = requests.patch(f"{base_url}/api/dcim/sites/{site_id}/", json=payload, headers=headers, verify=False, timeout=6)
                if res.status_code == 200:
                    s = res.json()
                    data["id"] = s.get("id")
                    data["name"] = s.get("name")
                    data["slug"] = s.get("slug")
            except Exception as ex:
                logger.warning(f"Erro ao atualizar site no NetBox: {ex}")

        sites = config.get("sites", [])
        found = False
        for i, site in enumerate(sites):
            if str(site.get("id")) == str(site_id):
                data["id"] = site_id
                sites[i] = {**site, **data}
                found = True
                break
        if not found:
            data["id"] = site_id
            sites.append(data)

        ConfigService.save_config(config)
        ConfigService.reload_config()
        return jsonify({"success": True, "message": f"Site '{name}' atualizado com sucesso!", "site": data})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/sites/<site_id>', methods=['DELETE'])
def delete_site(site_id):
    try:
        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        if base_url and token:
            try:
                import requests
                requests.packages.urllib3.disable_warnings()
                headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
                res = requests.delete(f"{base_url}/api/dcim/sites/{site_id}/", headers=headers, verify=False, timeout=6)
                if res.status_code in [200, 204]:
                    pass
                elif res.status_code == 404:
                    # Idempotent: already deleted or does not exist
                    pass
                else:
                    return jsonify({"error": f"Erro do NetBox ({res.status_code}): {res.text}"}), 400
            except Exception as netbox_err:
                logger.warning(f"Erro ao excluir site no NetBox: {netbox_err}")

        # Also clean up from local fallback list
        sites = config.get("sites", [])
        new_sites = [s for s in sites if str(s.get("id")) != str(site_id)]
        config["sites"] = new_sites
        ConfigService.save_config(config)
        ConfigService.reload_config()

        return jsonify({"success": True, "message": f"Site {site_id} excluído com sucesso do NetBox!"})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500

@admin_bp.route('/api/admin/manufacturers', methods=['GET'])
def get_manufacturers():
    try:
        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        if base_url and token:
            try:
                import requests
                requests.packages.urllib3.disable_warnings()
                headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
                res = requests.get(f"{base_url}/api/dcim/manufacturers/?limit=100", headers=headers, verify=False, timeout=6)
                if res.status_code == 200:
                    mfgs = [{"id": m.get("id"), "name": m.get("name"), "slug": m.get("slug")} for m in res.json().get('results', [])]
                    resp = jsonify({"success": True, "data": mfgs})
                    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                    return resp
            except Exception:
                pass
        return jsonify({"success": True, "data": [{"name": "HPE"}, {"name": "Cisco"}, {"name": "Dell"}]})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/models', methods=['GET'])
def get_models():
    try:
        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        local_models = config.get("device_models", [])

        if base_url and token:
            try:
                import requests
                requests.packages.urllib3.disable_warnings()
                headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
                res = requests.get(f"{base_url}/api/dcim/device-types/?limit=500", headers=headers, verify=False, timeout=6)
                if res.status_code == 200:
                    netbox_models = []
                    local_profile_map = {str(m.get("id")): m.get("default_profile") for m in local_models}
                    local_name_map = {(m.get("manufacturer", "").strip().lower(), m.get("model", "").strip().lower()): m.get("default_profile") for m in local_models}

                    for dt in res.json().get('results', []):
                        mfg = dt.get('manufacturer', {})
                        mfg_name = mfg.get('name') if isinstance(mfg, dict) else str(mfg or "")
                        model_name = dt.get('model', '')
                        dt_id = dt.get('id')

                        def_prof = local_profile_map.get(str(dt_id)) or local_name_map.get((mfg_name.lower(), model_name.lower())) or "NETWORK_SWITCH"

                        netbox_models.append({
                            "id": dt_id,
                            "manufacturer": mfg_name,
                            "model": model_name,
                            "slug": dt.get("slug"),
                            "part_number": dt.get("part_number") or "",
                            "device_count": dt.get("device_count", 0),
                            "default_profile": def_prof
                        })
                    resp = jsonify({"success": True, "data": netbox_models})
                    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                    resp.headers['Pragma'] = 'no-cache'
                    resp.headers['Expires'] = '0'
                    return resp
            except Exception as netbox_err:
                logger.warning(f"Falha ao consultar modelos no NetBox: {netbox_err}. Usando fallback local.")

        resp = jsonify({"success": True, "data": local_models})
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/models', methods=['POST'])
def create_model():
    try:
        data = request.json or {}
        manufacturer = (data.get("manufacturer") or "").strip()
        model = (data.get("model") or "").strip()
        if not manufacturer or not model:
            return jsonify({"error": "Model and manufacturer are required"}), 400

        default_profile = data.get("default_profile", "NETWORK_SWITCH")
        part_number = data.get("part_number", "").strip()
        slug = data.get("slug")
        if not slug:
            slug = re.sub(r'[^a-z0-9]+', '-', f"{manufacturer}-{model}".lower()).strip('-')

        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        created_model = None
        if base_url and token:
            try:
                import requests
                requests.packages.urllib3.disable_warnings()
                headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}

                # 1. Resolve or create manufacturer in NetBox
                mfg_res = requests.get(f"{base_url}/api/dcim/manufacturers/?limit=100", headers=headers, verify=False, timeout=6)
                mfg_id = None
                if mfg_res.status_code == 200:
                    for m in mfg_res.json().get('results', []):
                        if m.get('name', '').strip().lower() == manufacturer.lower():
                            mfg_id = m.get('id')
                            break

                if not mfg_id:
                    mfg_slug = re.sub(r'[^a-z0-9]+', '-', manufacturer.lower()).strip('-')
                    mfg_create = requests.post(f"{base_url}/api/dcim/manufacturers/", json={"name": manufacturer, "slug": mfg_slug}, headers=headers, verify=False, timeout=6)
                    if mfg_create.status_code in [200, 201]:
                        mfg_id = mfg_create.json().get('id')

                if mfg_id:
                    payload = {
                        "manufacturer": mfg_id,
                        "model": model,
                        "slug": slug,
                        "part_number": part_number
                    }
                    dt_res = requests.post(f"{base_url}/api/dcim/device-types/", json=payload, headers=headers, verify=False, timeout=6)
                    if dt_res.status_code in [200, 201]:
                        dt = dt_res.json()
                        created_model = {
                            "id": dt.get("id"),
                            "manufacturer": manufacturer,
                            "model": model,
                            "slug": dt.get("slug"),
                            "part_number": dt.get("part_number") or "",
                            "default_profile": default_profile,
                            "device_count": 0
                        }
                    else:
                        return jsonify({"error": f"Erro do NetBox ({dt_res.status_code}): {dt_res.text}"}), 400
            except Exception as netbox_err:
                logger.warning(f"Falha ao criar modelo no NetBox: {netbox_err}. Gravando localmente.")

        if not created_model:
            model_id = data.get("id") or uuid.uuid4().hex[:8]
            created_model = {
                "id": model_id,
                "manufacturer": manufacturer,
                "model": model,
                "slug": slug,
                "part_number": part_number,
                "default_profile": default_profile,
                "device_count": 0
            }

        # Also maintain local config for offline fallback
        models = config.setdefault("device_models", [])
        models.append(created_model)
        ConfigService.save_config(config)
        ConfigService.reload_config()

        return jsonify({"success": True, "message": f"Modelo '{manufacturer} {model}' criado com sucesso no NetBox!", "model": created_model}), 201
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/models/<model_id>', methods=['PUT'])
def update_model(model_id):
    try:
        data = request.json or {}
        manufacturer = (data.get("manufacturer") or "").strip()
        model_name = (data.get("model") or "").strip()
        default_profile = data.get("default_profile", "NETWORK_SWITCH")
        part_number = (data.get("part_number") or "").strip()

        if not model_name:
            return jsonify({"error": "Nome do modelo é obrigatório"}), 400

        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        if base_url and token:
            try:
                import requests
                requests.packages.urllib3.disable_warnings()
                headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
                payload = {}
                if model_name: payload["model"] = model_name
                if part_number is not None: payload["part_number"] = part_number

                if manufacturer:
                    mfg_res = requests.get(f"{base_url}/api/dcim/manufacturers/?limit=100", headers=headers, verify=False, timeout=6)
                    if mfg_res.status_code == 200:
                        for m in mfg_res.json().get('results', []):
                            if m.get('name', '').strip().lower() == manufacturer.lower():
                                payload["manufacturer"] = m.get('id')
                                break

                res = requests.patch(f"{base_url}/api/dcim/device-types/{model_id}/", json=payload, headers=headers, verify=False, timeout=6)
                if res.status_code == 200:
                    dt = res.json()
                    data["id"] = dt.get("id")
                    data["model"] = dt.get("model")
            except Exception as ex:
                logger.warning(f"Erro ao atualizar modelo no NetBox: {ex}")

        models = config.setdefault("device_models", [])
        found = False
        for i, m in enumerate(models):
            if str(m.get("id")) == str(model_id):
                data["id"] = model_id
                models[i] = {**m, **data}
                found = True
                break
        if not found:
            data["id"] = model_id
            models.append(data)

        ConfigService.save_config(config)
        ConfigService.reload_config()
        return jsonify({"success": True, "message": f"Modelo '{model_name}' atualizado com sucesso!", "model": data})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/models/<model_id>', methods=['DELETE'])
def delete_model(model_id):
    try:
        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        if base_url and token:
            try:
                import requests
                requests.packages.urllib3.disable_warnings()
                headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
                res = requests.delete(f"{base_url}/api/dcim/device-types/{model_id}/", headers=headers, verify=False, timeout=6)
                if res.status_code in [200, 204]:
                    pass
                elif res.status_code == 404:
                    # Idempotent: already removed or does not exist
                    pass
                else:
                    return jsonify({"error": f"Erro do NetBox ({res.status_code}): {res.text}"}), 400
            except Exception as netbox_err:
                logger.warning(f"Erro ao excluir modelo no NetBox: {netbox_err}")

        models = config.get("device_models", [])
        new_models = [m for m in models if str(m.get("id")) != str(model_id)]
        config["device_models"] = new_models
        ConfigService.save_config(config)
        ConfigService.reload_config()

        return jsonify({"success": True, "message": f"Modelo {model_id} excluído com sucesso do NetBox!"})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


# ============================================================
# NetBox Virtualization Clusters Endpoints
# ============================================================

@admin_bp.route('/api/admin/clusters', methods=['GET'])
def get_admin_clusters():
    try:
        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        fallback_clusters = [
            {"id": 18, "name": "10.11.0.233 - SRVPVE52", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 17, "name": "10.11.0.232 - SRVPVE51", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 20, "name": "10.11.0.236 - SRVPVE50", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 16, "name": "10.11.0.228 - SRVPVE28", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 12, "name": "10.11.0.240 - SRVPVE40", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 7, "name": "10.11.0.243 - SRVPVE43", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 19, "name": "10.11.0.244 - SRVPVE44", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 8, "name": "10.11.0.245 - SRVPVE45", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 1, "name": "10.11.0.247 - SRVPVE47", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 9, "name": "10.11.2.212 - SRVPVE12", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 2, "name": "10.11.2.220 - SRVPVETSNEWS1", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 4, "name": "10.11.2.226 - SRVPVE226", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 10, "name": "10.11.3.81 - SRVPVE81", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 5, "name": "10.10.14.110 -SRVPVE10", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 6, "name": "10.10.14.112 - SRVPVE11", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 14, "name": "10.65.0.10 - SRVPVE29", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 11, "name": "10.65.0.12 - SRVPVE42", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 15, "name": "10.65.0.13 - SRVPVE26", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0},
            {"id": 13, "name": "10.65.0.14 - SRVPVE27", "type": "PROXMOX-PVE", "site": "RedeTV", "vm_count": 0}
        ]

        if not base_url or not token:
            return jsonify({"success": True, "data": fallback_clusters})

        import requests
        requests.packages.urllib3.disable_warnings()
        headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
        res = requests.get(f"{base_url}/api/virtualization/clusters/", headers=headers, verify=False, timeout=6)
        if res.status_code == 200:
            clusters = []
            for c in res.json().get('results', []):
                clusters.append({
                    "id": c["id"],
                    "name": c.get("name"),
                    "type": c.get("type", {}).get("name", "PROXMOX-PVE") if isinstance(c.get("type"), dict) else "PROXMOX-PVE",
                    "site": c.get("site", {}).get("name") if isinstance(c.get("site"), dict) else "-",
                    "vm_count": c.get("virtualmachine_count", 0)
                })
            resp = jsonify({"success": True, "data": clusters})
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
            return resp
        resp = jsonify({"success": True, "data": fallback_clusters})
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/clusters', methods=['POST'])
def create_admin_cluster():
    try:
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Nome do cluster é obrigatório"}), 400

        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        if not base_url or not token:
            return jsonify({"error": "NetBox URL ou Token não configurados em config.json"}), 400

        import requests
        requests.packages.urllib3.disable_warnings()
        headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}

        # 1. Resolve cluster type (default to 1 or search PROXMOX-PVE)
        type_id = data.get("type_id", 1)
        payload = {
            "name": name,
            "type": int(type_id)
        }

        site_id = data.get("site_id")
        if site_id:
            payload["site"] = int(site_id)

        res = requests.post(f"{base_url}/api/virtualization/clusters/", json=payload, headers=headers, verify=False, timeout=6)
        if res.status_code in [200, 201]:
            created = res.json()
            return jsonify({
                "success": True,
                "message": f"Cluster '{name}' criado com sucesso no NetBox!",
                "cluster": {
                    "id": created.get("id"),
                    "name": created.get("name"),
                    "type": created.get("type", {}).get("name", "PROXMOX-PVE") if isinstance(created.get("type"), dict) else "PROXMOX-PVE"
                }
            }), 201
        else:
            return jsonify({"error": f"Erro do NetBox ({res.status_code}): {res.text}"}), 400
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/clusters/<int:cluster_id>', methods=['PUT'])
def update_admin_cluster(cluster_id):
    try:
        data = request.json or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Nome do cluster é obrigatório"}), 400

        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        if not base_url or not token:
            return jsonify({"error": "NetBox URL ou Token não configurados"}), 400

        import requests
        requests.packages.urllib3.disable_warnings()
        headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}

        payload = {"name": name}
        res = requests.patch(f"{base_url}/api/virtualization/clusters/{cluster_id}/", json=payload, headers=headers, verify=False, timeout=6)
        if res.status_code in [200, 201]:
            updated = res.json()
            return jsonify({
                "success": True,
                "message": f"Cluster ID #{cluster_id} atualizado com sucesso no NetBox!",
                "cluster": {
                    "id": updated.get("id"),
                    "name": updated.get("name"),
                    "type": updated.get("type", {}).get("name", "PROXMOX-PVE") if isinstance(updated.get("type"), dict) else "PROXMOX-PVE"
                }
            })
        else:
            return jsonify({"error": f"Erro do NetBox ({res.status_code}): {res.text}"}), 400
    except requests.exceptions.RequestException as req_err:
        logger.warning(f"Falha de conexão com NetBox ao atualizar cluster: {req_err}")
        return jsonify({
            "success": True,
            "message": f"Cluster ID #{cluster_id} atualizado (modo offline)",
            "cluster": {"id": cluster_id, "name": name, "type": "PROXMOX-PVE"}
        })
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/clusters/<int:cluster_id>', methods=['DELETE'])
def delete_admin_cluster(cluster_id):
    try:
        config = ConfigService.load_config()
        netbox_cfg = config.get('netbox', {})
        base_url = netbox_cfg.get('url', '').rstrip('/')
        token = netbox_cfg.get('api_token', '')

        if not base_url or not token:
            return jsonify({"error": "NetBox URL ou Token não configurados"}), 400

        import requests
        requests.packages.urllib3.disable_warnings()
        headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}

        res = requests.delete(f"{base_url}/api/virtualization/clusters/{cluster_id}/", headers=headers, verify=False, timeout=6)
        if res.status_code in [200, 204]:
            return jsonify({"success": True, "message": f"Cluster ID {cluster_id} excluído com sucesso do NetBox!"})
        elif res.status_code == 404:
            # Idempotent: NetBox returns 404 if the cluster was already deleted or doesn't exist
            return jsonify({"success": True, "message": f"Cluster ID {cluster_id} já foi removido ou não existe mais no NetBox."})
        else:
            return jsonify({"error": f"Erro do NetBox ({res.status_code}): {res.text}"}), 400
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


# ============================================================
# Database & Integrations Configuration Endpoints
# ============================================================

@admin_bp.route('/api/settings/db', methods=['GET'])
def get_db_settings():
    try:
        config = ConfigService.load_config()
        dbs = config.get("databases", {})
        # Sanitize password fields for display (send empty or placeholder, or actual if editing)
        return jsonify({
            "netdisco": dbs.get("netdisco", {}),
            "librenms": dbs.get("librenms", {}),
            "zabbix": dbs.get("zabbix", {})
        })
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/settings/db', methods=['POST'])
def save_db_settings():
    try:
        data = request.json or {}
        config = ConfigService.load_config()
        dbs = config.setdefault("databases", {})

        for db_name in ["netdisco", "librenms", "zabbix"]:
            if db_name in data:
                dbs[db_name] = data[db_name]

        ConfigService.save_config(config)
        ConfigService.reload_config()
        return jsonify({"success": True, "message": "Configurações de banco salvas com sucesso!"})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/settings/change-password', methods=['POST'])
def change_own_password():
    try:
        data = request.json or {}
        curr_pw = data.get("current_password", "")
        new_pw = data.get("new_password", "")

        if not curr_pw or not new_pw:
            return jsonify({"success": False, "error": "Senha atual e nova senha são obrigatórias"}), 400

        curr_user = session.get("username", "admin")
        users_cfg = ConfigService.load_users()
        users_list = users_cfg.get("users", [])

        target = None
        for u in users_list:
            if u.get("username") == curr_user:
                target = u
                break

        curr_hash = hashlib.sha256(curr_pw.encode('utf-8')).hexdigest()

        if not target:
            # Fallback legacy single user check
            if users_cfg.get("username") == curr_user and users_cfg.get("password_hash") == curr_hash:
                new_hash = hashlib.sha256(new_pw.encode('utf-8')).hexdigest()
                users_cfg["password_hash"] = new_hash
                users_cfg["users"] = [{
                    "username": curr_user,
                    "password_hash": new_hash,
                    "role": "admin",
                    "name": "Administrador Principal"
                }]
                ConfigService.save_users(users_cfg)
                return jsonify({"success": True, "message": "Senha alterada com sucesso!"})
            return jsonify({"success": False, "error": "Senha atual incorreta."}), 401

        if target.get("password_hash") != curr_hash:
            return jsonify({"success": False, "error": "Senha atual incorreta."}), 401

        new_hash = hashlib.sha256(new_pw.encode('utf-8')).hexdigest()
        target["password_hash"] = new_hash
        ConfigService.save_users(users_cfg)
        return jsonify({"success": True, "message": "Senha alterada com sucesso!"})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


# ============================================================
# NetLens User Management CRUD Endpoints
# ============================================================

@admin_bp.route('/api/admin/users', methods=['GET'])
def list_admin_users():
    try:
        users_cfg = ConfigService.load_users()
        user_list = []
        for u in users_cfg.get("users", []):
            user_list.append({
                "username": u.get("username"),
                "name": u.get("name", u.get("username")),
                "role": u.get("role", "operator"),
                "created_at": u.get("created_at", "-")
            })
        return jsonify({"success": True, "data": user_list, "current_user": session.get("username")})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/users', methods=['POST'])
def create_admin_user():
    try:
        data = request.json or {}
        username = (data.get("username") or "").strip().lower()
        password = data.get("password") or ""
        role = data.get("role") or "operator"
        name = (data.get("name") or username).strip()

        if not username or not password:
            return jsonify({"error": "Nome de usuário e senha são obrigatórios"}), 400

        if len(password) < 4:
            return jsonify({"error": "A senha deve ter pelo menos 4 caracteres"}), 400

        users_cfg = ConfigService.load_users()
        users_list = users_cfg.setdefault("users", [])

        for u in users_list:
            if u.get("username", "").lower() == username:
                return jsonify({"error": f"Usuário '{username}' já existe"}), 409

        import datetime
        pw_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        new_user = {
            "username": username,
            "name": name,
            "role": "admin" if role == "admin" else "operator",
            "password_hash": pw_hash,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        users_list.append(new_user)
        ConfigService.save_users(users_cfg)

        return jsonify({
            "success": True,
            "message": f"Usuário '{username}' criado com sucesso!",
            "user": {
                "username": new_user["username"],
                "name": new_user["name"],
                "role": new_user["role"]
            }
        }), 201
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/users/<username>', methods=['PUT'])
def update_admin_user(username):
    try:
        username = username.strip().lower()
        data = request.json or {}
        new_role = data.get("role")
        new_password = data.get("password")
        new_name = data.get("name")

        users_cfg = ConfigService.load_users()
        users_list = users_cfg.get("users", [])

        target = None
        for u in users_list:
            if u.get("username", "").lower() == username:
                target = u
                break

        if not target:
            return jsonify({"error": f"Usuário '{username}' não encontrado"}), 404

        if new_name:
            target["name"] = new_name.strip()

        if new_role:
            target["role"] = "admin" if new_role == "admin" else "operator"

        if new_password:
            if len(new_password) < 4:
                return jsonify({"error": "A senha deve ter pelo menos 4 caracteres"}), 400
            target["password_hash"] = hashlib.sha256(new_password.encode('utf-8')).hexdigest()

        ConfigService.save_users(users_cfg)
        return jsonify({"success": True, "message": f"Usuário '{username}' atualizado com sucesso!"})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/users/<username>', methods=['DELETE'])
def delete_admin_user(username):
    try:
        username = username.strip().lower()
        current_user = (session.get("username") or "").lower()

        if username == current_user:
            return jsonify({"error": "Não é permitido excluir o usuário que está atualmente logado"}), 400

        users_cfg = ConfigService.load_users()
        users_list = users_cfg.get("users", [])

        # Prevent deleting the last admin
        admins = [u for u in users_list if u.get("role") == "admin"]
        target = next((u for u in users_list if u.get("username", "").lower() == username), None)

        if not target:
            return jsonify({"error": f"Usuário '{username}' não encontrado"}), 404

        if target.get("role") == "admin" and len(admins) <= 1:
            return jsonify({"error": "Não é permitido excluir o único administrador do sistema"}), 400

        users_cfg["users"] = [u for u in users_list if u.get("username", "").lower() != username]
        ConfigService.save_users(users_cfg)

        return jsonify({"success": True, "message": f"Usuário '{username}' excluído com sucesso!"})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


# ==============================================================================
# CRUD & TESTES PARA SERVIDORES / INTEGRAÇÕES DINÂMICAS
# ==============================================================================

def _test_server_url(url: str, timeout: float = 3.0) -> dict:
    """Helper para testar conectividade de um servidor web/API com medição de latência."""
    if not url:
        return {"online": False, "error": "URL não informada", "latency_ms": 0}
    try:
        import time, requests
        requests.packages.urllib3.disable_warnings()
        t0 = time.time()
        res = requests.get(url, timeout=timeout, verify=False)
        lat = round((time.time() - t0) * 1000, 1)
        is_online = res.status_code < 500
        return {
            "online": is_online,
            "status_code": res.status_code,
            "latency_ms": lat,
            "error": None if is_online else f"HTTP {res.status_code}"
        }
    except Exception as e:
        return {"online": False, "error": SecretSanitizer.sanitize_text(str(e)), "latency_ms": 0}


@admin_bp.route('/api/admin/servers', methods=['GET'])
def get_admin_servers():
    """Lista todos os servidores cadastrados com checagem rápida de conectividade."""
    try:
        config = ConfigService.load_config()
        servers = config.get("servers", [])
        
        # Verificar status de cada servidor ativo
        servers_with_status = []
        for s in servers:
            s_copy = s.copy()
            # Mascarar senha ao retornar para a interface
            if s_copy.get("password"):
                s_copy["has_password"] = True
                s_copy["password"] = "••••••••"
            if s_copy.get("api_token"):
                tok = s_copy["api_token"]
                s_copy["api_token_masked"] = f"{tok[:4]}...{tok[-4:]}" if len(tok) > 8 else "••••••••"
            
            if s_copy.get("enabled", True):
                conn = _test_server_url(s_copy.get("url", ""), timeout=2.0)
                s_copy["status"] = "online" if conn.get("online") else "offline"
                s_copy["latency_ms"] = conn.get("latency_ms", 0)
                s_copy["status_code"] = conn.get("status_code")
                s_copy["status_error"] = conn.get("error")
            else:
                s_copy["status"] = "disabled"
                s_copy["latency_ms"] = 0

            servers_with_status.append(s_copy)

        resp = jsonify({"success": True, "data": servers_with_status})
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/servers', methods=['POST'])
def create_admin_server():
    """Cadastra um novo servidor integrado."""
    try:
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        url = data.get("url", "").strip().rstrip('/')
        srv_type = data.get("type", "generic").strip().lower()

        if not name or not url:
            return jsonify({"error": "Nome e Endereço/URL são obrigatórios"}), 400

        config = ConfigService.load_config()
        servers = config.setdefault("servers", [])

        import uuid
        server_id = data.get("id") or f"srv-{uuid.uuid4().hex[:8]}"
        
        # Evitar ID duplicado
        if any(s.get("id") == server_id for s in servers):
            server_id = f"srv-{uuid.uuid4().hex[:8]}"

        new_server = {
            "id": server_id,
            "name": name,
            "type": srv_type,
            "url": url,
            "api_token": data.get("api_token", "").strip(),
            "user": data.get("user", "").strip(),
            "password": data.get("password", ""),
            "description": data.get("description", "").strip(),
            "show_in_header": bool(data.get("show_in_header", True)),
            "enabled": bool(data.get("enabled", True))
        }

        servers.append(new_server)
        ConfigService.save_config(config)
        ConfigService.reload_config()

        return jsonify({
            "success": True,
            "message": f"Servidor '{name}' cadastrado com sucesso!",
            "data": new_server
        }), 201
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/servers/<server_id>', methods=['PUT'])
def update_admin_server(server_id):
    """Atualiza as propriedades de um servidor existente."""
    try:
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        url = data.get("url", "").strip().rstrip('/')

        if not name or not url:
            return jsonify({"error": "Nome e Endereço/URL são obrigatórios"}), 400

        config = ConfigService.load_config()
        servers = config.get("servers", [])
        target = next((s for s in servers if s.get("id") == server_id), None)

        if not target:
            return jsonify({"error": f"Servidor '{server_id}' não encontrado"}), 404

        target["name"] = name
        target["type"] = data.get("type", target.get("type", "generic")).strip().lower()
        target["url"] = url
        target["description"] = data.get("description", "").strip()
        target["show_in_header"] = bool(data.get("show_in_header", True))
        target["enabled"] = bool(data.get("enabled", True))

        if "user" in data:
            target["user"] = data["user"].strip()

        # Atualizar senha apenas se informada e não for a máscara
        if data.get("password") and data.get("password") != "••••••••":
            target["password"] = data["password"]

        # Atualizar token apenas se informado e não for máscara
        if data.get("api_token") and "••••" not in data.get("api_token"):
            target["api_token"] = data["api_token"].strip()

        # Sincronizar chave legada caso seja um dos servidores nativos
        if target["type"] in ["netbox", "zabbix", "librenms", "netdisco"]:
            leg = config.setdefault(target["type"], {})
            leg["url"] = target["url"]
            if target.get("user"): leg["user"] = target["user"]
            if target.get("password"): leg["password"] = target["password"]
            if target.get("api_token"): leg["api_token"] = target["api_token"]

        ConfigService.save_config(config)
        ConfigService.reload_config()

        return jsonify({
            "success": True,
            "message": f"Servidor '{name}' atualizado com sucesso!",
            "data": target
        })
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/servers/<server_id>', methods=['DELETE'])
def delete_admin_server(server_id):
    """Remove um servidor cadastrado."""
    try:
        config = ConfigService.load_config()
        servers = config.get("servers", [])
        target = next((s for s in servers if s.get("id") == server_id), None)

        if not target:
            return jsonify({"error": f"Servidor '{server_id}' não encontrado"}), 404

        config["servers"] = [s for s in servers if s.get("id") != server_id]
        ConfigService.save_config(config)
        ConfigService.reload_config()

        return jsonify({
            "success": True,
            "message": f"Servidor '{target.get('name')}' excluído com sucesso!"
        })
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/servers/test', methods=['POST'])
def test_admin_server_connection():
    """Testa a conectividade de um endereço/servidor antes de salvar."""
    try:
        data = request.get_json() or {}
        url = data.get("url", "").strip()
        if not url:
            return jsonify({"error": "URL/Endereço não informado"}), 400

        result = _test_server_url(url, timeout=4.0)
        return jsonify({
            "success": True,
            "result": result
        })
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/port-events-config', methods=['GET'])
def get_port_events_config():
    """Retorna as configurações atuais de monitoramento de eventos de portas e STP."""
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        config = ConfigService.load_config()
        settings = config.get("port_events_settings", {
            "flapping_warning_threshold": 3,
            "flapping_critical_threshold": 6,
            "default_window_hours": 24,
            "stp_patterns": [
                "Blocked by STP",
                "BPDU Protection",
                "BPDU",
                "MSTP_BLOCKED",
                "MSTP_DISCARDING",
                "BLOCK_BPDUGUARD",
                "loop-protect",
                "err-disable"
            ]
        })
        return jsonify({"success": True, "data": settings})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/port-events-config', methods=['PUT'])
def update_port_events_config():
    """Atualiza as configurações de monitoramento de portas e padrões STP."""
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    if session.get('user_role') != 'admin':
        return jsonify({"error": "Forbidden"}), 403

    try:
        data = request.get_json() or {}
        config = ConfigService.load_config()
        current = config.setdefault("port_events_settings", {})

        if "flapping_warning_threshold" in data:
            try:
                current["flapping_warning_threshold"] = max(1, min(100, int(data["flapping_warning_threshold"])))
            except (ValueError, TypeError):
                pass
        if "flapping_critical_threshold" in data:
            try:
                crit_val = int(data["flapping_critical_threshold"])
                warn_val = current.get("flapping_warning_threshold", 3)
                current["flapping_critical_threshold"] = max(warn_val, min(200, crit_val))
            except (ValueError, TypeError):
                pass
        if "default_window_hours" in data:
            try:
                current["default_window_hours"] = max(1, min(168, int(data["default_window_hours"])))
            except (ValueError, TypeError):
                pass
        if "stp_patterns" in data and isinstance(data["stp_patterns"], list):
            cleaned_patterns = []
            for p in data["stp_patterns"]:
                p_str = str(p).strip()
                if p_str and p_str not in cleaned_patterns:
                    cleaned_patterns.append(p_str)
            if cleaned_patterns:
                current["stp_patterns"] = cleaned_patterns

        ConfigService.save_config(config)
        ConfigService.reload_config()

        return jsonify({
            "success": True,
            "message": "Configurações de eventos de portas salvas com sucesso!",
            "data": current
        })
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/bottlenecks-config', methods=['GET'])
def get_bottlenecks_config():
    """Retorna as configurações de detecção de gargalos de tráfego e erros de portas."""
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        config = ConfigService.load_config()
        settings = config.get("bottlenecks_settings", {
            "util_warning_threshold": 75.0,
            "util_critical_threshold": 90.0,
            "ignore_virtual_interfaces": True,
            "min_speed_mbps": 100.0,
            "error_detection_mode": "rate_and_delta",
            "error_min_delta": 5,
            "error_critical_rate": 10.0,
            "discard_min_delta": 50
        })
        return jsonify({"success": True, "data": settings})
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500


@admin_bp.route('/api/admin/bottlenecks-config', methods=['PUT'])
def update_bottlenecks_config():
    """Atualiza as regras de detecção de gargalos de tráfego e erros/descartes de portas."""
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    if session.get('user_role') != 'admin':
        return jsonify({"error": "Forbidden"}), 403

    try:
        data = request.get_json() or {}
        config = ConfigService.load_config()
        current = config.setdefault("bottlenecks_settings", {})

        if "util_warning_threshold" in data:
            try:
                val = float(data["util_warning_threshold"])
                current["util_warning_threshold"] = max(10.0, min(99.0, val))
            except (ValueError, TypeError):
                pass

        if "util_critical_threshold" in data:
            try:
                val = float(data["util_critical_threshold"])
                warn = current.get("util_warning_threshold", 75.0)
                current["util_critical_threshold"] = max(warn, min(100.0, val))
            except (ValueError, TypeError):
                pass

        if "ignore_virtual_interfaces" in data:
            current["ignore_virtual_interfaces"] = bool(data["ignore_virtual_interfaces"])

        if "min_speed_mbps" in data:
            try:
                current["min_speed_mbps"] = max(0.0, float(data["min_speed_mbps"]))
            except (ValueError, TypeError):
                pass

        if "error_detection_mode" in data:
            mode = str(data["error_detection_mode"]).strip().lower()
            if mode in ["rate_and_delta", "cumulative"]:
                current["error_detection_mode"] = mode

        if "error_min_delta" in data:
            try:
                current["error_min_delta"] = max(0, int(data["error_min_delta"]))
            except (ValueError, TypeError):
                pass

        if "error_critical_rate" in data:
            try:
                current["error_critical_rate"] = max(0.1, float(data["error_critical_rate"]))
            except (ValueError, TypeError):
                pass

        if "discard_min_delta" in data:
            try:
                current["discard_min_delta"] = max(0, int(data["discard_min_delta"]))
            except (ValueError, TypeError):
                pass

        ConfigService.save_config(config)
        ConfigService.reload_config()

        return jsonify({
            "success": True,
            "message": "Configurações de gargalos e erros salvas com sucesso!",
            "data": current
        })
    except Exception as e:
        return jsonify({"error": SecretSanitizer.sanitize_exception(e)}), 500




