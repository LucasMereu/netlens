import os
import time
import uuid
import requests
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, jsonify, request
from app.services.config_service import ConfigService

links_bp = Blueprint('links', __name__)

def _test_link_url(url: str, timeout: float = 2.5) -> dict:
    """Testa a conectividade de um link útil com medição de latência."""
    if not url:
        return {"online": False, "error": "URL não informada", "latency_ms": 0, "status_code": None}
    try:
        requests.packages.urllib3.disable_warnings()
        t0 = time.time()
        # Head primeiro para ser o mais rápido possível; fallback para GET se não suportado
        try:
            res = requests.head(url, timeout=timeout, verify=False, allow_redirects=True)
            if res.status_code >= 405: # Method Not Allowed
                res = requests.get(url, timeout=timeout, verify=False, stream=True)
        except requests.RequestException:
            res = requests.get(url, timeout=timeout, verify=False, stream=True)

        lat = round((time.time() - t0) * 1000, 1)
        is_online = res.status_code < 500
        return {
            "online": is_online,
            "status_code": res.status_code,
            "latency_ms": lat,
            "error": None if is_online else f"HTTP {res.status_code}"
        }
    except Exception as e:
        return {
            "online": False,
            "error": str(e),
            "latency_ms": 0,
            "status_code": None
        }


@links_bp.route('/api/links', methods=['GET'])
def get_links():
    """
    Lista todos os links úteis cadastrados com status ao vivo e latência.
    Suporta ?check_status=false para retorno instantâneo.
    """
    links = ConfigService.load_links() or []
    check_status = request.args.get('check_status', 'true').lower() in ['true', '1', 'yes']

    # Garante que cada item possua um identificador único e campos estruturados
    updated = False
    for idx, item in enumerate(links):
        if not item.get("id"):
            item["id"] = f"link-{uuid.uuid4().hex[:8]}"
            updated = True
        if not item.get("category"):
            # Inferir categoria básica pelo nome/tipo
            name_lower = (item.get("name") or "").lower()
            if any(k in name_lower for k in ["proxmox", "pdm", "cluster"]):
                item["category"] = "Virtualização"
                item["type"] = item.get("type") or "proxmox"
            elif any(k in name_lower for k in ["sophos", "firewall"]):
                item["category"] = "Segurança & Firewall"
                item["type"] = item.get("type") or "firewall"
            elif any(k in name_lower for k in ["zimbra", "mail", "quarantine", "e-mail"]):
                item["category"] = "Comunicação & E-mail"
                item["type"] = item.get("type") or "email"
            elif any(k in name_lower for k in ["grafana", "zabbix", "librenms", "dashboard"]):
                item["category"] = "Monitoramento"
                item["type"] = item.get("type") or "grafana"
            elif any(k in name_lower for k in ["netbox", "netdisco"]):
                item["category"] = "Infraestrutura"
                item["type"] = item.get("type") or "netbox"
            else:
                item["category"] = "Geral / Ferramentas"
                item["type"] = item.get("type") or "generic"
            updated = True

    if updated:
        ConfigService.save_links(links)

    if not check_status:
        return jsonify({"success": True, "links": links})

    # Checagem concorrente de status (máximo 2.5s para todos os links em paralelo)
    def _check_item(l):
        res = l.copy()
        url = res.get("url", "").strip()
        conn = _test_link_url(url)
        res["online"] = conn["online"]
        res["status"] = "online" if conn["online"] else "offline"
        res["latency_ms"] = conn["latency_ms"]
        res["status_code"] = conn["status_code"]
        res["status_error"] = conn["error"]
        return res

    with ThreadPoolExecutor(max_workers=12) as executor:
        links_with_status = list(executor.map(_check_item, links))

    resp = jsonify({"success": True, "links": links_with_status})
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@links_bp.route('/api/links', methods=['POST'])
def add_link():
    """Adiciona um novo link útil com categoria e tipo."""
    data = request.json or {}
    name = data.get('name', '').strip()
    url = data.get('url', '').strip()
    category = data.get('category', 'Geral / Ferramentas').strip()
    link_type = data.get('type', 'generic').strip()
    description = data.get('description', '').strip()

    if not name or not url:
        return jsonify({"success": False, "error": "Nome e URL são obrigatórios."}), 400

    links = ConfigService.load_links() or []
    new_link = {
        "id": f"link-{uuid.uuid4().hex[:8]}",
        "name": name,
        "url": url,
        "category": category,
        "type": link_type,
        "description": description,
        "created_at": int(time.time())
    }
    links.append(new_link)
    ConfigService.save_links(links)

    # Teste rápido do novo link
    conn = _test_link_url(url)
    new_link["online"] = conn["online"]
    new_link["status"] = "online" if conn["online"] else "offline"
    new_link["latency_ms"] = conn["latency_ms"]

    return jsonify({"success": True, "link": new_link, "links": links})


@links_bp.route('/api/links/<link_id>', methods=['PUT'])
def update_link(link_id):
    """Atualiza um link existente por ID ou índice."""
    data = request.json or {}
    links = ConfigService.load_links() or []

    target_idx = None
    if link_id.isdigit():
        idx = int(link_id)
        if 0 <= idx < len(links):
            target_idx = idx
    if target_idx is None:
        for i, l in enumerate(links):
            if l.get("id") == link_id:
                target_idx = i
                break

    if target_idx is None:
        return jsonify({"success": False, "error": f"Link '{link_id}' não encontrado."}), 404

    item = links[target_idx]
    if "name" in data and data["name"].strip():
        item["name"] = data["name"].strip()
    if "url" in data and data["url"].strip():
        item["url"] = data["url"].strip()
    if "category" in data:
        item["category"] = data["category"].strip()
    if "type" in data:
        item["type"] = data["type"].strip()
    if "description" in data:
        item["description"] = data["description"].strip()

    ConfigService.save_links(links)
    return jsonify({"success": True, "link": item, "links": links})


@links_bp.route('/api/links/<link_id>', methods=['DELETE'])
def delete_link(link_id):
    """Exclui um link por ID ou índice."""
    links = ConfigService.load_links() or []

    target_idx = None
    if link_id.isdigit():
        idx = int(link_id)
        if 0 <= idx < len(links):
            target_idx = idx
    if target_idx is None:
        for i, l in enumerate(links):
            if l.get("id") == link_id:
                target_idx = i
                break

    if target_idx is None:
        return jsonify({"success": False, "error": f"Link '{link_id}' não encontrado."}), 404

    removed = links.pop(target_idx)
    ConfigService.save_links(links)
    return jsonify({"success": True, "removed": removed, "links": links})


@links_bp.route('/api/links/test', methods=['POST'])
def test_link():
    """Testa a conectividade imediata de uma URL específica."""
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"success": False, "error": "URL não informada."}), 400

    conn = _test_link_url(url)
    return jsonify({"success": True, **conn})


@links_bp.route('/api/links/category/rename', methods=['POST'])
def rename_category():
    """Renomeia uma categoria em todos os links associados."""
    data = request.json or {}
    old_name = (data.get('old_name') or '').strip()
    new_name = (data.get('new_name') or '').strip()

    if not old_name or not new_name:
        return jsonify({"success": False, "error": "Nome atual e novo nome da categoria são obrigatórios."}), 400

    links = ConfigService.load_links() or []
    changed = 0
    for l in links:
        if (l.get('category') or '').strip() == old_name:
            l['category'] = new_name
            changed += 1

    if changed > 0:
        ConfigService.save_links(links)

    return jsonify({"success": True, "changed": changed, "links": links})

