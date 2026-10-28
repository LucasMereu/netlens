import networkx as nx

class PathTracer:
    def __init__(self, netdisco_client):
        self.netdisco = netdisco_client
        self.graph = nx.Graph()
        self.topology_data = []

    def build_topology_graph(self):
        """Constrói o grafo de rede utilizando os dados de topologia do Netdisco."""
        self.graph.clear()
        try:
            self.topology_data = self.netdisco.get_topology()
        except Exception as e:
            raise Exception(f"Não foi possível obter a topologia para traçar rotas: {e}")

        for link in self.topology_data:
            dev_a = link.get("from_device")
            dev_a_name = link.get("from_device_name") or dev_a
            dev_b = link.get("to_device")
            dev_b_name = link.get("to_device_name") or dev_b

            if not dev_a or not dev_b:
                continue

            # Adiciona os nós com metadados (nome/IP)
            self.graph.add_node(dev_a, name=dev_a_name, ip=dev_a)
            self.graph.add_node(dev_b, name=dev_b_name, ip=dev_b)

            # Adiciona a aresta representando a conexão física
            edge_data = self.graph.get_edge_data(dev_a, dev_b) or {"links": []}
            edge_data["links"].append({
                "from_port": link.get("from_port"),
                "to_port": link.get("to_port")
            })
            self.graph.add_edge(dev_a, dev_b, **edge_data)

    def find_device_by_ip_or_name(self, query):
        """Busca um dispositivo cadastrado pelo IP ou Nome."""
        query = query.strip().lower()
        
        # Primeiro, varre o grafo para ver se o nó existe direto pelo IP
        if query in self.graph:
            return query

        # Varre os nós em busca de correspondência de nome
        for node, data in self.graph.nodes(data=True):
            if data.get("name", "").lower() == query:
                return node
                
        # Se não encontrar no grafo, tenta fazer busca na API do Netdisco
        try:
            devices = self.netdisco.get_devices()
            for dev in devices:
                ip = dev.get("ip")
                name = dev.get("name", "")
                if query == ip.lower() or query == name.lower():
                    return ip
        except Exception:
            pass

        return None

    def find_client_by_ip_or_mac(self, query):
        """Retorna informações da conexão de um cliente (IP ou MAC) no Netdisco database."""
        if not self.netdisco:
            return None
            
        conn = self.netdisco.get_db_connection()
        if not conn:
            return None
            
        try:
            cur = conn.cursor()
            query_clean = query.strip().lower()
            
            # 1. Tenta buscar por IP primeiro
            sql_ip = """
                SELECT n.switch::text, n.port, n.mac::text, n.vlan, ni.dns
                FROM node n
                JOIN node_ip ni ON n.mac = ni.mac
                WHERE ni.ip::text = %s AND n.active = true
                ORDER BY n.time_recent DESC
                LIMIT 1;
            """
            cur.execute(sql_ip, (query_clean,))
            row = cur.fetchone()
            if row:
                return {
                    "switch_ip": self.netdisco.clean_ip(row[0]),
                    "port": row[1],
                    "mac": row[2],
                    "vlan": row[3],
                    "dns": row[4],
                    "ip": query_clean,
                    "type": "client"
                }
                
            # 2. Tenta buscar por MAC
            sql_mac = """
                SELECT switch::text, port, mac::text, vlan
                FROM node
                WHERE mac::text = %s AND active = true
                ORDER BY time_recent DESC
                LIMIT 1;
            """
            cur.execute(sql_mac, (query_clean,))
            row = cur.fetchone()
            if row:
                cur.execute("SELECT ip::text FROM node_ip WHERE mac::text = %s ORDER BY time_last DESC LIMIT 1;", (row[2],))
                ip_row = cur.fetchone()
                ip_str = self.netdisco.clean_ip(ip_row[0]) if ip_row else "N/A"
                
                return {
                    "switch_ip": self.netdisco.clean_ip(row[0]),
                    "port": row[1],
                    "mac": row[2],
                    "vlan": row[3],
                    "dns": None,
                    "ip": ip_str,
                    "type": "client"
                }
        except Exception as e:
            print(f"[PATH TRACER] Erro ao buscar cliente no banco: {e}")
        finally:
            conn.close()
            
        return None

    def trace_path(self, src_query, dest_query):
        """Calcula o caminho físico (salto a salto) entre dois dispositivos ou clientes."""
        if not self.graph.nodes:
            self.build_topology_graph()

        # Resolve a origem (pode ser switch ou cliente)
        src_client = self.find_client_by_ip_or_mac(src_query)
        if src_client:
            src_node = src_client["switch_ip"]
            src_display_name = f"Dispositivo Cliente ({src_client['ip']})"
        else:
            src_node = self.find_device_by_ip_or_name(src_query)
            if not src_node:
                raise Exception(f"Origem '{src_query}' não foi localizada (nem como switch, nem como cliente ativo).")
            src_display_name = self.graph.nodes[src_node].get("name", src_node)

        # Resolve o destino (pode ser switch ou cliente)
        dest_client = self.find_client_by_ip_or_mac(dest_query)
        if dest_client:
            dest_node = dest_client["switch_ip"]
            dest_display_name = f"Dispositivo Cliente ({dest_client['ip']})"
        else:
            dest_node = self.find_device_by_ip_or_name(dest_query)
            if not dest_node:
                raise Exception(f"Destino '{dest_query}' não foi localizado (nem como switch, nem como cliente ativo).")
            dest_display_name = self.graph.nodes[dest_node].get("name", dest_node)

        # Caso em que ambos estão no mesmo switch ou são o mesmo dispositivo
        if src_node == dest_node:
            path_details = []
            hop_idx = 1
            if src_client:
                path_details.append({
                    "hop_index": hop_idx,
                    "from_device": src_client["ip"],
                    "from_device_name": f"Cliente ({src_client['ip']} - {src_client['mac']})",
                    "to_device": src_node,
                    "to_device_name": self.graph.nodes[src_node].get("name", src_node),
                    "links": [{"from_port": "NIC", "to_port": src_client["port"]}]
                })
                hop_idx += 1
            if dest_client:
                path_details.append({
                    "hop_index": hop_idx,
                    "from_device": dest_node,
                    "from_device_name": self.graph.nodes[dest_node].get("name", dest_node),
                    "to_device": dest_client["ip"],
                    "to_device_name": f"Cliente ({dest_client['ip']} - {dest_client['mac']})",
                    "links": [{"from_port": dest_client["port"], "to_port": "NIC"}]
                })
            
            return {
                "success": True,
                "same_device": False,
                "source": src_query,
                "source_name": src_display_name,
                "destination": dest_query,
                "destination_name": dest_display_name,
                "hops_count": len(path_details),
                "path": path_details
            }

        try:
            # Encontra o caminho mais curto entre os dois switches usando Dijkstra
            shortest_path = nx.shortest_path(self.graph, source=src_node, target=dest_node)
            
            path_details = []
            hop_idx = 1
            
            # Se a origem for um cliente, adiciona o primeiro salto (do cliente até o switch)
            if src_client:
                path_details.append({
                    "hop_index": hop_idx,
                    "from_device": src_client["ip"],
                    "from_device_name": f"Cliente ({src_client['ip']} - {src_client['mac']})",
                    "to_device": src_node,
                    "to_device_name": self.graph.nodes[src_node].get("name", src_node),
                    "links": [{"from_port": "NIC", "to_port": src_client["port"]}]
                })
                hop_idx += 1
            
            # Adiciona os saltos entre os switches
            for i in range(len(shortest_path) - 1):
                node_current = shortest_path[i]
                node_next = shortest_path[i+1]
                edge_data = self.graph.get_edge_data(node_current, node_next)
                links = edge_data.get("links", [])
                
                path_details.append({
                    "hop_index": hop_idx,
                    "from_device": node_current,
                    "from_device_name": self.graph.nodes[node_current].get("name", node_current),
                    "to_device": node_next,
                    "to_device_name": self.graph.nodes[node_next].get("name", node_next),
                    "links": links
                })
                hop_idx += 1
                
            # Se o destino for um cliente, adiciona o último salto (do switch até o cliente)
            if dest_client:
                path_details.append({
                    "hop_index": hop_idx,
                    "from_device": dest_node,
                    "from_device_name": self.graph.nodes[dest_node].get("name", dest_node),
                    "to_device": dest_client["ip"],
                    "to_device_name": f"Cliente ({dest_client['ip']} - {dest_client['mac']})",
                    "links": [{"from_port": dest_client["port"], "to_port": "NIC"}]
                })
                hop_idx += 1

            return {
                "success": True,
                "same_device": False,
                "source": src_query,
                "source_name": src_display_name,
                "destination": dest_query,
                "destination_name": dest_display_name,
                "hops_count": len(path_details),
                "path": path_details
            }
        except nx.NetworkXNoPath:
            return {
                "success": False,
                "error": "Não há caminho físico mapeado entre estes dois dispositivos na topologia."
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Erro ao calcular caminho: {e}"
            }
