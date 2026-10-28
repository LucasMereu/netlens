# Camada de Banco de Dados e Pool de Conexões

Esta documentação descreve o gerenciamento de conexões de banco de dados e as regras de concorrência introduzidas no Sprint 1.

## Pool de Conexões Thread-Safe

O NetLens conecta-se a bases PostgreSQL (Netdisco, Zabbix) e MySQL/MariaDB (LibreNMS). Para suportar concorrência segura, as conexões são gerenciadas por pools centralizados em [connection_pool.py](file:///Users/administrator/Desktop/Rossi/Desenvolvimento/Redes/app/database/connection_pool.py):

*   **PostgreSQL:** Utiliza `psycopg2.pool.ThreadedConnectionPool`.
*   **MySQL/MariaDB:** Utiliza uma fila thread-safe robusta baseada em `queue.Queue` desenvolvida com verificação de integridade de conexões (`conn.ping(reconnect=True)`) e reinicialização automática de conexões quebradas.

## Regra de Isolamento por Thread

Fica terminantemente proibido compartilhar uma conexão aberta entre threads distintas. 

### Modelo Correto
```python
with MySQLConnectionContext("librenms_pool", db_cfg) as conn:
    # A conexao pertence apenas a esta thread durante o bloco with
    cur = conn.cursor()
    cur.execute(...)
# Conexao devolvida automaticamente para o pool ao sair do bloco
```
