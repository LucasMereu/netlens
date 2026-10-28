import requests
import json
import urllib3

# Desabilitar avisos de SSL se configurado
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ZabbixClient:
    def __init__(self, url, user, password, verify_ssl=False, db_config=None):
        # Trata barra no final da URL
        self.url = url.rstrip('/')
        if not self.url.endswith('api_jsonrpc.php'):
            self.url = f"{self.url}/api_jsonrpc.php"
        self.user = user
        self.password = password
        self.verify_ssl = verify_ssl
        self.db_config = db_config
        self.auth_token = None

    def get_db_connection(self):
        """Retorna uma conexão ativa ao banco de dados PostgreSQL do Zabbix."""
        if not self.db_config:
            return None
        import psycopg2
        return psycopg2.connect(
            host=self.db_config.get("host", "192.168.10.108"),
            port=int(self.db_config.get("port", 5432)),
            database=self.db_config.get("database", "zabbix"),
            user=self.db_config.get("user", "zabbix"),
            password=self.db_config.get("password", "zabbix"),
            connect_timeout=5
        )

    def _request_api(self, method, params=None, auth_required=True, retries=1):
        if auth_required and not self.auth_token:
            self.login()

        headers = {'Content-Type': 'application/json'}
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": 1
        }
        if auth_required and self.auth_token:
            payload["auth"] = self.auth_token

        try:
            response = requests.post(
                self.url,
                data=json.dumps(payload),
                headers=headers,
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            if "error" in result:
                err_data = result['error'].get('data', '')
                err_msg = result['error'].get('message', '')
                # Se for erro de sessão/autenticação e tiver retries, refaz login e tenta de novo
                if auth_required and retries > 0 and any(x in str(err_data).lower() or x in str(err_msg).lower() for x in ["session", "auth", "logged in", "permission", "authorized"]):
                    self.auth_token = None
                    self.login()
                    return self._request_api(method, params, auth_required, retries - 1)
                raise Exception(f"Erro na API do Zabbix ({method}): {err_data or err_msg}")
            return result.get("result")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Falha de conexão com a API do Zabbix: {e}")

    def _request(self, method, params=None, auth_required=True, retries=1):
        if not self.db_config:
            return self._request_api(method, params, auth_required, retries)
            
        if method == "trigger.get":
            return self.get_active_alerts()
        elif method == "host.get":
            return self.get_hosts()
        elif method == "user.login":
            return self.login()
            
        return self._request_api(method, params, auth_required, retries)

    def login(self):
        if self.db_config:
            try:
                conn = self.get_db_connection()
                conn.close()
                return "DB_OK"
            except Exception as e:
                raise Exception(f"Falha de conexão direta com o banco do Zabbix: {e}")

        # Tenta logar usando 'username' (Zabbix 6.0+) ou 'user' (Zabbix 5.4-)
        try:
            params = {"username": self.user, "password": self.password}
            self.auth_token = self._request_api("user.login", params, auth_required=False)
        except Exception as e:
            # Fallback para versões mais antigas do Zabbix
            try:
                params = {"user": self.user, "password": self.password}
                self.auth_token = self._request_api("user.login", params, auth_required=False)
            except Exception as e2:
                raise Exception(f"Falha de autenticação no Zabbix: {e2}")
        return self.auth_token

    def get_hosts(self):
        """Retorna todos os hosts monitorados no Zabbix."""
        if not self.db_config:
            params = {
                "output": ["hostid", "host", "name", "status"],
                "selectInterfaces": ["ip"]
            }
            return self._request_api("host.get", params)
            
        try:
            conn = self.get_db_connection()
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            sql = """
                SELECT h.hostid::text, h.host, h.name, h.status::text, hi.ip
                FROM hosts h
                LEFT JOIN interface hi ON h.hostid = hi.hostid
            """
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            
            hosts_map = {}
            for row in rows:
                hid = row["hostid"]
                if hid not in hosts_map:
                    hosts_map[hid] = {
                        "hostid": hid,
                        "host": row["host"],
                        "name": row["name"],
                        "status": row["status"],
                        "interfaces": []
                    }
                if row["ip"]:
                    hosts_map[hid]["interfaces"].append({"ip": row["ip"]})
            return list(hosts_map.values())
        except Exception as e:
            print(f"[Zabbix DB Error] get_hosts failed: {e}")
            params = {
                "output": ["hostid", "host", "name", "status"],
                "selectInterfaces": ["ip"]
            }
            return self._request_api("host.get", params)

    def get_active_alerts(self):
        """Retorna os alertas/triggers ativos de alta prioridade (Warning a Disaster)."""
        if not self.db_config:
            params = {
                "output": ["triggerid", "description", "priority", "lastchange"],
                "filter": {
                    "value": 1, # Apenas triggers em estado de problema
                    "status": 0 # Habilitadas
                },
                "selectHosts": ["hostid", "name"],
                "sortfield": "priority",
                "sortorder": "DESC",
                "limit": 50
            }
            return self._request_api("trigger.get", params)

        try:
            conn = self.get_db_connection()
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            sql = """
                SELECT t.triggerid::text, t.description, t.priority::text, t.lastchange::text,
                       h.hostid::text, h.name as host_name
                FROM triggers t
                JOIN functions f ON t.triggerid = f.triggerid
                JOIN items i ON f.itemid = i.itemid
                JOIN hosts h ON i.hostid = h.hostid
                WHERE t.status = 0 AND t.value = 1
                ORDER BY t.priority DESC
            """
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            
            alerts_map = {}
            for row in rows:
                tid = row["triggerid"]
                if tid not in alerts_map:
                    alerts_map[tid] = {
                        "triggerid": tid,
                        "description": row["description"],
                        "priority": row["priority"],
                        "lastchange": row["lastchange"],
                        "hosts": []
                    }
                alerts_map[tid]["hosts"].append({
                    "hostid": row["hostid"],
                    "name": row["host_name"]
                })
            return list(alerts_map.values())[:50]
        except Exception as e:
            print(f"[Zabbix DB Error] get_active_alerts failed: {e}")
            params = {
                "output": ["triggerid", "description", "priority", "lastchange"],
                "filter": {
                    "value": 1,
                    "status": 0
                },
                "selectHosts": ["hostid", "name"],
                "sortfield": "priority",
                "sortorder": "DESC",
                "limit": 50
            }
            return self._request_api("trigger.get", params)

    def get_interface_traffic(self, host_name=None):
        """Retorna métricas de tráfego de interface do Zabbix."""
        # Geralmente preferimos o LibreNMS para isso, mas serve como fallback/cruzamento
        params = {
            "output": ["itemid", "name", "key_", "lastvalue"],
            "search": {
                "key_": "net.if"
            },
            "filter": {
                "value_type": 3 # Numeric unsigned
            }
        }
        if host_name:
            params["host"] = host_name
        return self._request_api("item.get", params)
