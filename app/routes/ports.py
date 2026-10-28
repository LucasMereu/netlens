from flask import Blueprint, jsonify, request
from app.clients import get_librenms_client, get_netdisco_client, is_mock_mode
from app.analysis.port_event_tracker import PortEventTracker
from app.services.config_service import ConfigService

ports_bp = Blueprint('ports', __name__)

MOCK_PORT_EVENTS = [
    {
        "port_id": 101,
        "device_id": 1,
        "device_name": "CORE-SW01",
        "device_ip": "10.100.1.1",
        "port_name": "GigabitEthernet1/0/5",
        "status": "down",
        "timestamp": "2026-06-02 15:45:00",
        "relative_time": "há 6 minutos",
        "neighbor": None,
        "flaps": 7,
        "is_flapping": True,
        "flap_severity": "critical",
        "stp_blocked": True,
        "stp_details": {
            "timestamp": "2026-06-02 15:45:00",
            "message": "port 5 is Blocked by STP [00435]",
            "type": "BPDU Protect / STP Block"
        }
    },
    {
        "port_id": 102,
        "device_id": 2,
        "device_name": "DIST-SW01",
        "device_ip": "10.100.1.2",
        "port_name": "GigabitEthernet1/0/12",
        "status": "up",
        "timestamp": "2026-06-02 15:30:00",
        "relative_time": "há 21 minutos",
        "neighbor": {
            "neighbor_name": "ACC-SW-T1-1",
            "neighbor_ip": "10.100.10.10",
            "neighbor_port": "GigabitEthernet0/1"
        },
        "flaps": 1,
        "is_flapping": False,
        "flap_severity": "none",
        "stp_blocked": False,
        "stp_details": None
    },
    {
        "port_id": 103,
        "device_id": 190,
        "device_name": "aruba-2930f-48g-poep-4sfpp",
        "device_ip": "172.16.11.4",
        "port_name": "12",
        "status": "down",
        "timestamp": "2026-09-14 17:01:03",
        "relative_time": "há 1 dia",
        "neighbor": None,
        "flaps": 7,
        "is_flapping": True,
        "flap_severity": "critical",
        "stp_blocked": True,
        "stp_details": {
            "timestamp": "2026-09-14 17:01:03",
            "message": "port 12 is Blocked by STP [00435]",
            "type": "BPDU Protect / STP Block"
        }
    }
]

@ports_bp.route('/api/ports/events')
def get_port_events():
    page = request.args.get('page', default=1, type=int)
    limit = request.args.get('limit', default=15, type=int)
    paginate = request.args.get('paginate', default='false').lower() == 'true'
    
    # Parâmetros dinâmicos configuráveis
    hours = request.args.get('hours', default=None, type=int)
    min_flaps = request.args.get('min_flaps', default=None, type=int)
    stp_only = request.args.get('stp_only', default='false').lower() == 'true'
    search = request.args.get('search', default='').strip().lower()

    ln = get_librenms_client()
    nd = get_netdisco_client()
    
    if is_mock_mode() or not ln:
        events_list = [dict(e) for e in MOCK_PORT_EVENTS]
        # Aplica filtros nos mock events para testes
        if stp_only:
            events_list = [e for e in events_list if e.get('stp_blocked')]
        if min_flaps:
            events_list = [e for e in events_list if e.get('flaps', 0) >= min_flaps]
        if search:
            events_list = [
                e for e in events_list if 
                search in e.get('device_name', '').lower() or 
                search in e.get('device_ip', '').lower() or 
                search in e.get('port_name', '').lower()
            ]
    else:
        try:
            tracker = PortEventTracker(ln, nd)
            fetch_limit = 500 if (paginate or stp_only or min_flaps or search) else limit
            events_list = tracker.get_recent_port_events(
                limit=fetch_limit,
                hours_back=hours,
                min_flaps=min_flaps,
                stp_only=stp_only
            )
            if search:
                events_list = [
                    e for e in events_list if 
                    search in e.get('device_name', '').lower() or 
                    search in e.get('device_ip', '').lower() or 
                    search in e.get('port_name', '').lower()
                ]
        except Exception as e:
            print(f"[PORT EVENTS ERROR] {e}")
            events_list = MOCK_PORT_EVENTS

    # Métricas agregadas de resumo
    stp_count = sum(1 for e in events_list if e.get('stp_blocked'))
    flapping_count = sum(1 for e in events_list if e.get('is_flapping'))
    summary = {
        "total": len(events_list),
        "stp_blocked": stp_count,
        "flapping": flapping_count,
        "hours": hours or 24
    }

    if paginate:
        total = len(events_list)
        start = (page - 1) * limit
        end = start + limit
        paginated_events = events_list[start:end]
        return jsonify({
            "events": paginated_events,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
            "summary": summary
        })
    else:
        return jsonify(events_list[:limit])
