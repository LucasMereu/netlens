class VlanAuditor:
    def __init__(self, netdisco_client, librenms_client=None):
        self.netdisco = netdisco_client
        self.librenms = librenms_client
        # Cache para evitar consultar a API repetidamente para o mesmo dispositivo
        self._device_ports_cache = {}

    def _get_device_ports(self, device_ip):
        if device_ip in self._device_ports_cache:
            return self._device_ports_cache[device_ip]
        
        try:
            ports = self.netdisco.get_device_ports(device_ip)
            ports_dict = {p.get("port"): p for p in ports if p.get("port")}
            
            # Busca as relações de VLAN por porta no Netdisco
            try:
                port_vlans = self.netdisco._request("GET", f"object/device/{device_ip}/port_vlans")
                for pv in port_vlans:
                    port_name = pv.get("port")
                    if port_name in ports_dict:
                        p = ports_dict[port_name]
                        vlan_id = pv.get("vlan")
                        is_native = pv.get("native")
                        egress_tag = pv.get("egress_tag")
                        
                        if "vlans" not in p:
                            p["vlans"] = []
                        p["vlans"].append(vlan_id)
                        
                        # Se for nativa/untagged (is_native ou egress_tag == 0/False), define como PVID da porta
                        if is_native or egress_tag == 0 or egress_tag is False:
                            p["pvid"] = vlan_id
                            p["vlan"] = vlan_id
            except Exception as e:
                print(f"[VlanAuditor] Erro ao buscar port_vlans para {device_ip}: {e}")
                
            self._device_ports_cache[device_ip] = ports_dict
            return ports_dict
        except Exception:
            # Fallback para o LibreNMS se o Netdisco falhar ou não tiver a informação
            if self.librenms:
                try:
                    ports = self.librenms.get_device_ports(device_ip)
                    # No LibreNMS, ifName ou ifDescr costuma ser o identificador
                    ports_dict = {}
                    for p in ports:
                        if p.get("ifName"):
                            ports_dict[p.get("ifName")] = p
                        if p.get("ifDescr") and p.get("ifDescr") != p.get("ifName"):
                            ports_dict[p.get("ifDescr")] = p
                    self._device_ports_cache[device_ip] = ports_dict
                    return ports_dict
                except Exception:
                    pass
            
            self._device_ports_cache[device_ip] = {}
            return {}

    def audit_vlans(self):
        """Audita todas as conexões físicas em busca de erros de VLAN."""
        mismatches = []
        try:
            topology = self.netdisco.get_topology()
        except Exception as e:
            raise Exception(f"Não foi possível obter a topologia para auditoria: {e}")

        # Evita processar o mesmo link duas vezes (A -> B e B -> A)
        processed_links = set()

        for link in topology:
            from_dev = link.get("from_device")
            from_port_name = link.get("from_port")
            to_dev = link.get("to_device")
            to_port_name = link.get("to_port")

            if not all([from_dev, from_port_name, to_dev, to_port_name]):
                continue

            # Chave única para o link ordenado
            link_key = tuple(sorted([f"{from_dev}:{from_port_name}", f"{to_dev}:{to_port_name}"]))
            if link_key in processed_links:
                continue
            processed_links.add(link_key)

            # Busca portas nos dispositivos
            from_ports = self._get_device_ports(from_dev)
            to_ports = self._get_device_ports(to_dev)

            port_a = from_ports.get(from_port_name)
            port_b = to_ports.get(to_port_name)

            # Se não acharmos informações de um dos lados, não podemos auditar
            if not port_a or not port_b:
                continue

            # Extrai VLANs nativas (PVID)
            pvid_a = self._extract_pvid(port_a)
            pvid_b = self._extract_pvid(port_b)

            # Extrai modo da porta (trunk vs access)
            is_trunk_a = self._is_trunk(port_a)
            is_trunk_b = self._is_trunk(port_b)

            # Extrai VLANs permitidas (allowed)
            allowed_a = self._extract_allowed_vlans(port_a, pvid_a, is_trunk_a)
            allowed_b = self._extract_allowed_vlans(port_b, pvid_b, is_trunk_b)

            # 1. Verificação de Divergência de Modo (Trunk vs Access)
            if is_trunk_a != is_trunk_b:
                mismatches.append({
                    "mismatch_type": "mode_mismatch",
                    "severity": "high",
                    "device_a": from_dev,
                    "device_a_name": link.get("from_device_name") or from_dev,
                    "port_a": from_port_name,
                    "port_a_mode": "Trunk" if is_trunk_a else "Access",
                    "device_b": to_dev,
                    "device_b_name": link.get("to_device_name") or to_dev,
                    "port_b": to_port_name,
                    "port_b_mode": "Trunk" if is_trunk_b else "Access",
                    "description": f"Divergência de modo: Porta {from_port_name} está em modo {'Trunk' if is_trunk_a else 'Access'} e a porta vizinha {to_port_name} está em {'Trunk' if is_trunk_b else 'Access'}."
                })
                continue # Pula as outras verificações se o modo for totalmente diferente

            # 2. Verificação de Native VLAN Mismatch (VLAN Nativa diferente)
            if pvid_a != pvid_b:
                mismatches.append({
                    "mismatch_type": "native_vlan_mismatch",
                    "severity": "critical",
                    "device_a": from_dev,
                    "device_a_name": link.get("from_device_name") or from_dev,
                    "port_a": from_port_name,
                    "port_a_pvid": pvid_a,
                    "device_b": to_dev,
                    "device_b_name": link.get("to_device_name") or to_dev,
                    "port_b": to_port_name,
                    "port_b_pvid": pvid_b,
                    "description": f"Divergência de VLAN nativa (PVID): Lado A ({from_port_name}) usa VLAN nativa {pvid_a}, enquanto o Lado B ({to_port_name}) usa VLAN nativa {pvid_b}."
                })

            # 3. Verificação de Allowed VLANs Mismatch (VLANs truncadas que divergem)
            if is_trunk_a and is_trunk_b:
                diff_a = allowed_a.difference(allowed_b)
                diff_b = allowed_b.difference(allowed_a)

                if diff_a or diff_b:
                    details = []
                    if diff_a:
                        details.append(f"VLANs permitidas apenas no Lado A: {sorted(list(diff_a))}")
                    if diff_b:
                        details.append(f"VLANs permitidas apenas no Lado B: {sorted(list(diff_b))}")

                    mismatches.append({
                        "mismatch_type": "allowed_vlans_mismatch",
                        "severity": "warning",
                        "device_a": from_dev,
                        "device_a_name": link.get("from_device_name") or from_dev,
                        "port_a": from_port_name,
                        "port_a_allowed": sorted(list(allowed_a)),
                        "device_b": to_dev,
                        "device_b_name": link.get("to_device_name") or to_dev,
                        "port_b": to_port_name,
                        "port_b_allowed": sorted(list(allowed_b)),
                        "description": f"Divergência nas VLANs permitidas (Trunk): " + " | ".join(details)
                    })

        return mismatches

    def _extract_pvid(self, port_data):
        # Tenta pegar pvid, vlan, native_vlan ou untagged do Netdisco/LibreNMS
        for key in ["pvid", "vlan", "native_vlan", "untagged"]:
            val = port_data.get(key)
            if val is not None:
                try:
                    return int(val)
                except ValueError:
                    pass
        return 1 # Default vlan

    def _is_trunk(self, port_data):
        # Tenta descobrir o modo
        is_trunk = port_data.get("is_trunk") or port_data.get("tagged") or port_data.get("is_uplink")
        if is_trunk is not None:
            return bool(is_trunk)

        # Se tiver VLANs na lista de tagged_vlans ou vlans e o tamanho for maior que 1, assume trunk
        vlans = port_data.get("vlans") or port_data.get("tagged_vlans") or []
        if isinstance(vlans, list) and len(vlans) > 0:
            return True
            
        # Se na descrição tiver "trunk", "uplink" ou similar
        desc = str(port_data.get("ifDescr") or port_data.get("ifAlias") or "").lower()
        if "trunk" in desc or "uplink" in desc:
            return True

        return False

    def _extract_allowed_vlans(self, port_data, pvid, is_trunk):
        if not is_trunk:
            return {pvid}

        allowed = set()
        # Se for trunk, a VLAN nativa costuma ser permitida como untagged
        if pvid:
            allowed.add(pvid)

        # Busca VLANs tagged permitidas
        # Netdisco costuma retornar uma lista de inteiros ou dicionários de VLANs
        for key in ["vlans", "tagged_vlans", "allowed_vlans"]:
            vlan_list = port_data.get(key)
            if vlan_list:
                if isinstance(vlan_list, list):
                    for v in vlan_list:
                        if isinstance(v, dict):
                            v_id = v.get("vlan") or v.get("id")
                        else:
                            v_id = v
                        try:
                            allowed.add(int(v_id))
                        except (ValueError, TypeError):
                            pass
                elif isinstance(vlan_list, str):
                    # Se for string formatada (ex: "10,20,30-35")
                    allowed.update(self._parse_vlan_string(vlan_list))

        return allowed

    def _parse_vlan_string(self, vlan_str):
        # Converte "10,20,30-35" em {10, 20, 30, 31, 32, 33, 34, 35}
        vlans = set()
        parts = vlan_str.split(',')
        for part in parts:
            part = part.strip()
            if '-' in part:
                try:
                    start, end = map(int, part.split('-'))
                    vlans.update(range(start, end + 1))
                except ValueError:
                    pass
            else:
                try:
                    vlans.add(int(part))
                except ValueError:
                    pass
        return vlans
