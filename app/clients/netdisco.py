import requests
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class NetdiscoClient:
    def __init__(self, url, user, password, api_token=None, verify_ssl=False, db_config=None):
        self.url = url.rstrip('/')
        if not '/api/v1' in self.url:
            self.url = f"{self.url}/api/v1"
        self.user = user
        self.password = password
        self.api_token = api_token
        self.verify_ssl = verify_ssl
        self.db_config = db_config
        self.session = requests.Session()
        self._cache = {}

    def get_db_connection(self):
        """Retorna uma conexão ativa ao banco de dados PostgreSQL do Netdisco."""
        if not self.db_config:
            return None
        import psycopg2
        return psycopg2.connect(
            host=self.db_config.get("host", "127.0.0.1"),
            port=int(self.db_config.get("port", 5432)),
            database=self.db_config.get("database", "netdisco"),
            user=self.db_config.get("user", "netdisco"),
            password=self.db_config.get("password", "netdisco123"),
            connect_timeout=5
        )

    def clean_ip(self, ip_str):
        """Remove o sufixo CIDR (como /32) das strings de IP do PostgreSQL."""
        if not ip_str:
            return ip_str
        if '/' in ip_str:
            return ip_str.split('/')[0]
        return ip_str

    def _get_cached(self, key, ttl=300):
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time.time() - timestamp < ttl:
                return data
        return None

    def _set_cached(self, key, data):
        self._cache[key] = (time.time(), data)

    def clear_device_cache(self, device_ip):
        self._cache.pop(f"ports:{device_ip}", None)

    def clear_topology_cache(self):
        self._cache.pop("topology", None)

    def clear_all_cache(self):
        self._cache.clear()

    def _get_headers(self):
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        if self.api_token:
            headers['Authorization'] = self.api_token
        return headers

    def login(self):
        """Tenta efetuar login no Netdisco para obter um token se não fornecido."""
        if self.api_token:
            return self.api_token

        # O endpoint de login fica na raiz do Netdisco, não sob /api/v1
        base_url = self.url.replace('/api/v1', '').rstrip('/')
        login_url = f"{base_url}/login"
        
        try:
            # Netdisco requer Basic Auth para o POST /login retornar a API key
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            response = self.session.post(
                login_url,
                json={},
                auth=(self.user, self.password),
                headers=headers,
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            res_data = response.json()
            
            if "api_key" in res_data:
                self.api_token = res_data["api_key"]
                
            return self.api_token
        except requests.exceptions.RequestException as e:
            raise Exception(f"Falha de autenticação no Netdisco: {e}")

    def _request_api(self, method, endpoint, params=None, json_data=None, retries=1):
        if not self.api_token:
            self.login()

        headers = self._get_headers()
        url = f"{self.url}/{endpoint.lstrip('/')}"

        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_data,
                verify=self.verify_ssl,
                timeout=15
            )
            
            # Se receber 401 e tiver tentativas, limpa o token e refaz login
            if response.status_code == 401 and retries > 0:
                self.api_token = None
                self.session.cookies.clear()
                self.login()
                return self._request_api(method, endpoint, params, json_data, retries - 1)
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 401 and retries > 0:
                self.api_token = None
                self.session.cookies.clear()
                self.login()
                return self._request_api(method, endpoint, params, json_data, retries - 1)
            raise Exception(f"Erro na API do Netdisco ({endpoint}): {e}")

    def _request(self, method, endpoint, params=None, json_data=None, retries=1):
        if not self.db_config:
            return self._request_api(method, endpoint, params, json_data, retries)
            
        endpoint_clean = endpoint.strip('/')
        
        if endpoint_clean == 'search/device':
            q = params.get('q', '%') if params else '%'
            return self.get_devices(q)
            
        if endpoint_clean == 'topology':
            return self.get_topology()
            
        if endpoint_clean.startswith('object/device/') and endpoint_clean.endswith('/port_vlans'):
            parts = endpoint_clean.split('/')
            device_ip = parts[2]
            return self.get_port_vlans(device_ip)
            
        if endpoint_clean.startswith('object/device/') and endpoint_clean.endswith('/ports'):
            parts = endpoint_clean.split('/')
            device_ip = parts[2]
            return self.get_device_ports(device_ip)
            
        if endpoint_clean.startswith('object/device/'):
            parts = endpoint_clean.split('/')
            device_ip = parts[2]
            return self.get_device_details(device_ip)
            
        return self._request_api(method, endpoint, params, json_data, retries)

    def get_port_vlans(self, device_ip):
        try:
            conn = self.get_db_connection()
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT port, vlan, native, egress_tag 
                FROM device_port_vlan 
                WHERE ip = %s;
            """, (device_ip,))
            rows = [dict(row) for row in cur.fetchall()]
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            print(f"[Netdisco DB Error] get_port_vlans failed for {device_ip}: {e}")
            return self._request_api("GET", f"object/device/{device_ip}/port_vlans")

    def get_devices(self, query="%"):
        """Lista os dispositivos descobertos pelo Netdisco."""
        cache_key = f"devices:{query}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
            
        if not self.db_config:
            data = self._request_api("GET", "search/device", params={"q": query})
            self._set_cached(cache_key, data)
            return data

        try:
            conn = self.get_db_connection()
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            if query == "%":
                cur.execute("SELECT ip::text as ip, dns, name, model, vendor, os, os_ver FROM device;")
            else:
                q = f"%{query}%"
                cur.execute("""
                    SELECT ip::text as ip, dns, name, model, vendor, os, os_ver 
                    FROM device 
                    WHERE name ILIKE %s OR ip::text ILIKE %s OR dns ILIKE %s;
                """, (q, q, q))
            rows = [dict(row) for row in cur.fetchall()]
            for r in rows:
                r["ip"] = self.clean_ip(r["ip"])
            cur.close()
            conn.close()
            self._set_cached(cache_key, rows)
            return rows
        except Exception as e:
            print(f"[Netdisco DB Error] get_devices failed: {e}")
            data = self._request_api("GET", "search/device", params={"q": query})
            self._set_cached(cache_key, data)
            return data

    def get_device_details(self, device_ip):
        """Obtém detalhes de um dispositivo pelo IP."""
        if not self.db_config:
            return self._request_api("GET", f"object/device/{device_ip}")
            
        try:
            conn = self.get_db_connection()
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT ip::text as ip, dns, name, model, vendor, os, os_ver 
                FROM device 
                WHERE ip = %s;
            """, (device_ip,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                row = dict(row)
                row["ip"] = self.clean_ip(row["ip"])
                return row
            return None
        except Exception as e:
            print(f"[Netdisco DB Error] get_device_details failed for {device_ip}: {e}")
            return self._request_api("GET", f"object/device/{device_ip}")

    def get_device_ports(self, device_ip):
        """Obtém as portas de um dispositivo específico e suas configurações de VLAN."""
        cache_key = f"ports:{device_ip}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
            
        if not self.db_config:
            data = self._request_api("GET", f"object/device/{device_ip}/ports")
            self._set_cached(cache_key, data)
            return data
            
        try:
            conn = self.get_db_connection()
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT port, descr, up, up_admin, type, speed, name, stp, vlan,
                       remote_ip::text as remote_ip, remote_port 
                FROM device_port 
                WHERE ip = %s;
            """, (device_ip,))
            rows = [dict(row) for row in cur.fetchall()]
            for r in rows:
                r["remote_ip"] = self.clean_ip(r["remote_ip"])
            cur.close()
            conn.close()
            self._set_cached(cache_key, rows)
            return rows
        except Exception as e:
            print(f"[Netdisco DB Error] get_device_ports failed for {device_ip}: {e}")
            data = self._request_api("GET", f"object/device/{device_ip}/ports")
            self._set_cached(cache_key, data)
            return data

    def get_topology(self):
        """Obtém os links físicos descobertos via CDP/LLDP."""
        cache_key = "topology"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
            
        if not self.db_config:
            try:
                data = self._request_api("GET", "topology")
            except Exception:
                data = self._get_topology_from_neighbors()
            self._set_cached(cache_key, data)
            return data
            
        try:
            conn = self.get_db_connection()
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            sql_top = """
                SELECT dp.ip::text AS from_device, d1.name AS from_device_name, dp.port AS from_port,
                       dp.remote_ip::text AS to_device, dp.remote_port AS to_port, d2.name AS to_device_name
                FROM device_port dp
                JOIN device d1 ON dp.ip = d1.ip
                LEFT JOIN device d2 ON dp.remote_ip = d2.ip
                WHERE dp.remote_ip IS NOT NULL AND dp.remote_port IS NOT NULL
            """
            cur.execute(sql_top)
            rows = [dict(row) for row in cur.fetchall()]
            for r in rows:
                r["from_device"] = self.clean_ip(r["from_device"])
                r["to_device"] = self.clean_ip(r["to_device"])
            cur.close()
            conn.close()
            self._set_cached(cache_key, rows)
            return rows
        except Exception as e:
            print(f"[Netdisco DB Error] get_topology failed: {e}")
            try:
                data = self._request_api("GET", "topology")
            except Exception:
                data = self._get_topology_from_neighbors()
            self._set_cached(cache_key, data)
            return data

    def _get_topology_from_neighbors(self):
        """Reconstrói a topologia a partir das portas de todos os dispositivos."""
        devices = self.get_devices()
        topology = []
        for dev in devices:
            ip = dev.get("ip")
            if not ip:
                continue
            try:
                ports = self.get_device_ports(ip)
                for port in ports:
                    # Se houver vizinho LLDP/CDP associado a esta porta
                    remote_ip = port.get("remote_ip")
                    remote_port = port.get("remote_port")
                    if remote_ip and remote_port:
                        topology.append({
                            "from_device": ip,
                            "from_device_name": dev.get("name"),
                            "from_port": port.get("port"),
                            "to_device": remote_ip,
                            "to_port": remote_port
                        })
            except Exception:
                continue
        return topology
