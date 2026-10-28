import time
from app.clients import get_netdisco_client, get_librenms_client, is_mock_mode
from app.analysis.vlan_auditor import VlanAuditor

class VlanService:
    _vlan_auditor = None
    _vlans_cache = {
        "data": None,
        "timestamp": 0
    }
    CACHE_TIMEOUT = 300 # 5 minutes

    @classmethod
    def get_auditor(cls):
        if cls._vlan_auditor is None and not is_mock_mode():
            nd = get_netdisco_client()
            ln = get_librenms_client()
            if nd:
                cls._vlan_auditor = VlanAuditor(nd, ln)
        return cls._vlan_auditor

    @classmethod
    def audit_vlans(cls, force_refresh=False):
        if is_mock_mode() or cls.get_auditor() is None:
            # Return static mock data as fallback
            from app.routes.vlans import MOCK_VLANS
            return MOCK_VLANS

        now = time.time()
        if not force_refresh and cls._vlans_cache["data"] is not None and (now - cls._vlans_cache["timestamp"] < cls.CACHE_TIMEOUT):
            return cls._vlans_cache["data"]

        auditor = cls.get_auditor()
        data = auditor.audit_vlans()
        cls._vlans_cache["data"] = data
        cls._vlans_cache["timestamp"] = now
        return data

    @classmethod
    def validate_link(cls, device_a: str, device_b: str):
        if is_mock_mode():
            time.sleep(2)
            return {"success": True, "resolved": True, "message": "Link validado (Simulacao: Alinhado!)"}

        nd = get_netdisco_client()
        if not nd:
            raise Exception("Netdisco client nao inicializado.")

        # 1. Envia jobs de discover no Netdisco
        for dev in [device_a, device_b]:
            try:
                nd._request("POST", "queue/jobs", json_data=[{"device": dev, "action": "discover"}])
            except Exception as e:
                print(f"[VLAN VALIDATION] Erro ao agendar discover para {dev}: {e}")

        # 2. Busca os job IDs criados recentemente na fila
        time.sleep(1)
        job_ids = {}
        try:
            queue = nd._request("GET", "queue/jobs")
            for j in queue:
                dev = j.get("device")
                action = j.get("action")
                status = j.get("status")
                job_id = j.get("job")
                if dev in [device_a, device_b] and action == "discover" and status in ["queued", "running", "done"]:
                    if dev not in job_ids:
                        job_ids[dev] = job_id
        except Exception as e:
            print(f"[VLAN VALIDATION] Erro ao ler fila para mapear job IDs: {e}")

        # 3. Aguarda a finalizacao dos jobs (maximo 30 segundos)
        start_time = time.time()
        completed = False
        while time.time() - start_time < 30:
            time.sleep(3)
            all_done = True
            try:
                queue = nd._request("GET", "queue/jobs")
                jobs_dict = {j.get("job"): j for j in queue if j.get("job")}
                for dev, jid in job_ids.items():
                    if jid in jobs_dict:
                        status = jobs_dict[jid].get("status")
                        if status not in ["done", "error", "failed"]:
                            all_done = False
                            break
            except Exception as e:
                print(f"[VLAN VALIDATION] Erro ao checar status dos jobs: {e}")
                all_done = False

            if all_done:
                completed = True
                break

        auditor = cls.get_auditor()
        if auditor:
            # Limpa cache do auditor para estes dispositivos
            auditor._device_ports_cache.pop(device_a, None)
            auditor._device_ports_cache.pop(device_b, None)

            mismatches = cls.audit_vlans(force_refresh=True)
            still_has_mismatch = False
            matching_mismatch = None
            for m in mismatches:
                if (m.get("device_a") == device_a and m.get("device_b") == device_b) or \
                   (m.get("device_a") == device_b and m.get("device_b") == device_a):
                    still_has_mismatch = True
                    matching_mismatch = m
                    break

            if not still_has_mismatch:
                return {
                    "success": True, 
                    "resolved": True, 
                    "message": "Divergencia resolvida! Ambas as interfaces estao configuradas de forma identica."
                }
            else:
                return {
                    "success": True, 
                    "resolved": False, 
                    "message": f"Divergencia ainda persiste: {matching_mismatch.get('description')}"
                }
        else:
            raise Exception("VlanAuditor nao inicializado.")
