import psycopg2
import pymysql
import os
import json

class DatabaseClient:
    def __init__(self, config_dict=None):
        self.config = config_dict or {}
        self.db_configs = self.config.get("databases", {})

    def get_connection(self, name):
        """Retorna uma conexão ativa para o banco de dados especificado."""
        cfg = self.db_configs.get(name)
        if not cfg:
            raise Exception(f"Configuração do banco de dados '{name}' não encontrada no config.json.")

        db_type = cfg.get("type", "").lower()
        host = cfg.get("host")
        port = int(cfg.get("port", 0))
        database = cfg.get("database")
        user = cfg.get("user")
        password = cfg.get("password")

        # Se estivermos rodando localmente no host 192.168.10.51 (ou localhost) e o host estiver configurado como localhost,
        # podemos ajustar caso necessário, mas o host do config.json já mapeia isso perfeitamente.
        if db_type == "postgresql":
            return psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                connect_timeout=5
            )
        elif db_type == "mysql" or db_type == "mariadb":
            return pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                connect_timeout=5,
                autocommit=True
            )
        else:
            raise Exception(f"Tipo de banco de dados '{db_type}' não suportado para '{name}'.")

    def execute_query(self, db_name, sql, params=None):
        """Executa uma consulta de seleção (SELECT) e retorna os resultados como uma lista de dicionários."""
        conn = None
        cur = None
        try:
            conn = self.get_connection(db_name)
            # Para MySQL/MariaDB, usamos DictCursor para retornar dicionários.
            # Para PostgreSQL, usamos RealDictCursor.
            db_type = self.db_configs.get(db_name, {}).get("type", "").lower()
            
            if db_type == "mysql" or db_type == "mariadb":
                cur = conn.cursor(pymysql.cursors.DictCursor)
                cur.execute(sql, params)
                results = cur.fetchall()
            else:
                # PostgreSQL
                from psycopg2.extras import RealDictCursor
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(sql, params)
                results = [dict(row) for row in cur.fetchall()]
                
            return results
        except Exception as e:
            print(f"[DATABASE ERROR] Erro ao executar query em '{db_name}': {e}")
            raise e
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def execute_write(self, db_name, sql, params=None):
        """Executa uma instrução de escrita (INSERT/UPDATE/DELETE) e commita."""
        conn = None
        cur = None
        try:
            conn = self.get_connection(db_name)
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"[DATABASE WRITE ERROR] Erro ao escrever em '{db_name}': {e}")
            raise e
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
