from flask import Blueprint, jsonify, request, session
from app.models.vlan_intent import VlanIntent, PropagationPolicy
from app.services.intent_engine import VlanIntentEngine

intent_bp = Blueprint('intent', __name__)
engine = VlanIntentEngine()

@intent_bp.route('/api/vlans/intent', methods=['POST'])
def create_vlan_intent():
    data = request.json or {}
    vlan_id = data.get("vlan_id")
    name = data.get("name", "").strip()
    target_switch = data.get("target_switch", "").strip()
    target_port = data.get("target_port", "").strip()
    propagation_str = data.get("propagation", "PATH_TO_CORE").strip().upper()
    target_mode = data.get("target_mode", "access").strip().lower()

    if not vlan_id or not name or not target_switch or not target_port:
        return jsonify({"success": False, "error": "VLAN ID, nome, switch e porta sao obrigatorios."}), 400

    try:
        propagation = PropagationPolicy(propagation_str)
    except ValueError:
        return jsonify({"success": False, "error": f"Politica de propagacao invalida: {propagation_str}"}), 400

    intent = VlanIntent(
        vlan_id=int(vlan_id),
        name=name,
        target_switch=target_switch,
        target_port=target_port,
        propagation=propagation,
        target_mode=target_mode
    )

    try:
        user = session.get("username", "admin")
        change_plan = engine.generate_plan(intent, created_by=user)
        return jsonify({"success": True, "change_plan": change_plan.to_dict()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@intent_bp.route('/api/change-plans/<plan_id>', methods=['GET'])
def get_change_plan_status(plan_id):
    plan = engine.get_change_plan(plan_id)
    if not plan:
        return jsonify({"success": False, "error": "Plano de alteracao nao encontrado."}), 404
    return jsonify({"success": True, "change_plan": plan.to_dict()})

@intent_bp.route('/api/change-plans/<plan_id>/approve', methods=['POST'])
def approve_change_plan(plan_id):
    user = session.get("username", "admin")
    try:
        plan = engine.approve_plan(plan_id, approver=user)
        return jsonify({"success": True, "change_plan": plan.to_dict()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@intent_bp.route('/api/change-plans/<plan_id>/apply', methods=['POST'])
def apply_change_plan(plan_id):
    try:
        res = engine.apply_plan(plan_id)
        return jsonify({"success": True, "result": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
