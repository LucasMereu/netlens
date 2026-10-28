import requests
import urllib3
import time
import pymysql

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class LibreNMSClient:
    def __init__(self, url, user=None, password=None, api_token=None, verify_ssl=False, db_config=None):
        self.url = url.rstrip('/')
        if not '/api/v0' in self.url:
            self.url = f"{self.url}/api/v0"
        self.user = user
        self.password = password
        self.api_token = api_token
        self.verify_ssl = verify_ssl
        self.db_config = db_config
        self._cache = {}

    def get_db_connection(self):
        """Retorna uma conexão ativa ao banco de dados MySQL/MariaDB do LibreNMS."""
        if not self.db_config:
            return None
        import pymysql
        return pymysql.connect(
            host=self.db_config.get("host", "192.168.10.50"),
            port=int(self.db_config.get("port", 33066)),
            user=self.db_config.get("user", "librenms"),
            password=self.db_config.get("password", "librenms"),
            database=self.db_config.get("database", "librenms"),
            connect_timeout=5,
            autocommit=True
        )

    def _get_cached(self, key, ttl=300):
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time.time() - timestamp < ttl:
                return data
        return None

    def _set_cached(self, key, data):
        self._cache[key] = (time.time(), data)

    def clear_all_cache(self):
        self._cache.clear()

    def _get_headers(self):
        headers = {}
        if self.api_token:
            headers['X-Auth-Token'] = self.api_token
        return headers

    def _request_api(self, endpoint, params=None):
        headers = self._get_headers()
        url = f"{self.url}/{endpoint.lstrip('/')}"
        
        # Se não houver api_token mas tiver user/pass, tentamos Basic Auth
        auth = None
        if not self.api_token and self.user and self.password:
            auth = (self.user, self.password)

        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                auth=auth,
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Falha de conexão com a API do LibreNMS: {e}")

    def _request(self, endpoint, params=None):
        if not self.db_config:
            return self._request_api(endpoint, params)
            
        endpoint_clean = endpoint.strip('/')
        
        if endpoint_clean == 'devices':
            devices = self.get_devices()
            return {"devices": devices}
            
        if endpoint_clean.startswith('devices/') and endpoint_clean.endswith('/ports'):
            parts = endpoint_clean.split('/')
            device_id_or_hostname = parts[1]
            ports = self.get_device_ports(device_id_or_hostname)
            return {"ports": ports}
            
        if endpoint_clean == 'ports':
            ports = self.get_all_ports()
            return {"ports": ports}
            
        if endpoint_clean == 'logs/syslog':
            from_time = params.get('from') if params else None
            limit = int(params.get('limit', 1000)) if params else 1000
            logs = self.get_syslog(from_time, limit)
            return {"logs": logs}
            
        return self._request_api(endpoint, params)

    def get_syslog(self, from_time=None, limit=1000):
        try:
            conn = self.get_db_connection()
            cur = conn.cursor(pymysql.cursors.DictCursor)
            
            sql = """
                SELECT s.msg, s.timestamp, d.hostname, d.sysName
                FROM syslog s
                JOIN devices d ON s.device_id = d.device_id
            """
            params = []
            if from_time:
                sql += " WHERE s.timestamp >= %s"
                params.append(from_time)
                
            sql += " ORDER BY s.timestamp ASC LIMIT %s"
            params.append(limit)
            
            cur.execute(sql, params)
            rows = cur.fetchall()
            
            for r in rows:
                if r.get("timestamp"):
                    r["timestamp"] = r["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
                    
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            print(f"[LibreNMS DB Error] get_syslog failed: {e}")
            return self._request_api("logs/syslog", params={"from": from_time, "limit": limit}).get("logs", [])

    def get_devices(self, force_refresh=False):
        """Retorna a lista de dispositivos cadastrados."""
        cache_key = "devices"
        if not force_refresh:
            cached = self._get_cached(cache_key, ttl=60)
            if cached is not None:
                return cached
            
        if not self.db_config:
            result = self._request_api("devices")
            data = result.get("devices", [])
            self._set_cached(cache_key, data)
            return data
            
        try:
            conn = self.get_db_connection()
            cur = conn.cursor(pymysql.cursors.DictCursor)
            cur.execute("SELECT device_id, hostname, sysName, uptime, last_polled, os, hardware, community FROM devices;")
            rows = cur.fetchall()
            for r in rows:
                if r.get("last_polled"):
                    r["last_polled"] = r["last_polled"].strftime("%Y-%m-%d %H:%M:%S")
            cur.close()
            conn.close()
            self._set_cached(cache_key, rows)
            return rows
        except Exception as e:
            print(f"[LibreNMS DB Error] get_devices failed: {e}")
            result = self._request_api("devices")
            data = result.get("devices", [])
            self._set_cached(cache_key, data)
            return data

    def get_device_ports(self, device_id_or_hostname):
        """Retorna todas as portas de um dispositivo específico."""
        cache_key = f"ports:{device_id_or_hostname}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
            
        if not self.db_config:
            endpoint = f"devices/{device_id_or_hostname}/ports"
            result = self._request_api(endpoint)
            data = result.get("ports", [])
            self._set_cached(cache_key, data)
            return data
            
        try:
            conn = self.get_db_connection()
            cur = conn.cursor(pymysql.cursors.DictCursor)
            
            if str(device_id_or_hostname).isdigit():
                sql = """
                    SELECT p.*, ps.ifInDiscards, ps.ifOutDiscards
                    FROM ports p
                    LEFT JOIN ports_statistics ps ON p.port_id = ps.port_id
                    WHERE p.device_id = %s
                """
                params = (int(device_id_or_hostname),)
            else:
                sql = """
                    SELECT p.*, ps.ifInDiscards, ps.ifOutDiscards
                    FROM ports p
                    JOIN devices d ON p.device_id = d.device_id
                    LEFT JOIN ports_statistics ps ON p.port_id = ps.port_id
                    WHERE d.hostname = %s
                """
                params = (device_id_or_hostname,)
                
            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            self._set_cached(cache_key, rows)
            return rows
        except Exception as e:
            print(f"[LibreNMS DB Error] get_device_ports failed for {device_id_or_hostname}: {e}")
            endpoint = f"devices/{device_id_or_hostname}/ports"
            result = self._request_api(endpoint)
            data = result.get("ports", [])
            self._set_cached(cache_key, data)
            return data

    def get_all_ports(self, force_refresh=False, ttl=10):
        """Retorna a lista de todas as portas ativas no sistema (TTL padrão de 10s para dados frescos)."""
        cache_key = "all_ports"
        if not force_refresh:
            cached = self._get_cached(cache_key, ttl=ttl)
            if cached is not None:
                return cached
            
        if not self.db_config:
            columns = "port_id,device_id,ifIndex,ifName,ifDescr,ifAlias,ifSpeed,ifType,ifInOctets_rate,ifOutOctets_rate,ifInErrors,ifOutErrors,ifInErrors_rate,ifInErrors_delta,ifOutErrors_rate,ifOutErrors_delta,ifOperStatus,ifAdminStatus,poll_period,poll_time"
            result = self._request_api("ports", params={"columns": columns})
            data = result.get("ports", [])
            self._set_cached(cache_key, data)
            return data
            
        try:
            conn = self.get_db_connection()
            cur = conn.cursor(pymysql.cursors.DictCursor)
            sql = """
                SELECT p.port_id, p.device_id, p.ifIndex, p.ifName, p.ifDescr, p.ifAlias, p.ifSpeed, p.ifType,
                       p.ifInOctets_rate, p.ifOutOctets_rate, p.ifInErrors, p.ifOutErrors,
                       p.ifInErrors_rate, p.ifInErrors_delta, p.ifOutErrors_rate, p.ifOutErrors_delta,
                       p.ifOperStatus, p.ifAdminStatus, p.ifLastChange, p.poll_period, p.poll_time,
                       ps.ifInDiscards, ps.ifOutDiscards,
                       ps.ifInDiscards_rate, ps.ifInDiscards_delta, ps.ifOutDiscards_rate, ps.ifOutDiscards_delta
                FROM ports p
                LEFT JOIN ports_statistics ps ON p.port_id = ps.port_id
            """
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            self._set_cached(cache_key, rows)
            return rows
        except Exception as e:
            print(f"[LibreNMS DB Error] get_all_ports failed: {e}")
            columns = "port_id,device_id,ifIndex,ifName,ifDescr,ifAlias,ifSpeed,ifType,ifInOctets_rate,ifOutOctets_rate,ifInErrors,ifOutErrors,ifInErrors_rate,ifInErrors_delta,ifOutErrors_rate,ifOutErrors_delta,ifOperStatus,ifAdminStatus,poll_period,poll_time"
            result = self._request_api("ports", params={"columns": columns})
            data = result.get("ports", [])
            self._set_cached(cache_key, data)
            return data

    def get_high_utilization_ports(self, threshold_pct=80.0):
        """Retorna portas que estão utilizando acima do threshold (%)."""
        ports = self.get_all_ports()
        high_ports = []
        for port in ports:
            # Pula portas desligadas
            if port.get("ifOperStatus") != "up":
                continue
                
            speed = float(port.get("ifSpeed") or 0)
            if not speed:
                continue

            in_rate = float(port.get("ifInOctets_rate") or 0) * 8 # octetos/s para bps
            out_rate = float(port.get("ifOutOctets_rate") or 0) * 8

            max_rate = max(in_rate, out_rate)
            util_pct = (max_rate / speed) * 100.0

            if util_pct >= threshold_pct:
                port["util_pct"] = round(util_pct, 2)
                port["in_rate_mbps"] = round(in_rate / 1000000.0, 2)
                port["out_rate_mbps"] = round(out_rate / 1000000.0, 2)
                port["speed_mbps"] = round(speed / 1000000.0, 2)
                high_ports.append(port)
                
        return high_ports

    def get_error_ports(self):
        """Retorna portas que possuem erros físicos ativos."""
        ports = self.get_all_ports()
        error_ports = []
        for port in ports:
            in_err = int(port.get("ifInErrors") or 0)
            out_err = int(port.get("ifOutErrors") or 0)

            if in_err > 0 or out_err > 0:
                port["total_errors"] = in_err + out_err
                port["total_discards"] = int(port.get("ifInDiscards") or 0) + int(port.get("ifOutDiscards") or 0)
                error_ports.append(port)

        return error_ports
