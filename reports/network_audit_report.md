# Relatório de Auditoria de Configuração - Switches Dell Core VLT e Acesso

Este documento apresenta uma análise detalhada das configurações dos switches core **DC-DELL-ETH** (`10.11.0.248`), **DC-DELL-FIBRA** (`10.11.0.249`) e do switch de acesso **ILHAS-DELL-ETH** (`10.11.0.251`), com o objetivo de identificar divergências que possam causar instabilidade, perda de pacotes ou falhas de failover na rede.

> [!IMPORTANT]
> Conforme solicitado ("Não faça nenhuma alteração"), este relatório é estritamente informativo e apresenta apenas recomendações de correções de configuração para serem aplicadas de forma segura e planejada.

---

## Resumo dos Problemas Detectados

| Gravidade | Categoria | Descrição do Problema | Impacto |
| :--- | :--- | :--- | :--- |
| **CRÍTICA** | **Redundância (VRRP)** | Conflito de VRRP Group ID na VLAN 98 (Estúdio A). `248` usa Grupo 3; `249` usa Grupo 1. | **Split-brain de Gateway:** Ambos os switches operam como VRRP Master ativos para o IP `192.168.98.1`, gerando perda de pacotes e intermitência nas ilhas de transmissão VMix. |
| **ALTA** | **VLT / LACP** | Ausência do comando `vlt-peer-lag` no Port-channel 49 (Conexão com switch de acesso `251`). | **Falha de agregação LACP:** O switch `251` downstream não consegue estabelecer agregação ativa-ativa redundante com os dois switches core de forma íntegra. |
| **ALTA** | **Roteamento L3** | Ausência do comando `peer-routing` no domínio VLT. | **Hair-pinning de tráfego:** Pacotes destinados ao gateway redundante passam pelo link de interconexão física (ICL - Port-channel 53) desnecessariamente se caírem no switch backup, reduzindo performance e aumentando latência. |
| **MÉDIA** | **Spanning Tree (STP)** | Prioridades STP invertidas: Switch Secundário (`248`) é o Root Bridge (prioridade 0), enquanto o switch Principal (`249`) é o Backup (prioridade 4096). | **Caminho L2 sub-otimizado:** O tráfego de Spanning Tree converge para o nó secundário do VLT, contrariando o design padrão do cluster. |
| **MÉDIA** | **VLAN Nativa** | Divergência de Default VLAN nos cores: `249` usa VLAN 4094 como default, enquanto `248` usa VLAN 1. | **Native VLAN Mismatch:** Pode causar vazamento de pacotes sem tag (untagged) ou incompatibilidade de tráfego de controle entre os cores. |
| **MÉDIA** | **VLANs no Trunk** | Desalinhamento de VLANs permitidas no Port-channel 49 (Cores vs Acesso). | VLANs taggadas no Core que não estão permitidas no switch de acesso, e vice-versa. |

---

## 1. Conflito de VRRP Split-Brain (VLAN 98 - VMix Estudio A)

Identificamos um desalinhamento de grupo de VRRP na VLAN 98 que explica diretamente problemas de latência e intermitência nas ilhas VMix:

*   **Configuração no `10.11.0.248` (DC-DELL-ETH):**
    ```text
    interface Vlan 98
     ip address 192.168.98.3/28
     vrrp-group 3
      virtual-address 192.168.98.1
    ```
*   **Configuração no `10.11.0.249` (DC-DELL-FIBRA):**
    ```text
    interface Vlan 98
     ip address 192.168.98.2/28
     vrrp-group 1
      virtual-address 192.168.98.1
    ```

> [!CAUTION]
> Como os grupos VRRP são diferentes (`vrrp-group 3` vs `vrrp-group 1`), os switches **não trocam anúncios VRRP entre si** para a VLAN 98. 
> Ambos consideram-se o único roteador do grupo e entram em estado **VRRP Master (Ativo)** para o IP `192.168.98.1`. 
> Isso faz com que as tabelas ARP dos clientes fiquem oscilando (MAC flapping) entre a interface do switch `248` e do `249`, causando quedas frequentes e pacotes perdidos.

### Correção Proposta:
Alinhar o grupo de VRRP para o mesmo ID em ambos os switches. Recomendamos usar o **Grupo 3** (ou outro ID comum único para a VLAN):
*   No switch `10.11.0.249` (DC-DELL-FIBRA), alterar o grupo de 1 para 3:
    ```text
    interface Vlan 98
     no vrrp-group 1
     vrrp-group 3
      no preempt
      virtual-address 192.168.98.1
    ```

