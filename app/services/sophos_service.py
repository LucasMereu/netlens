# Sophos Firewall Integration Service (SFOS XML API)
import os
import time
import ssl
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from app.utils.logging import get_logger

logger = get_logger("sophos_service")

class SophosService:
    _cache = {}
    CACHE_TTL = 300  # 5 minutos de cache (instantâneo nas trocas de aba)

    APPLIANCES = [
        {
            "id": "matriz",
            "name": "Sophos Matriz SP (F1)",
            "host": "10.1.1.2",
            "port": "4444",
            "model": "XGS3300_RL01_SFOS",
            "role": "Borda & Datacenter SP",
            "location": "São Paulo - HQ"
        },
        {
            "id": "brasilia",
            "name": "Sophos Brasília (F2)",
            "host": "10.61.0.250",
            "port": "4444",
            "model": "SFOS Appliance",
            "role": "Sucursal & Links Brasília",
            "location": "Brasília - DF"
        },
        {
            "id": "str",
            "name": "Sophos STR (F3)",
            "host": "10.11.0.253",
            "port": "4444",
            "model": "XGS2100_RL01_SFOS",
            "role": "Firewall Segmento STR",
            "location": "São Paulo - STR"
        }
    ]

    @classmethod
    def get_appliances(cls) -> list:
        try:
            from app.services.config_service import ConfigService
            cfg = ConfigService.load_config()
            fws = cfg.get("firewalls")
            if fws and isinstance(fws, list):
                return fws
        except Exception as e:
            logger.warning(f"Erro ao carregar firewalls de config.json: {e}")
        return [
            {
                "id": "fw-matriz-sp",
                "name": "Sophos Matriz SP (F1)",
                "host": "10.1.1.2",
                "port": "4444",
                "city": "São Paulo",
                "role": "Borda & Datacenter SP",
                "location": "São Paulo - HQ",
                "user": "netlens_api",
                "password": "@NetLensSecurePass2026!",
                "use_default_auth": True,
                "enabled": True
            },
            {
                "id": "fw-brasilia",
                "name": "Sophos Brasília (F2)",
                "host": "10.61.0.250",
                "port": "4444",
                "city": "Brasília",
                "role": "Sucursal & Links Brasília",
                "location": "Brasília - DF",
                "user": "netlens_api",
                "password": "@NetLensSecurePass2026!",
                "use_default_auth": True,
                "enabled": True
            },
            {
                "id": "fw-praca-10-65",
                "name": "Sophos Praça 10.65 (F4)",
                "host": "10.65.0.250",
                "port": "4444",
                "city": "Praça 10.65",
                "role": "Sucursal & Gateway Remoto",
                "location": "Praça Remota",
                "user": "netlens_api",
                "password": "@NetLensSecurePass2026!",
                "use_default_auth": True,
                "enabled": True
            },
            {
                "id": "fw-str",
                "name": "Sophos STR (F3)",
                "host": "10.11.0.253",
                "port": "4444",
                "city": "São Paulo - STR",
                "role": "Firewall Segmento STR",
                "location": "São Paulo - STR",
                "user": "netlens_api",
                "password": "@NetLensSecurePass2026!",
                "use_default_auth": True,
                "enabled": True
            }
        ]

    @classmethod
    def _get_api_credentials(cls, host: str = None):
        default_user = os.environ.get("SOPHOS_API_USER", "netlens_api")
        default_pass = os.environ.get("SOPHOS_API_PASS", "@NetLensSecurePass2026!")
        default_host = os.environ.get("SOPHOS_API_HOST", "10.1.1.2")
        default_port = os.environ.get("SOPHOS_API_PORT", "4444")

        target_host = host or default_host
        target_port = default_port
        target_user = default_user
        target_pass = default_pass

        # Buscar configurações específicas do appliance
        appliances = cls.get_appliances()
        for app in appliances:
            if app.get("host") == target_host or app.get("id") == target_host:
                target_host = app.get("host", target_host)
                target_port = str(app.get("port") or target_port)
                if not app.get("use_default_auth", True):
                    target_user = app.get("user") or target_user
                    target_pass = app.get("password") or target_pass
                break

        return target_host, target_port, target_user, target_pass

    @classmethod
    def _make_request(cls, xml_body: str, host: str = None, timeout: int = 25) -> str:
        target_host, port, user, password = cls._get_api_credentials(host)

        full_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Request>
  <Login>
    <Username>{user}</Username>
    <Password>{password}</Password>
  </Login>
{xml_body}
</Request>"""

        data = urllib.parse.urlencode({"reqxml": full_xml}).encode("utf-8")
        url = f"https://{target_host}:{port}/webconsole/APIController"

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    @classmethod
    def _get_subports_for_host(cls, host: str) -> list:
        subports = []
        try:
            from app.clients import get_librenms_client
            import pymysql.cursors
            ln = get_librenms_client()
            if ln:
                with ln.get_db_connection() as conn:
                    with conn.cursor(pymysql.cursors.DictCursor) as cur:
                        cur.execute("""
                            SELECT p.ifName
                            FROM ports p
                            JOIN devices d ON p.device_id = d.device_id
                            WHERE (d.hostname LIKE %s OR INET6_NTOA(d.ip) = %s)
                              AND INSTR(p.ifName, '.') > 0
                            ORDER BY p.ifName
                        """, (f"%{host}%", host))
                        rows = cur.fetchall()
                        subports = [r["ifName"] for r in rows if r.get("ifName")]
        except Exception as e:
            logger.warning(f"Não foi possível obter subports do LibreNMS para {host}: {e}")

        if not subports and host in (None, "10.1.1.2"):
            subports = [
                "Port2.52", "Port3.111", "Port3.112", "Port3.126",
                "Port7.10", "Port7.151", "Port7.152", "Port7.153",
                "Port8.573", "Port8.574", "Port8.577",
                "PortF4.11", "PortF4.112", "PortF4.126"
            ]
        return subports

    @classmethod
    def get_firewall_overview(cls, force: bool = False, host: str = None) -> dict:
        def_host, _, _, _ = cls._get_api_credentials()
        target_host = host or def_host
        cache_key = f"overview_{target_host}"

        now = time.time()
        if not force and cache_key in cls._cache:
            entry = cls._cache[cache_key]
            if now - entry["timestamp"] < cls.CACHE_TTL:
                return entry["data"]

        try:
            subports = cls._get_subports_for_host(target_host)
            vlan_filters = "".join([f'<VLAN><Filter><key name="Hardware" criteria="=">{p}</key></Filter></VLAN>' for p in subports])

            xml_query = f"""  <Get>
    <Interface/>
    <FirewallRule/>
    <IPHostGroup/>
    {vlan_filters}
  </Get>"""
            raw_resp = cls._make_request(xml_query, host=target_host)
            root = ET.fromstring(raw_resp)

            # 1. Status de Login
            login_status = root.findtext(".//Login/status", default="Failed")
            if login_status and "successful" not in login_status.lower() and "ok" not in login_status.lower() and login_status != "200":
                logger.warning(f"Falha de autenticação Sophos API ({target_host}): {login_status}")
                return {
                    "success": False,
                    "host": target_host,
                    "error": f"Falha de autenticação no Sophos: {login_status}",
                    "auth_status": login_status,
                    "stats": {
                        "interfaces_total": 0, "interfaces_up": 0, "interfaces_physical": 0, "interfaces_vlans": 0,
                        "rules_total": 0, "rules_enabled": 0, "rules_disabled": 0,
                        "rules_drop": 0, "rules_accept": 0, "host_groups_total": 0
                    },
                    "interfaces": [], "rules": [], "host_groups": [],
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }

            # 2. Interfaces de Rede (Físicas e Virtuais / VLANs)
            interfaces = []
            # 2a. Portas Físicas
            for iface in root.findall(".//Interface"):
                name = (iface.findtext("Name", default="") or "").strip()
                hw = (iface.findtext("Hardware", default="") or "").strip()
                
                # Ignora tags filhas órfãs de <VLAN> que não possuem Name/Hardware raiz
                if not name and not hw:
                    continue

                ip = (iface.findtext("IPAddress", default="") or "").strip()
                netmask = (iface.findtext("Netmask", default="") or "").strip()
                status = (iface.findtext("InterfaceStatus", default="OFF") or "").strip()
                zone = (iface.findtext("NetworkZone", default="") or "").strip()
                detail_status = (iface.findtext("Status", default="") or "").strip()
                is_admin_on = status.upper() == "ON"
                
                # Classificação precisa do estado real do link
                if "disabled" in detail_status.lower() or not is_admin_on:
                    real_status = "DISABLED"
                    status_label = "DESABILITADA"
                    is_up = False
                elif "unplugged" in detail_status.lower() or "disconnected" in detail_status.lower():
                    real_status = "DOWN"
                    status_label = "DESCONECTADA"
                    is_up = False
                elif "connected" in detail_status.lower() or is_admin_on:
                    real_status = "UP"
                    status_label = "UP"
                    is_up = True
                else:
                    real_status = "DOWN"
                    status_label = "DOWN"
                    is_up = False

                interfaces.append({
                    "name": name,
                    "hardware": hw or name,
                    "ip": ip,
                    "netmask": netmask,
                    "zone": zone,
                    "status": real_status,
                    "status_label": status_label,
                    "status_detail": detail_status,
                    "is_connected": is_up,
                    "type": "physical",
                    "vlan_id": None,
                    "parent_interface": None,
                    "gateway_name": "",
                    "gateway_address": ""
                })

            # 2b. Interfaces Virtuais (VLANs)
            for v in root.findall(".//VLAN"):
                v_name = v.findtext("Name", default="")
                v_hw = v.findtext("Hardware", default="")
                if not v_hw or not v_name:
                    continue
                v_ip = v.findtext("IPAddress", default="")
                v_netmask = v.findtext("Netmask", default="")
                v_zone = v.findtext("Zone", default="WAN")
                v_id = v.findtext("VLANID", default="")
                v_status = v.findtext("InterfaceStatus", default="OFF")
                v_detail = v.findtext("Status", default="").strip()
                v_parent = v.findtext("Interface", default="")
                v_gw_name = v.findtext("GatewayName", default="")
                v_gw_addr = v.findtext("GatewayAddress", default="")

                is_admin_on = v_status.upper() == "ON"
                if "disabled" in v_detail.lower() or not is_admin_on:
                    real_status = "DISABLED"
                    status_label = "DESABILITADA"
                    is_up = False
                elif "unplugged" in v_detail.lower() or "disconnected" in v_detail.lower():
                    real_status = "DOWN"
                    status_label = "DESCONECTADA"
                    is_up = False
                elif "connected" in v_detail.lower() or is_admin_on:
                    real_status = "UP"
                    status_label = "UP"
                    is_up = True
                else:
                    real_status = "DOWN"
                    status_label = "DOWN"
                    is_up = False

                interfaces.append({
                    "name": v_name,
                    "hardware": v_hw,
                    "ip": v_ip,
                    "netmask": v_netmask,
                    "zone": v_zone,
                    "status": real_status,
                    "status_label": status_label,
                    "status_detail": v_detail,
                    "is_connected": is_up,
                    "type": "vlan",
                    "vlan_id": v_id,
                    "parent_interface": v_parent,
                    "gateway_name": v_gw_name,
                    "gateway_address": v_gw_addr
                })

            # 3. Regras de Firewall
            rules = []
            rules_enabled = 0
            rules_disabled = 0
            rules_drop = 0
            rules_accept = 0

            for r in root.findall(".//FirewallRule"):
                r_name = r.findtext("Name", default="")
                r_status = r.findtext("Status", default="Enable")
                is_enabled = r_status.lower() == "enable"

                policy = r.find("NetworkPolicy")
                action = "Accept"
                src_zones = []
                dst_zones = []
                src_nets = []
                dst_nets = []

                if policy is not None:
                    action = policy.findtext("Action", default="Accept")
                    for z in policy.findall(".//SourceZones/Zone"):
                        if z.text: src_zones.append(z.text)
                    for z in policy.findall(".//DestinationZones/Zone"):
                        if z.text: dst_zones.append(z.text)
                    for n in policy.findall(".//SourceNetworks/Network"):
                        if n.text: src_nets.append(n.text)
                    for n in policy.findall(".//DestinationNetworks/Network"):
                        if n.text: dst_nets.append(n.text)

                if is_enabled:
                    rules_enabled += 1
                else:
                    rules_disabled += 1

                if action.lower() == "drop" or action.lower() == "reject":
                    rules_drop += 1
                else:
                    rules_accept += 1

                rules.append({
                    "name": r_name,
                    "status": "ENABLED" if is_enabled else "DISABLED",
                    "action": action.upper(),
                    "source_zones": src_zones,
                    "destination_zones": dst_zones,
                    "source_networks": src_nets[:3],
                    "destination_networks": dst_nets[:3]
                })

            # 4. Grupos de Host / Blacklists de Bloqueio
            host_groups = []
            for g in root.findall(".//IPHostGroup"):
                g_name = g.findtext("Name", default="")
                g_desc = g.findtext("Description", default="")
                host_list = [h.text for h in g.findall(".//HostList/Host") if h.text]
                host_groups.append({
                    "name": g_name,
                    "description": g_desc,
                    "hosts_count": len(host_list),
                    "hosts_sample": host_list[:5]
                })

            total_ifaces = len(interfaces)
            physical_ifaces = len([i for i in interfaces if i.get("type") == "physical"])
            vlan_ifaces = len([i for i in interfaces if i.get("type") == "vlan"])
            up_ifaces = len([i for i in interfaces if i["status"] == "UP"])
            disabled_ifaces = len([i for i in interfaces if i["status"] == "DISABLED"])
            down_ifaces = len([i for i in interfaces if i["status"] == "DOWN"])

            result = {
                "success": True,
                "host": target_host,
                "api_version": root.attrib.get("APIVersion", "SFOS"),
                "auth_status": login_status,
                "stats": {
                    "interfaces_total": total_ifaces,
                    "interfaces_physical": physical_ifaces,
                    "interfaces_vlans": vlan_ifaces,
                    "interfaces_up": up_ifaces,
                    "interfaces_disabled": disabled_ifaces,
                    "interfaces_down": down_ifaces,
                    "rules_total": len(rules),
                    "rules_enabled": rules_enabled,
                    "rules_disabled": rules_disabled,
                    "rules_drop": rules_drop,
                    "rules_accept": rules_accept,
                    "host_groups_total": len(host_groups)
                },
                "interfaces": interfaces,
                "rules": rules,
                "host_groups": host_groups,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            cls._cache[cache_key] = {
                "timestamp": now,
                "data": result
            }
            return result

        except Exception as e:
            logger.error(f"Erro ao consultar API do Sophos ({target_host}): {e}")
            return {
                "success": False,
                "host": target_host,
                "error": str(e),
                "auth_status": "Failed",
                "stats": {
                    "interfaces_total": 0,
                    "interfaces_up": 0,
                    "rules_total": 0,
                    "rules_enabled": 0,
                    "rules_disabled": 0,
                    "rules_drop": 0,
                    "rules_accept": 0,
                    "host_groups_total": 0
                },
                "interfaces": [],
                "rules": [],
                "host_groups": [],
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }

    @classmethod
    def get_all_interfaces_for_selection(cls, host: str = None) -> list:
        overview = cls.get_firewall_overview(host=host)
        ifaces = overview.get("interfaces", []) if overview.get("success", False) else []
        result = []
        for i in ifaces:
            hw = (i.get("hardware") or i.get("name") or "").strip()
            nm = (i.get("name") or "").strip()
            if not hw and not nm:
                continue
            ip = i.get("ip")
            zn = i.get("zone", "")
            itype = i.get("type", "physical")
            st = i.get("status_label", "DOWN")
            gw = i.get("gateway_address", "")
            
            if itype == "vlan":
                label = f"{hw} — {nm} (VLAN {i.get('vlan_id', '')} | {zn}{' - ' + ip if ip else ''})"
            else:
                label = f"{hw} — {nm} ({zn}{' - ' + ip if ip else ''})"
                
            result.append({
                "id": hw,
                "name": nm,
                "hardware": hw,
                "zone": zn,
                "ip": ip,
                "gateway": gw,
                "type": itype,
                "vlan_id": i.get("vlan_id"),
                "status": i.get("status"),
                "status_label": st,
                "display_label": label
            })

        # Adicionar Interfaces de Túnel e VPN via LibreNMS (ex: ipsec0, tun0, tun1, gre0)
        try:
            from app.clients import get_librenms_client
            import pymysql.cursors
            ln = get_librenms_client()
            if ln:
                target_h = host or "10.1.1.2"
                with ln.get_db_connection() as conn:
                    with conn.cursor(pymysql.cursors.DictCursor) as cur:
                        cur.execute("""
                            SELECT p.ifName, p.ifDescr, p.ifAlias, p.ifType, p.ifOperStatus,
                                   a.ipv4_address, a.ipv4_prefixlen
                            FROM ports p
                            JOIN devices d ON p.device_id = d.device_id
                            LEFT JOIN ipv4_addresses a ON p.port_id = a.port_id
                            WHERE (d.hostname LIKE %s OR INET6_NTOA(d.ip) = %s)
                              AND (p.ifName LIKE 'tun%%' OR p.ifName LIKE 'ipsec%%' OR p.ifName LIKE 'xfrm%%' OR p.ifType = 'tunnel')
                            ORDER BY p.ifName
                        """, (f"%{target_h}%", target_h))
                        tunnels = cur.fetchall()
                        for t in tunnels:
                            if_name = t.get("ifName")
                            if not if_name:
                                continue
                            ip_addr = t.get("ipv4_address") or ""
                            oper_st = (t.get("ifOperStatus") or "down").upper()
                            label = f"{if_name} — Túnel VPN ({oper_st}{' - ' + ip_addr if ip_addr else ''})"
                            result.append({
                                "id": if_name,
                                "name": if_name,
                                "hardware": if_name,
                                "zone": "VPN",
                                "ip": ip_addr,
                                "gateway": "",
                                "type": "tunnel",
                                "vlan_id": None,
                                "status": oper_st,
                                "status_label": oper_st,
                                "display_label": label
                            })
        except Exception as e:
            logger.warning(f"Não foi possível consultar interfaces de túnel no LibreNMS para {host}: {e}")

        # Adicionar VPNs Site-to-Site IPsec (Baseadas em políticas) diretamente da API do Sophos
        try:
            vpn_xml = cls._make_request("<Get><VPNIPSecConnection/></Get>", host=host, timeout=10)
            if vpn_xml and "<VPNIPSecConnection" in vpn_xml and "code=\"529\"" not in vpn_xml:
                import xml.etree.ElementTree as ET
                import re
                v_root = ET.fromstring(vpn_xml)
                v_conns = v_root.findall(".//VPNIPSecConnection/Configuration")
                for cfg in v_conns:
                    v_name = (cfg.findtext("Name") or "").strip()
                    if not v_name:
                        continue
                    v_status = (cfg.findtext("Status") or "Active").strip()
                    v_type = cfg.findtext("ConnectionType") or "SiteToSite"
                    v_local_wan = cfg.findtext("LocalWANPort") or cfg.findtext("AliasLocalWANPort") or ""
                    v_remote_host = (cfg.findtext("RemoteHost") or "*").strip()
                    v_local_id = (cfg.findtext("LocalID") or "").strip()
                    v_desc = (cfg.findtext("Description") or "").strip()

                    # Sub-redes remotas
                    v_remote_nets = [n.text.strip() for n in cfg.findall(".//RemoteNetwork/Network") if n.text]
                    remote_summary = ", ".join(v_remote_nets) if v_remote_nets else v_remote_host

                    # Determinar IP de teste sugerido (ex: Brasília 10.61.0.250)
                    suggested_target_ip = ""
                    if "10.61.0" in remote_summary or "BSB" in v_name.upper():
                        suggested_target_ip = "10.61.0.250"
                    elif v_remote_host and v_remote_host != "*":
                        suggested_target_ip = v_remote_host
                    elif v_remote_nets:
                        m = re.search(r"(\d+\.\d+\.\d+\.\d+)", v_remote_nets[0])
                        if m:
                            ip_found = m.group(1)
                            suggested_target_ip = ip_found[:-1] + "1" if ip_found.endswith(".0") else ip_found

                    is_active = str(v_status).lower() in ("active", "1", "12", "enable", "enabled")
                    st_label = "ATIVA" if is_active else str(v_status)
                    wan_info = f" | Saída: {v_local_wan}" if v_local_wan else ""
                    dest_info = f" -> {remote_summary}" if remote_summary and remote_summary != "*" else ""
                    label = f"{v_name} — VPN Site a Site ({st_label}{wan_info}{dest_info})"

                    result.append({
                        "id": v_name,
                        "name": v_name,
                        "hardware": v_name,
                        "zone": "VPN_SiteToSite",
                        "ip": v_local_id,
                        "gateway": suggested_target_ip,
                        "type": "vpn_site_to_site",
                        "vlan_id": None,
                        "status": "UP" if is_active else "DOWN",
                        "status_label": st_label,
                        "display_label": label,
                        "local_wan": v_local_wan,
                        "remote_host": v_remote_host,
                        "remote_networks": v_remote_nets,
                        "description": v_desc
                    })
        except Exception as e:
            logger.warning(f"Não foi possível consultar VPNIPSecConnection para {host}: {e}")

        return result


