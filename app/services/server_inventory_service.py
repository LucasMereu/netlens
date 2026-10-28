# NetLens Server Inventory Service
# Queries hardware specs (CPU, Memory, Disks) from LibreNMS database AND Zabbix API
# Provides unified server inventory across Proxmox, TrueNAS, Linux, Windows, macOS, etc.
import logging
import socket
import time
import json
import re
from typing import Dict, List, Any, Optional
from app.clients import get_librenms_client, get_zabbix_client

logger = logging.getLogger('netlens.server_inventory')

class ServerInventoryService:
    _cached_data = None
    _last_fetch = 0
    _CACHE_TTL = 30  # 30 seconds cache for snappy responsiveness

    @staticmethod
    def _decode_ip(raw_ip) -> str:
        if isinstance(raw_ip, bytes) and len(raw_ip) == 4:
            try:
                return socket.inet_ntoa(raw_ip)
            except Exception:
                return str(raw_ip)
        return str(raw_ip) if raw_ip is not None else ''

    @staticmethod
    def _format_bytes(num_bytes: Optional[float]) -> str:
        if num_bytes is None or num_bytes <= 0:
            return '0 B'
        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
        idx = 0
        val = float(num_bytes)
        while val >= 1024.0 and idx < len(units) - 1:
            val /= 1024.0
            idx += 1
        return f'{val:.1f} {units[idx]}'

    @staticmethod
    def _format_uptime(uptime_seconds: Optional[int]) -> str:
        if not uptime_seconds or uptime_seconds <= 0:
            return 'N/A'
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        parts = []
        if days > 0:
            parts.append(f'{days}d')
        if hours > 0 or days > 0:
            parts.append(f'{hours}h')
        parts.append(f'{minutes}m')
        return ' '.join(parts)

    @classmethod
    def get_server_inventory(cls, force_refresh: bool = False) -> Dict[str, Any]:
        now = time.time()
        if not force_refresh and cls._cached_data and (now - cls._last_fetch < cls._CACHE_TTL):
            return cls._cached_data

        client = get_librenms_client()
        if not client:
            return cls._cached_data or cls._empty_response('Cliente LibreNMS não inicializado')

        conn = client.get_db_connection()
        if not conn:
            logger.error('LibreNMS DB connection not available for server inventory')
            return cls._cached_data or cls._empty_response('Conexão com banco LibreNMS indisponível')

        try:
            import pymysql.cursors
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            # 1. Fetch servers & storages (including TrueNAS, FreeNAS, PowerVault, etc.)
            query_devices = (
                "SELECT device_id, hostname, sysName, ip, os, version, hardware, status, status_reason, "
                "       last_ping, last_ping_timetaken, uptime, purpose, type "
                "FROM devices "
                "WHERE os IN ('windows', 'linux', 'proxmox', 'freebsd', 'esxi', 'vmware', "
                "             'truenas', 'truenas-scale', 'freenas', 'powervault', 'qnap', 'synology') "
                "   OR type IN ('server', 'storage') "
                "   OR hostname LIKE '%truenas%' OR sysName LIKE '%truenas%' "
                "ORDER BY hostname ASC"
            )
            cursor.execute(query_devices)
            device_rows = cursor.fetchall()

            device_ids = [r['device_id'] for r in device_rows] if device_rows else []
            proc_by_device: Dict[int, List[Dict[str, Any]]] = {}
            mem_by_device: Dict[int, List[Dict[str, Any]]] = {}
            storage_by_device: Dict[int, List[Dict[str, Any]]] = {}

            if device_ids:
                placeholders = ','.join(['%s'] * len(device_ids))

                # Processors
                query_proc = (
                    f"SELECT device_id, processor_descr, processor_usage "
                    f"FROM processors "
                    f"WHERE device_id IN ({placeholders})"
                )
                cursor.execute(query_proc, device_ids)
                for p in cursor.fetchall():
                    proc_by_device.setdefault(p['device_id'], []).append(p)

                # Memory pools
                query_mem = (
                    f"SELECT device_id, mempool_descr, mempool_perc, mempool_total, mempool_used, mempool_free "
                    f"FROM mempools "
                    f"WHERE device_id IN ({placeholders})"
                )
                cursor.execute(query_mem, device_ids)
                for m in cursor.fetchall():
                    mem_by_device.setdefault(m['device_id'], []).append(m)

                # Storage / Disks
                query_storage = (
                    f"SELECT device_id, storage_descr, storage_size, storage_used, storage_free, storage_perc "
                    f"FROM storage "
                    f"WHERE device_id IN ({placeholders})"
                )
                cursor.execute(query_storage, device_ids)
                for s in cursor.fetchall():
                    storage_by_device.setdefault(s['device_id'], []).append(s)

            servers = []
            known_ips = set()
            known_hostnames = set()

            for dev in device_rows:
                dev_id = dev['device_id']
                ip_clean = cls._decode_ip(dev['ip'])
                if ip_clean:
                    known_ips.add(ip_clean)
                if dev['hostname']:
                    known_hostnames.add(dev['hostname'].strip().lower())
                if dev['sysName']:
                    known_hostnames.add(dev['sysName'].strip().lower())

                # Status check: If status == 0 but status_reason == 'snmp' and last_ping was successful, device is reachable/online!
                # Only if reason is 'icmp' and ping fails is it truly offline.
                is_online = (dev['status'] == 1)
                if not is_online:
                    last_ping_time = dev.get('last_ping_timetaken')
                    status_reason = (dev.get('status_reason') or '').lower()
                    if status_reason == 'snmp' and last_ping_time is not None and float(last_ping_time) > 0:
                        is_online = True  # Host is responding to ping, only SNMP timeout occurred

                raw_os = (dev['os'] or 'outro').lower()

                # CPU aggregation
                dev_procs = proc_by_device.get(dev_id, [])
                cpu_cores = len(dev_procs)
                if dev_procs:
                    usages = [float(p['processor_usage'] or 0) for p in dev_procs]
                    cpu_usage_avg = round(sum(usages) / len(usages), 1) if usages else 0
                    cpu_model = dev_procs[0]['processor_descr'] or 'Processador Genérico'
                else:
                    cpu_usage_avg = 0
                    cpu_model = dev['hardware'] or 'Desconhecido'

                # Memory aggregation
                dev_mems = mem_by_device.get(dev_id, [])
                ram_total = 0
                ram_used = 0
                ram_perc = 0
                if dev_mems:
                    phys_mem = next((m for m in dev_mems if 'physical' in (m['mempool_descr'] or '').lower() or 'ram' in (m['mempool_descr'] or '').lower()), None)
                    if not phys_mem:
                        phys_mem = max(dev_mems, key=lambda x: float(x['mempool_total'] or 0))

                    ram_total = float(phys_mem['mempool_total'] or 0)
                    ram_used = float(phys_mem['mempool_used'] or 0)
                    ram_free = float(phys_mem['mempool_free'] or (ram_total - ram_used))
                    ram_perc = round(float(phys_mem['mempool_perc'] or (0 if ram_total == 0 else (ram_used / ram_total * 100))), 1)
                else:
                    ram_free = 0

                # Storage / Partitions aggregation
                dev_storage = storage_by_device.get(dev_id, [])
                disks = []
                dev_total_storage = 0
                dev_used_storage = 0

                for st in dev_storage:
                    st_descr = st['storage_descr'] or 'Disco'
                    lower_d = st_descr.lower()
                    if 'memory' in lower_d or 'swap' in lower_d or 'virtual' in lower_d:
                        continue

                    st_size = float(st['storage_size'] or 0)
                    st_used = float(st['storage_used'] or 0)
                    st_free = float(st['storage_free'] or (st_size - st_used))
                    st_perc = round(float(st['storage_perc'] or (0 if st_size == 0 else (st_used / st_size * 100))), 1)

                    dev_total_storage += st_size
                    dev_used_storage += st_used

                    disks.append({
                        'mount': st_descr,
                        'total_bytes': st_size,
                        'total_formatted': cls._format_bytes(st_size),
                        'used_bytes': st_used,
                        'used_formatted': cls._format_bytes(st_used),
                        'free_bytes': st_free,
                        'free_formatted': cls._format_bytes(st_free),
                        'percent': st_perc,
                        'status': 'critical' if st_perc >= 90 else ('warning' if st_perc >= 80 else 'normal')
                    })

                server_item = {
                    'id': dev_id,
                    'source': 'librenms',
                    'hostname': dev['hostname'],
                    'sys_name': dev['sysName'] or dev['hostname'],
                    'ip': ip_clean,
                    'os': dev['os'] or 'outro',
                    'os_version': dev['version'] or '',
                    'hardware': dev['hardware'] or '',
                    'status': 'online' if is_online else 'offline',
                    'status_reason': dev['status_reason'] or '',
                    'uptime_raw': dev['uptime'],
                    'uptime_formatted': cls._format_uptime(dev['uptime']),
                    'purpose': dev['purpose'] or '',
                    'cpu': {
                        'model': cpu_model,
                        'cores': cpu_cores,
                        'percent': cpu_usage_avg,
                        'status': 'critical' if cpu_usage_avg >= 90 else ('warning' if cpu_usage_avg >= 75 else 'normal')
                    },
                    'memory': {
                        'total_bytes': ram_total,
                        'total_formatted': cls._format_bytes(ram_total),
                        'used_bytes': ram_used,
                        'used_formatted': cls._format_bytes(ram_used),
                        'free_bytes': ram_free,
                        'free_formatted': cls._format_bytes(ram_free),
                        'percent': ram_perc,
                        'status': 'critical' if ram_perc >= 90 else ('warning' if ram_perc >= 80 else 'normal')
                    },
                    'storage': {
                        'total_bytes': dev_total_storage,
                        'total_formatted': cls._format_bytes(dev_total_storage),
                        'used_bytes': dev_used_storage,
                        'used_formatted': cls._format_bytes(dev_used_storage),
                        'percent': round(0 if dev_total_storage == 0 else (dev_used_storage / dev_total_storage * 100), 1),
                        'partitions': disks
                    }
                }
                servers.append(server_item)

            # 2. Enrich with Zabbix servers that are not present in LibreNMS (e.g. 10.65.0.25, 26, 27)
            zb_client = get_zabbix_client()
            if zb_client:
                try:
                    server_group_ids = ['33', '4', '32', '23', '27', '70', '71', '2', '58']
                    zb_hosts = zb_client._request_api("host.get", {
                        "groupids": server_group_ids,
                        "output": ["hostid", "host", "name", "status"],
                        "selectInterfaces": ["interfaceid", "ip", "type", "main", "port", "available", "error"],
                        "selectGroups": ["groupid", "name"],
                        "filter": {"status": 0}
                    })

                    zb_eligible = []
                    seen_zb_ips = set()

                    for zh in zb_hosts:
                        zh_name = zh.get('name', '').strip()
                        # Skip OLD or test hosts
                        if 'OLD' in zh_name.upper() or 'TESTE' in zh_name.upper():
                            continue

                        interfaces = zh.get('interfaces', [])
                        valid_ips = [ifc.get('ip') for ifc in interfaces if ifc.get('ip') and ifc.get('ip') != '127.0.0.1']
                        if not valid_ips:
                            continue

                        primary_ip = valid_ips[0]
                        # Check if already present from LibreNMS or duplicate in Zabbix
                        if primary_ip in known_ips or primary_ip in seen_zb_ips:
                            continue

                        seen_zb_ips.add(primary_ip)
                        zb_eligible.append((zh, primary_ip))

                    if zb_eligible:
                        # Query items in chunks of 15 to avoid Zabbix API timeout
                        for i in range(0, len(zb_eligible), 15):
                            chunk = zb_eligible[i:i+15]
                            chunk_hids = [zh['hostid'] for zh, _ in chunk]
                            try:
                                zb_items = zb_client._request_api("item.get", {
                                    "hostids": chunk_hids,
                                    "output": ["hostid", "name", "key_", "lastvalue", "units"],
                                    "search": {
                                        "key_": ["cpu.util", "cpu.num", "memory.size", "vfs.fs", "uptime", "uname", "icmpping"]
                                    },
                                    "searchByAny": True
                                })
                            except Exception as zb_item_err:
                                logger.warning(f"Erro ao buscar itens Zabbix para chunk {chunk_hids}: {zb_item_err}")
                                zb_items = []

                            items_by_hid: Dict[str, List[Dict[str, Any]]] = {}
                            for item in zb_items:
                                items_by_hid.setdefault(item['hostid'], []).append(item)

                            for zh, primary_ip in chunk:
                                hid = zh['hostid']
                                h_items = items_by_hid.get(hid, [])
                                h_groups = [g.get('name', '') for g in zh.get('groups', [])]

                                # Determine OS from groups or uname
                                os_name = 'linux'
                                if any('windows' in g.lower() for g in h_groups):
                                    os_name = 'windows'
                                elif any('truenas' in g.lower() for g in h_groups):
                                    os_name = 'truenas'
                                elif any('macos' in g.lower() for g in h_groups):
                                    os_name = 'macosx'
                                elif any('proxmox' in g.lower() for g in h_groups):
                                    os_name = 'proxmox'

                                cpu_idle = None
                                cpu_cores = 0
                                uname = ''
                                uptime_val = 0
                                ram_total = 0
                                ram_avail = 0
                                is_icmp_online = True
                                disks = []

                                for it in h_items:
                                    k = it.get('key_', '')
                                    val = it.get('lastvalue')
                                    if not val:
                                        continue

                                    if 'icmpping' in k and not 'loss' in k and not 'sec' in k:
                                        try:
                                            is_icmp_online = (int(val) == 1)
                                        except: pass
                                    elif 'system.cpu.util' in k and 'idle' in k:
                                        try: cpu_idle = float(val)
                                        except: pass
                                    elif 'system.cpu.num' in k:
                                        try: cpu_cores = int(val)
                                        except: pass
                                    elif 'system.uname' in k:
                                        uname = str(val)
                                        if 'windows' in uname.lower(): os_name = 'windows'
                                        elif 'darwin' in uname.lower(): os_name = 'macosx'
                                        elif 'pve' in uname.lower() or 'proxmox' in uname.lower(): os_name = 'proxmox'
                                    elif 'system.uptime' in k:
                                        try: uptime_val = int(val)
                                        except: pass
                                    elif 'vm.memory.size[total]' in k:
                                        try: ram_total = float(val)
                                        except: pass
                                    elif 'vm.memory.size[available]' in k:
                                        try: ram_avail = float(val)
                                        except: pass
                                    elif 'vfs.fs.dependent[' in k and 'data' in k:
                                        try:
                                            fs_data = json.loads(val)
                                            bytes_info = fs_data.get('bytes', {})
                                            tot = float(bytes_info.get('total', 0))
                                            used = float(bytes_info.get('used', 0))
                                            perc = round(float(bytes_info.get('pused', 0)), 1)
                                            mount = fs_data.get('fsname', 'Disco')
                                            if not any(d['mount'] == mount for d in disks):
                                                disks.append({
                                                    'mount': mount,
                                                    'total_bytes': tot,
                                                    'total_formatted': cls._format_bytes(tot),
                                                    'used_bytes': used,
                                                    'used_formatted': cls._format_bytes(used),
                                                    'free_bytes': max(0.0, tot - used),
                                                    'free_formatted': cls._format_bytes(max(0.0, tot - used)),
                                                    'percent': perc,
                                                    'status': 'critical' if perc >= 90 else ('warning' if perc >= 80 else 'normal')
                                                })
                                        except: pass
                                    elif 'vfs.fs.size[' in k and 'total' in k:
                                        try:
                                            mount = k.split('[')[1].split(',')[0]
                                            if not any(d['mount'] == mount for d in disks):
                                                tot = float(val)
                                                disks.append({
                                                    'mount': mount,
                                                    'total_bytes': tot,
                                                    'total_formatted': cls._format_bytes(tot),
                                                    'used_bytes': 0.0,
                                                    'used_formatted': '0 B',
                                                    'free_bytes': tot,
                                                    'free_formatted': cls._format_bytes(tot),
                                                    'percent': 0.0,
                                                    'status': 'normal'
                                                })
                                        except: pass
                                    elif 'vfs.fs.size[' in k and 'pused' in k:
                                        try:
                                            mount = k.split('[')[1].split(',')[0]
                                            for d in disks:
                                                if d['mount'] == mount:
                                                    p = round(float(val), 1)
                                                    d['percent'] = p
                                                    d['used_bytes'] = d['total_bytes'] * (p / 100.0)
                                                    d['used_formatted'] = cls._format_bytes(d['used_bytes'])
                                                    d['free_bytes'] = max(0.0, d['total_bytes'] - d['used_bytes'])
                                                    d['free_formatted'] = cls._format_bytes(d['free_bytes'])
                                                    d['status'] = 'critical' if p >= 90 else ('warning' if p >= 80 else 'normal')
                                        except: pass

                                cpu_perc = round(100.0 - cpu_idle, 1) if cpu_idle is not None else 0.0
                                ram_used = max(0.0, ram_total - ram_avail) if (ram_total and ram_avail) else 0.0
                                ram_perc = round((ram_used / ram_total) * 100.0, 1) if ram_total > 0 else 0.0

                                dev_total_st = sum(d['total_bytes'] for d in disks)
                                dev_used_st = sum(d['used_bytes'] for d in disks)
                                dev_st_perc = round((dev_used_st / dev_total_st) * 100.0, 1) if dev_total_st > 0 else 0.0

                                # Clean hostname
                                clean_name = zh.get('name', '')
                                if ' - ' in clean_name:
                                    parts = clean_name.split(' - ')
                                    host_title = parts[1] if len(parts) > 1 else parts[0]
                                else:
                                    host_title = clean_name

                                zb_server = {
                                    'id': f"zb-{hid}",
                                    'source': 'zabbix',
                                    'hostname': host_title,
                                    'sys_name': zh.get('name', ''),
                                    'ip': primary_ip,
                                    'os': os_name,
                                    'os_version': '',
                                    'hardware': f"{cpu_cores} vCPU" if cpu_cores else 'Zabbix Agent/SNMP',
                                    'status': 'online' if is_icmp_online else 'offline',
                                    'status_reason': '',
                                    'uptime_raw': uptime_val,
                                    'uptime_formatted': cls._format_uptime(uptime_val),
                                    'purpose': ', '.join(h_groups[:2]),
                                    'cpu': {
                                        'model': f"{cpu_cores} Cores" if cpu_cores else "Processador Virtual/Físico",
                                        'cores': cpu_cores,
                                        'percent': cpu_perc,
                                        'status': 'critical' if cpu_perc >= 90 else ('warning' if cpu_perc >= 75 else 'normal')
                                    },
                                    'memory': {
                                        'total_bytes': ram_total,
                                        'total_formatted': cls._format_bytes(ram_total),
                                        'used_bytes': ram_used,
                                        'used_formatted': cls._format_bytes(ram_used),
                                        'free_bytes': ram_avail,
                                        'free_formatted': cls._format_bytes(ram_avail),
                                        'percent': ram_perc,
                                        'status': 'critical' if ram_perc >= 90 else ('warning' if ram_perc >= 80 else 'normal')
                                    },
                                    'storage': {
                                        'total_bytes': dev_total_st,
                                        'total_formatted': cls._format_bytes(dev_total_st),
                                        'used_bytes': dev_used_st,
                                        'used_formatted': cls._format_bytes(dev_used_st),
                                        'percent': dev_st_perc,
                                        'partitions': disks
                                    }
                                }
                                servers.append(zb_server)

                except Exception as zb_err:
                    logger.error(f"Erro ao enriquecer inventário com Zabbix: {zb_err}", exc_info=True)

            # Aggregate fleet KPIs
            total_ram_bytes = sum(s['memory']['total_bytes'] for s in servers)
            total_storage_bytes = sum(s['storage']['total_bytes'] for s in servers)
            cpu_servers = [s['cpu']['percent'] for s in servers if s['status'] == 'online' and s['cpu']['percent'] > 0]
            avg_cpu = round(sum(cpu_servers) / len(cpu_servers), 1) if cpu_servers else 0.0

            critical_disks_count = 0
            for s in servers:
                for d in s['storage']['partitions']:
                    if d.get('percent', 0) >= 90:
                        critical_disks_count += 1

            os_counts: Dict[str, int] = {}
            online_count = 0
            for s in servers:
                if s['status'] == 'online':
                    online_count += 1
                o = (s.get('os') or 'outro').lower()
                os_counts[o] = os_counts.get(o, 0) + 1

            result = {
                'success': True,
                'summary': {
                    'total_servers': len(servers),
                    'online_servers': online_count,
                    'offline_servers': len(servers) - online_count,
                    'total_ram_bytes': total_ram_bytes,
                    'total_ram_formatted': cls._format_bytes(total_ram_bytes),
                    'total_storage_bytes': total_storage_bytes,
                    'total_storage_formatted': cls._format_bytes(total_storage_bytes),
                    'avg_cpu_percent': avg_cpu,
                    'critical_disks_count': critical_disks_count,
                    'os_counts': os_counts
                },
                'servers': sorted(servers, key=lambda x: x['hostname'].lower()),
                'cached_at': now
            }

            cls._cached_data = result
            cls._last_fetch = now
            return result

        except Exception as e:
            logger.error(f'Erro ao processar inventario de servidores: {e}', exc_info=True)
            return cls._cached_data or cls._empty_response(str(e))
        finally:
            if conn:
                conn.close()

    @classmethod
    def _empty_response(cls, error_msg: str) -> Dict[str, Any]:
        return {
            'success': False,
            'error': error_msg,
            'servers': [],
            'summary': {
                'total_servers': 0,
                'online_servers': 0,
                'offline_servers': 0,
                'total_ram_bytes': 0,
                'total_ram_formatted': '0 GB',
                'total_storage_bytes': 0,
                'total_storage_formatted': '0 GB',
                'avg_cpu_percent': 0,
                'critical_disks_count': 0,
                'os_counts': {}
            }
        }

    _category_cache = {}
    _category_last_fetch = {}

    @classmethod
    def get_category_inventory(cls, category: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Retorna inventário categorizado para:
        - 'switches' (Switches Core, Acesso, Distribuição)
        - 'firewalls' (Firewalls Sophos, Fortigate, etc.)
        - 'wifi-controllers' (Controladoras Wi-Fi Ruckus ZoneDirector, etc.)
        - 'wifi-aps' (Bases Wi-Fi / Access Points Ruckus, etc.)
        """
        category = category.lower().strip()
        now = time.time()
        last_fetch = cls._category_last_fetch.get(category, 0)

        if not force_refresh and category in cls._category_cache and (now - last_fetch < cls._CACHE_TTL):
            return cls._category_cache[category]

        client = get_librenms_client()
        if not client:
            return cls._empty_category_response(category, 'Cliente LibreNMS não inicializado')

        conn = client.get_db_connection()
        if not conn:
            return cls._empty_category_response(category, 'Conexão com banco LibreNMS indisponível')

        try:
            import pymysql.cursors
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            if category == 'switches':
                sql = """
                    SELECT device_id, hostname, sysName, ip, hardware, os, version, status, status_reason, 
                           last_ping, last_ping_timetaken, uptime, purpose, type
                    FROM devices
                    WHERE type = 'network' 
                       OR os IN ('3com', 'comware', 'procurve', 'dnos', 'edgeswitch', 'cisco', 'routeros')
                    ORDER BY hostname ASC
                """
                cat_label = "Switches de Rede"
            elif category == 'firewalls':
                sql = """
                    SELECT device_id, hostname, sysName, ip, hardware, os, version, status, status_reason, 
                           last_ping, last_ping_timetaken, uptime, purpose, type
                    FROM devices
                    WHERE os LIKE '%sophos%' OR os LIKE '%forti%' OR os LIKE '%pfsense%' 
                       OR type = 'firewall' OR (type = 'appliance' AND os LIKE '%xg%')
                    ORDER BY hostname ASC
                """
                cat_label = "Firewalls & Segurança"
            elif category in ('wifi-controllers', 'controladores-wifi', 'wlan-controllers'):
                sql = """
                    SELECT device_id, hostname, sysName, ip, hardware, os, version, status, status_reason, 
                           last_ping, last_ping_timetaken, uptime, purpose, type
                    FROM devices
                    WHERE os = 'ruckuswireless' OR hardware LIKE '%zd%' OR type = 'management'
                    ORDER BY hostname ASC
                """
                cat_label = "Controladores Wi-Fi"
            elif category in ('wifi-aps', 'bases-wifi', 'aps'):
                sql = """
                    SELECT device_id, hostname, sysName, ip, hardware, os, version, status, status_reason, 
                           last_ping, last_ping_timetaken, uptime, purpose, type
                    FROM devices
                    WHERE os = 'ruckuswireless-hotzone' OR (type = 'wireless' AND os != 'ruckuswireless')
                    ORDER BY hostname ASC
                """
                cat_label = "Bases Wi-Fi (Access Points)"
            else:
                return cls._empty_category_response(category, f"Categoria desconhecida: {category}")

            cursor.execute(sql)
            rows = cursor.fetchall()

            devices = []
            online_count = 0

            # Coleta portas / interfaces ativas desses dispositivos
            dev_ids = [r['device_id'] for r in rows] if rows else []
            ports_by_dev = {}
            if dev_ids:
                placeholders = ','.join(['%s'] * len(dev_ids))
                cursor.execute(f"""
                    SELECT device_id, COUNT(*) as total_ports,
                           SUM(CASE WHEN ifOperStatus = 'up' THEN 1 ELSE 0 END) as active_ports
                    FROM ports
                    WHERE device_id IN ({placeholders})
                    GROUP BY device_id
                """, dev_ids)
                for p_row in cursor.fetchall():
                    ports_by_dev[p_row['device_id']] = p_row

            for r in rows:
                is_online = (r['status'] == 1)
                last_ping_time = r.get('last_ping_timetaken')
                status_reason = (r.get('status_reason') or '').lower()
                if not is_online and status_reason == 'snmp' and last_ping_time is not None and float(last_ping_time) > 0:
                    is_online = True

                if is_online:
                    online_count += 1

                p_info = ports_by_dev.get(r['device_id'], {'total_ports': 0, 'active_ports': 0})

                # Detect Vendor / Fabricante
                raw_os = (r['os'] or '').lower()
                raw_hw = (r['hardware'] or '').lower()
                raw_host = (r['hostname'] or '').lower()

                vendor = 'Outro'
                if any(k in raw_os or k in raw_hw or k in raw_host for k in ['dell', 'dnos', 'ftos', 'force10']):
                    vendor = 'Dell'
                elif any(k in raw_os or k in raw_hw or k in raw_host for k in ['hpe', 'hp', 'procurve', 'aruba', 'officeconnect', '1930', '2910', '2920']):
                    vendor = 'HPE / Aruba'
                elif any(k in raw_os or k in raw_hw or k in raw_host for k in ['3com', 'baseline']):
                    vendor = '3Com'
                elif any(k in raw_os or k in raw_hw or k in raw_host for k in ['comware', 'h3c']):
                    vendor = 'H3C / Comware'
                elif any(k in raw_os or k in raw_hw or k in raw_host for k in ['cisco']):
                    vendor = 'Cisco'
                elif any(k in raw_os or k in raw_hw or k in raw_host for k in ['ubiquiti', 'edgeswitch', 'unifi']):
                    vendor = 'Ubiquiti'
                elif any(k in raw_os or k in raw_hw or k in raw_host for k in ['sophos']):
                    vendor = 'Sophos'
                elif any(k in raw_os or k in raw_hw or k in raw_host for k in ['ruckus', 'zonedirector']):
                    vendor = 'Ruckus'

                # Attention / Warning criteria:
                # - Status offline OR ping latency > 200ms OR active ports == 0 on switches with total ports
                is_attention = (not is_online) or (last_ping_time is not None and float(last_ping_time) > 0.2) or (category == 'switches' and p_info['total_ports'] > 0 and p_info['active_ports'] == 0)

                devices.append({
                    'id': r['device_id'],
                    'hostname': r['hostname'],
                    'sys_name': r['sysName'] or r['hostname'],
                    'ip': cls._decode_ip(r['ip']),
                    'hardware': r['hardware'] or 'Desconhecido',
                    'vendor': vendor,
                    'os': r['os'] or '',
                    'version': r['version'] or '',
                    'status': 'online' if is_online else 'offline',
                    'status_reason': r['status_reason'] or '',
                    'is_attention': is_attention,
                    'uptime_raw': r['uptime'],
                    'uptime_formatted': cls._format_uptime(r['uptime']),
                    'ports_total': p_info['total_ports'],
                    'ports_active': p_info['active_ports'],
                    'ping_ms': round(float(last_ping_time) * 1000, 1) if (last_ping_time and float(last_ping_time) > 0) else None
                })

            vendor_counts = {}
            attention_count = 0
            for d in devices:
                v = d.get('vendor', 'Outro')
                vendor_counts[v] = vendor_counts.get(v, 0) + 1
                if d.get('is_attention'):
                    attention_count += 1

            result = {
                'success': True,
                'category': category,
                'category_label': cat_label,
                'summary': {
                    'total': len(devices),
                    'online': online_count,
                    'offline': len(devices) - online_count,
                    'attention': attention_count,
                    'vendor_counts': vendor_counts
                },
                'devices': devices,
                'cached_at': now
            }

            cls._category_cache[category] = result
            cls._category_last_fetch[category] = now
            return result

        except Exception as e:
            logger.error(f"Erro ao buscar inventario da categoria {category}: {e}", exc_info=True)
            return cls._empty_category_response(category, str(e))
        finally:
            if conn:
                conn.close()

    @classmethod
    def _empty_category_response(cls, category: str, error_msg: str) -> Dict[str, Any]:
        return {
            'success': False,
            'category': category,
            'category_label': category.title(),
            'error': error_msg,
            'devices': [],
            'summary': {
                'total': 0,
                'online': 0,
                'offline': 0
            }
        }