---

## 2. Port-channel 49 sem VLT (Conexão com ILHAS-DELL-ETH)

O switch de acesso `10.11.0.251` (ILHAS-DELL-ETH) conecta-se aos cores através do **Port-channel 49** (composto pelas portas `1/49/1` a `1/49/4`).
No entanto, no arquivo de configuração de ambos os cores (`248` e `249`), o Port-channel 49 está configurado como um port-channel simples, **sem a indicação de que pertence ao VLT**:

```text
! Configuração atual nos Cores 248 e 249:
interface Port-channel 49
 no ip address
 portmode hybrid
 switchport
 lacp long-timeout
 no shutdown
```

> [!WARNING]
> Sem o comando `vlt-peer-lag port-channel 49` (ou `vlt-port-channel 49` dependendo do firmware), os dois switches core anunciam IDs de LACP diferentes para o switch de acesso `251`. 
> Como resultado, o switch `251` vê links indo para dois "switches parceiros" distintos e desativa metade dos links do port-channel por falha de LACP (ou causa loops que o Spanning Tree precisará bloquear, gerando perda de redundância e largura de banda).

### Correção Proposta:
Configurar o Port-channel 49 como VLT em ambos os cores:
*   **No `248` (DC-DELL-ETH) e no `249` (DC-DELL-FIBRA):**
    ```text
    interface Port-channel 49
     vlt-peer-lag port-channel 49
    ```

---

## 3. Prioridades de Spanning Tree (RSTP) Invertidas

O spanning-tree RSTP está ativo e configurado com prioridades conflitantes com a topologia VLT:

*   **Switch `248` (VLT Secondary):** `bridge-priority 0` (Root Bridge principal da rede).
*   **Switch `249` (VLT Primary):** `bridge-priority 4096` (Backup Root Bridge).
*   **VLT Domain Config:**
    *   No `248` (VLT Secondary): `primary-priority 1`
    *   No `249` (VLT Primary): `primary-priority 4096`

> [!NOTE]
> Embora a redundância funcione, em clusters VLT é recomendável que o switch com papel de **VLT Primary** seja também o **STP Root Bridge** (com prioridade menor, ex: 0) e o **VLT Secondary** seja o **STP Backup Root** (ex: 4096). 
> Atualmente, as prioridades de VLT e Spanning Tree estão invertidas e cruzadas.

### Correção Proposta:
Ajustar as prioridades para manter a consistência de quem é o switch principal do plano de controle:
*   **No switch `249` (DC-DELL-FIBRA - Primary):**
    ```text
    protocol spanning-tree rstp
     bridge-priority 0
    ```
*   **No switch `248` (DC-DELL-ETH - Secondary):**
    ```text
    protocol spanning-tree rstp
     bridge-priority 4096
    ```
*   **Ajuste VLT Priority:**
    Alinhar o `primary-priority` do VLT no switch `249` para ser menor que o do `248` para forçar o papel de Primary nominal de forma estável (ex: `249` com prioridade 1, e `248` com prioridade 4096).

---

## 4. Divergência de Default VLAN (VLAN Nativa) e Alinhamento com Legados

*   **Situação Atual:**
    *   No `249` (DC-DELL-FIBRA): Configurado `default vlan-id 4094`. O switch usa a VLAN 4094 como default.
    *   No `248` (DC-DELL-ETH): Não possui essa linha, usando a VLAN 1 (padrão de fábrica).
    *   Switches Legados (3Com, HP V1910): Travados com VLAN 1 como default/nativa (não permitem alteração).

> [!WARNING]
> O mismatch de VLAN padrão entre os cores VLT (`248` em VLAN 1 e `249` em VLAN 4094) e com os switches de borda legados causa divergências críticas no processamento de pacotes untagged e de controle (como BPDUs de Spanning Tree). Quando uma cascata reconecta, a inconsistência de STP nos pacotes untagged na VLAN padrão pode levar a loops temporários, oscilações ARP e picos de latência.

### Correção Proposta (Alinhamento em VLAN 1 com Bloqueio nos Trunks):
Para compatibilizar a rede com os switches legados sem expor a VLAN 1 (default) nos trunks, a estratégia recomendada é:
1.  **Alinhar o Default VLAN ID para 1** em todos os switches Dell para consistência operacional e processamento correto do STP BPDU untagged.
2.  **Manter `default-vlan disable` ativo** em ambos os cores Dell, impedindo que portas físicas pertençam automaticamente à VLAN 1 untagged.
3.  **Bloquear explicitamente a VLAN 1 nos Trunks:** Remover quaisquer interfaces trunk (como port-channels ou links físicos de cascata) de serem membros (seja tagged ou untagged) da VLAN 1.

