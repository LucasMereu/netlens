import os
import io
import csv
from datetime import datetime
from flask import Blueprint, jsonify, request, session, Response
from app.services.server_inventory_service import ServerInventoryService

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/api/audit-report', methods=['GET'])
def get_audit_report():
    report_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'reports', 'network_audit_report.md')
    try:
        if os.path.exists(report_path):
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({"success": True, "content": content})
        else:
            return jsonify({"success": False, "error": "Relatorio de auditoria nao encontrado."}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@reports_bp.route('/api/reports/servers/csv', methods=['GET'])
def export_server_inventory_csv():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401

    inventory = ServerInventoryService.get_server_inventory(force_refresh=False)
    servers = inventory.get('servers', [])

    output = io.StringIO()
    # Write UTF-8 BOM for Microsoft Excel compatibility
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    # Header
    writer.writerow([
        'Hostname',
        'IP',
        'Sistema Operacional',
        'Status',
        'Origem',
        'CPU Modelo',
        'CPU Cores',
        'CPU Uso (%)',
        'RAM Total',
        'RAM Usada',
        'RAM Uso (%)',
        'Storage Total',
        'Storage Usado',
        'Storage Uso (%)',
        'Particoes Alerta (>90%)',
        'Uptime',
        'Finalidade / Grupo'
    ])

    for s in servers:
        crit_disks = [
            f"{d['mount']} ({d['percent']}%)"
            for d in s.get('storage', {}).get('partitions', [])
            if d.get('percent', 0) >= 90
        ]
        crit_disks_str = ', '.join(crit_disks) if crit_disks else 'Nenhuma'

        writer.writerow([
            s.get('hostname', ''),
            s.get('ip', ''),
            s.get('os', '').upper(),
            s.get('status', '').upper(),
            s.get('source', '').upper(),
            s.get('cpu', {}).get('model', ''),
            s.get('cpu', {}).get('cores', 0),
            f"{s.get('cpu', {}).get('percent', 0)}%",
            s.get('memory', {}).get('total_formatted', '0 B'),
            s.get('memory', {}).get('used_formatted', '0 B'),
            f"{s.get('memory', {}).get('percent', 0)}%",
            s.get('storage', {}).get('total_formatted', '0 B'),
            s.get('storage', {}).get('used_formatted', '0 B'),
            f"{s.get('storage', {}).get('percent', 0)}%",
            crit_disks_str,
            s.get('uptime_formatted', 'N/A'),
            s.get('purpose', '')
        ])

    csv_data = output.getvalue()
    filename = f"inventario_servidores_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        csv_data,
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'no-cache'
        }
    )


@reports_bp.route('/api/reports/devices/<category>/csv', methods=['GET'])
def export_category_inventory_csv(category):
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401

    category = category.lower().strip()
    res = ServerInventoryService.get_category_inventory(category, force_refresh=False)
    devices = res.get('devices', [])
    cat_label = res.get('category_label', category)

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    # Header
    writer.writerow([
        'Nome / Hostname',
        'IP',
        'Fabricante / Modelo',
        'Sistema Operacional / Firmware',
        'Status',
        'Portas Ativas / Total',
        'Latencia Ping (ms)',
        'Uptime'
    ])

    for d in devices:
        ports_str = f"{d.get('ports_active', 0)} / {d.get('ports_total', 0)}" if d.get('ports_total') else '-'
        ping_str = f"{d.get('ping_ms')} ms" if d.get('ping_ms') is not None else '-'

        writer.writerow([
            d.get('hostname', ''),
            d.get('ip', ''),
            d.get('hardware', ''),
            d.get('version', '') or d.get('os', ''),
            d.get('status', '').upper(),
            ports_str,
            ping_str,
            d.get('uptime_formatted', 'N/A')
        ])

    csv_data = output.getvalue()
    filename = f"inventario_{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        csv_data,
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'no-cache'
        }
    )
