# Criando um Novo Driver de Rede (Guia do Desenvolvedor)

Este guia descreve os passos necessários para adicionar suporte a um novo fabricante (ex: HPE Comware, Aruba AOS-S, Cisco IOS) na arquitetura do NetLens.

## Passos para Implementação

1.  **Criar o Diretório:**
    Crie uma nova subpasta em `app/drivers/<fabricante>/`.
    
2.  **Implementar a Interface NetworkDriver:**
    Crie a classe concreta herdando de `NetworkDriver` (definido em [base_driver.py](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/drivers/base_driver.py)).
    
3.  **Implementar/Selecionar o Transport:**
    Utilize o `SSHTransport` existente ou implemente uma especialização de `NetworkTransport` (ex: `APITransport`) em `app/drivers/transport/`.
    
4.  **Implementar o Parser:**
    Crie uma classe `Parser` (ex: `HPEParser`) para processar as saídas CLI e retornar estruturas de dados tipadas (como `ExpectedState` ou `NetworkInterface`).
    
5.  **Implementar o Command Builder:**
    Crie uma classe `CommandBuilder` para encapsular a geração dos comandos CLI correspondentes de cada intenção de rede.
    
6.  **Declarar as Capabilities:**
    No construtor do novo driver, declare as capacidades suportadas instanciando o `DeviceCapabilities`.
    
7.  **Registrar no NetworkDriverFactory:**
    Atualize a lógica em [factory.py](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/drivers/factory.py) para que a tupla `(vendor, platform)` retorne o novo driver.
    
8.  **Criar os Testes Unitários:**
    Adicione os testes correspondentes em `test_app.py` garantindo que o driver gera os planos e rollback corretos e que o factory o resolve perfeitamente.