#### Comandos para o Switch `249` (DC-DELL-FIBRA):
```text
configure terminal

# 1. Alinha a VLAN padrão do switch para a VLAN 1 (padrão)
default vlan-id 1

# 2. Garante o bloqueio da VLAN 1 no trunk Port-channel 47
interface Vlan 1
 no untagged Port-channel 47
 exit

# 3. Remove a interface da VLAN 4094 (antiga padrão)
no interface Vlan 4094
write memory
```

#### Comandos para o Switch `248` (DC-DELL-ETH):
```text
configure terminal

# 1. Certifica-se de que a VLAN padrão é a VLAN 1 (já é o default se não alterado)
# 2. Certifica-se de que nenhum port-channel ou trunk é membro da VLAN 1
interface Vlan 1
 # Se houver alguma porta untagged ou tagged listada no 'show run' sob Vlan 1, remova-a, por exemplo:
 # no untagged Port-channel X
 exit
write memory
```

---

## 5. Mismatches de VLANs no Trunk (Port-channel 49)

O mapeamento comparativo de VLANs taggadas permitidas no Port-channel 49 mostrou desalinhamentos:

1.  **VLANs extras nos Cores que faltam no Acesso (`251`):**
    As VLANs `46` (Painel), `70` (Netlanches), `98` (VMix A), `99` (FW-Sophos), `100` (VMix PodCast), `111` (NET_111), `234` (Intelig), `370` (Starlink) estão taggadas no Port-channel 49 dos cores `248` e `249`, mas **não estão permitidas** no Port-channel 49 do switch `251`.
2.  **VLAN 371 (WIFI UBIQUITI 10Gb):**
    Está taggada em `248` e `251` no Port-channel 49, mas **não está taggada** em `249` (no `249` a VLAN 371 está taggada na porta física `1/14`). Se o tráfego da VLAN 371 for encaminhado para o switch `249` via LACP, ele será descartado.
3.  **VLAN 153 (V Vivo C):**
    Existe apenas no switch `249`, mas não no `248`.

### Correção Proposta:
*   Adicionar as VLANs faltantes no trunk do switch de acesso `251` (ou remover as VLANs não utilizadas nos trunks dos cores para reduzir o domínio de broadcast).
*   Adicionar a VLAN 371 no trunk do Port-channel 49 do switch `249` (DC-DELL-FIBRA):
    ```text
    interface Vlan 371
     tagged Port-channel 49
    ```

---

## 6. Otimização de Roteamento VLT (Peer-Routing)

O cluster VLT possui o recurso **Peer-Routing** desativado:
*   `Peer-Routing : Disabled` (conforme verificado no comando `show vlt brief`).

> [!TIP]
> Em uma topologia VLT com VRRP ativado, as requisições de roteamento dos clientes podem ser enviadas para o endereço MAC do switch VRRP Backup. Sem o peer-routing, esse switch backup é obrigado a encaminhar o pacote L3 pelo link ICL (Peer-Link) para o switch VRRP Master realizar o roteamento.
> Ativar o `peer-routing` faz com que ambos os switches consigam rotear pacotes localmente, economizando banda no Peer-Link e reduzindo o atraso (latência) de tráfego.

### Correção Proposta:
Habilitar o peer-routing sob a configuração do domínio VLT em ambos os switches core:
*   **No `248` (DC-DELL-ETH) e no `249` (DC-DELL-FIBRA):**
    ```text
    vlt domain 1
     peer-routing
    ```

---

## 7. VRRP sem Priorização de Master/Backup

Em quase todas as VLANs configuradas com VRRP (ex: VLANs 2, 7, 10, 11, 20, 40, 45, 46, 50, 65, 251), a prioridade do VRRP não está especificada, assumindo o valor default de `100` em ambos os switches core.

Embora o VRRP desempate pelo IP mais alto (tornando o `249` Master), o correto é ter uma prioridade explicitamente maior configurada no switch que deve ser o Master de roteamento ativo, facilitando o diagnóstico e a manutenção.

### Correção Proposta:
*   Definir prioridade `150` no switch core preferencial (ex: `249` - DC-DELL-FIBRA) e prioridade `100` no switch backup (`248` - DC-DELL-ETH) para todas as VLANs ativas.
    Exemplo na VLAN 10 do switch `249`:
    ```text
    interface Vlan 10
     vrrp-group 1
      priority 150
    ```
