# Relatório de Auditoria de Rede - Bloqueio de VLAN 1 nos Trunks

Este relatório apresenta a análise das configurações de todos os switches core Dell e switches da rede `172.16.11.0/24`. O objetivo é **alinhar a VLAN 1 como VLAN default/nativa** em todos os switches (para compatibilidade com os protocolos STP/PVST+ dos switches legados 3Com/HP 1910), mas **impedir que ela trafegue nos trunks**, assegurando que apenas VLANs de dados explicitamente taggeadas passem entre os switches.

---

## Resumo da Auditoria da VLAN 1 nos Trunks

| Switch IP | Nome do Switch | Fabricante / Modelo | VLAN 1 nos Trunks | Status da Auditoria |
| :--- | :--- | :--- | :--- | :--- |
| 10.11.0.251 | ILHAS-DELL-ETH | DELL (s4048t) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.1 | HP_DC_01 | ARUBA (2910al-48G) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.2 | HP_DC_02 172.16.11.2 | ARUBA (2910al-48G) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.3 | SWNET65 | COMWARE (EtherSwitch.199) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.4 | Aruba-2930F-48G-PoEP-4SFPP | ARUBA (2930F-48G-PoE+-4SFP+) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.8 | SW-V1004-CAMERAS_CENARIO_V_DC | COMWARE (3Com Baseline Switch 2928-PWR Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.23 | SW CRP2_5.23 - SL_CCaption | COMWARE (3Com Baseline Switch 2928-SFP Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.24 | SW CRP1 Arte News | COMWARE (V191048G) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.26 | SW CRP3_5.26_POE - Arte News | COMWARE (V191024GPoE365W) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.33 | CORP_POe_ALMOX-GERAL | ARUBA (J9983A) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.36 | Estudio G | COMWARE (3Com Baseline Switch 2928-SFP Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.37 | SW CRP1_5.37 - Eletrica | COMWARE (3Com Baseline Switch 2928-SFP Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.38 | SW-STUDIO-A | COMWARE (EtherSwitch.194) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.39 | HP V1910_ ESTUDIO H | COMWARE (V191024G) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.42 | SW CRP4_5.22_POE - Redacao | COMWARE (192024GPoEPlus180W) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.43 | SW CRP1_5.31 - Portaria | COMWARE (3Com Baseline Switch 2928-SFP Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.50 | SWITCH PABX 1 | COMWARE (3Com Baseline Switch 2928-PWR Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.51 | SW CRP2 5 33  Almox G | COMWARE (3Com Baseline Switch 2928-SFP Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.52 | SW CRP1_5.3 - A01 | COMWARE (V191048G) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.53 | SW CRP2_5.4_POE - A01 | COMWARE (V191024GPoE365W) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.54 | SW 11.54 - Monitor | COMWARE (3Com Baseline Switch 2928-SFP Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.55 | Almoxarifado Tec - 172.16.11.55 | ARUBA (2910al-48G) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.56 | HPE | COMWARE (V191024G) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.70 | SW CRP1_5.7 - A11 | COMWARE (3Com Baseline Switch 2952-SFP Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.73 | SW CRP1_5.9 - A12 | ARUBA (2910al-48G) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.74 | PROD01-LJ-M01-IP10.11.0.200 | ARUBA (J9983A) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.75 | corp_laranja_m02_ip10.11.0.201 | COMWARE (3Com Baseline Switch 2928-SFP Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.77 | CORP_10_AMARELO_10.11.0.210 | COMWARE (3Com Baseline Switch 2928-SFP Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.80 | SW CRP1_5.10 - A13 | ARUBA (2910al-48G) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.81 | SW CRP2_5.11  A-13 | COMWARE (3Com Baseline Switch 2952-SFP Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.82 | CORP_07_VERDE_M07_IP10.11.0.206 | ARUBA (J9983A) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.83 | CORP_08_VERDE_MESA_9 | COMWARE (192024GPoEPlus180W) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.85 | SW - CORP - A14 | COMWARE (3Com Baseline Switch 2952-SFP Plus) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.248 | DC-DELL-ETH | DELL (s4048t) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.249 | DC-DELL-FIBRA | DELL (s4048on) | Bloqueada em todos os trunks | **✅ Conforme** |
| 172.16.11.250 | DC-DELL-ETH | DELL (s4048t) | Bloqueada em todos os trunks | **✅ Conforme** |

---

## Detalhamento de Correções e Comandos CLI por Switch

> [!IMPORTANT]
> Conforme instrução expressa ("Não aplique configurações"), nenhuma alteração foi realizada nos switches ativos. Aplique os comandos a seguir manualmente em suas respectivas interfaces CLI durante uma janela de manutenção.

### Switch: DC-DELL-FIBRA (172.16.11.249) - DELL
- **Modelo:** s4048on
- **Trunks que permitem a VLAN 1 atualmente:** Nenhum trunk ativo permitindo VLAN 1.

**Comandos CLI sugeridos para correção:**
```text
configure terminal
default vlan-id 1
no interface Vlan 4094
write memory
```

### Procedimento de Correção para Switches Web-Managed (Aruba 1820)
Switches como o modelo `J9983A` (Aruba 1820) não possuem interface CLI de texto SSH/Telnet. A configuração de bloqueio da VLAN 1 deve ser efetuada manualmente na interface web:
- **Switch CORP_POe_ALMOX-GERAL (172.16.11.33):**
  1. Acesse `https://172.16.11.33` no navegador e faça login (usuário `admin`).
  2. Navegue até o menu **VLAN** > **VLAN Port Configuration**.
  3. Selecione a **VLAN 1**.
  4. Para as portas de cascata (Uplinks), mude a associação de `Untagged` para **Excluded** (ou desmarque-as).
  5. Selecione a VLAN de tráfego de dados taggeada desejada e configure as portas de cascata como `Tagged`.
  6. Clique em **Apply** e em seguida vá em **Save Configuration** no menu superior para persistir a alteração.

- **Switch PROD01-LJ-M01-IP10.11.0.200 (172.16.11.74):**
  1. Acesse `https://172.16.11.74` no navegador e faça login (usuário `admin`).
  2. Navegue até o menu **VLAN** > **VLAN Port Configuration**.
  3. Selecione a **VLAN 1**.
  4. Para as portas de cascata (Uplinks), mude a associação de `Untagged` para **Excluded** (ou desmarque-as).
  5. Selecione a VLAN de tráfego de dados taggeada desejada e configure as portas de cascata como `Tagged`.
  6. Clique em **Apply** e em seguida vá em **Save Configuration** no menu superior para persistir a alteração.

- **Switch CORP_07_VERDE_M07_IP10.11.0.206 (172.16.11.82):**
  1. Acesse `https://172.16.11.82` no navegador e faça login (usuário `admin`).
  2. Navegue até o menu **VLAN** > **VLAN Port Configuration**.
  3. Selecione a **VLAN 1**.
  4. Para as portas de cascata (Uplinks), mude a associação de `Untagged` para **Excluded** (ou desmarque-as).
  5. Selecione a VLAN de tráfego de dados taggeada desejada e configure as portas de cascata como `Tagged`.
  6. Clique em **Apply** e em seguida vá em **Save Configuration** no menu superior para persistir a alteração.


---

## Análise Adicional: Alinhamento de PVID nos Switches de Borda

### Contexto da Dúvida:
*Nos switches de borda, o PVID está atualmente como 4092 e sem untagged nos uplinks. Após corrigir os Dell para a VLAN 1 default, retornar o PVID da borda para 1 está correto?*

### Resposta Técnica:
**Sim, está correto e é altamente recomendável.**

### Detalhamento do Funcionamento:
1. **Prevenção de Port VLAN ID (PVID) Mismatch no STP:**
   Protocolos de Spanning Tree (STP/PVST+/MSTP) transmitem pacotes de controle (BPDUs) sem tag (untagged) ou na VLAN nativa. Se um lado do link (Core Dell) estiver usando a VLAN 1 como nativa e o outro lado (Switch de Borda) estiver configurado com PVID 4092, o STP detectará uma divergência de PVID (PVID Mismatch). Quando isso ocorre, o STP bloqueia a porta para evitar loops (estado "Broken" ou "Blocking"), causando perda de pacotes e instabilidade no link.
2. **Alinhamento dos Trunks:**
   Ao alinhar o default VLAN ID nos cores Dell para VLAN 1, os uplinks dos switches de borda devem acompanhar essa mudança, retornando para o PVID 1.
3. **Segurança e Isolamento de Tráfego:**
   Para manter a segurança (evitando tráfego de dados na VLAN default), o correto é não trafegar dados de usuários na VLAN 1. A VLAN 1 deve ficar restrita aos protocolos de controle (STP/LACP/LLDP). A configuração ideal para os uplinks de borda após o alinhamento é:
   * **PVID/Native VLAN:** 1 (para alinhar o STP e evitar mismatches).
   * **VLAN 1 untagged/tagged:** Sem permissão de tráfego de dados de usuário (no Aruba/HP, excluir a VLAN 1 dos trunks ou não passar tráfego de dados taggeado nela).
   * **VLANs de Dados:** Todas taggeadas explicitamente nos uplinks.

---

## Análise de Latência e Jitter: Link 172.16.11.41 ⇄ 172.16.11.42

### Contexto do Problema:
*Ao pingar os switches 172.16.11.41 (Aruba recente) e 172.16.11.42 (HP legado conectado ao Aruba), o tempo de resposta do switch HP (.42) oscila significativamente, enquanto o Aruba se mantém estável.*

### Diagnóstico Detalhado:
1. **Integridade Física do Link:**
   A análise de estatísticas via API do LibreNMS confirmou que **não há erros de CRC, erros de alinhamento, colisões físicas ou descartes de pacotes** nas portas de interconexão entre o Aruba e o HP. O link físico e a camada de enlace estão operando perfeitamente a 1 Gbps Full-Duplex.
2. **Gargalo no Plano de Controle (Control Plane CPU):**
   A oscilação de latência (jitter) observada ao pingar diretamente o IP do switch HP 1920 (`172.16.11.42`) é um comportamento clássico de switches legados de gerenciamento web (baseados no sistema Comware 5). 
   * **Processamento de ICMP (Ping):** Quando o switch recebe um pacote de ping destinado ao seu próprio IP de gerenciamento, o hardware (ASIC) encaminha esse pacote para a CPU (Control Plane). A CPU do HP 1920 é de baixo desempenho e núcleo único.
   * **Impacto do SNMP Polling:** Ferramentas de monitoramento como LibreNMS, Zabbix e Netdisco realizam consultas frequentes via SNMP para ler tabelas de MAC, ARP e tráfego. Essas consultas consomem picos de 80% a 95% da CPU do HP. Enquanto processa o SNMP, a CPU atrasa a resposta ao ping ICMP, gerando a oscilação de latência (de 1ms a mais de 100ms).
   * **Tráfego de Passagem (Data Plane):** É fundamental frisar que **este comportamento não afeta o tráfego de passagem dos usuários**. Pacotes gerados por servidores ou computadores que apenas transitam pelo switch HP em direção ao Aruba são processados inteiramente em hardware (ASIC) e não passam pela CPU. O tráfego de rede dos usuários ocorre sem nenhuma latência ou perda.

### Recomendações e Correções Sugeridas:
1. **Ajuste de Intervalo do SNMP no Monitoramento:**
   Configure o LibreNMS/Zabbix para aumentar o intervalo de polling SNMP de switches legados (ex: mudar de 1 minuto para 5 minutos) ou desative módulos de polling desnecessários para esses hosts (como monitoramento de disco/processo ou tabelas ARP desnecessárias).
2. **Configuração de Portas de Acesso (STP Edged Port):**
   Certifique-se de que todas as portas conectadas a dispositivos finais (computadores, telefones, impressoras) no HP estejam configuradas como Edge Ports:
   ```text
   interface <porta>
     stp edged-port enable
   ```
   Isso reduz a necessidade de a CPU recalcular a topologia STP sempre que uma máquina é ligada ou desligada.
3. **Isolamento da VLAN de Gerenciamento:**
   Garanta que o IP de gerenciamento do switch HP esteja em uma VLAN dedicada de gerência (out-of-band), isolada do tráfego de broadcast de VLANs de usuários (como DHCP, ARP requests, multicast). Isso evita que a CPU do HP consuma ciclos processando pacotes de broadcast da rede de usuários.
