import time
import queue
import threading
import psycopg2
import psycopg2.pool
import pymysql
import pymysql.cursors
from app.utils.logging import get_logger

logger = get_logger("connection_pool")

class ThreadSafeMySQLConnectionPool:
    """
    A robust, thread-safe connection pool for PyMySQL using queue.Queue.
    Supports connection validation (ping) and auto-reconnection.
    """
    def __init__(self, minconn=2, maxconn=10, **kwargs):
        self.maxconn = maxconn
        self.kwargs = kwargs
        self.pool = queue.Queue(maxsize=maxconn)
        self.lock = threading.Lock()
        self.allocated = 0

        # Initialize minimum connections
        for _ in range(minconn):
            conn = self._create_connection()
            if conn:
                self.pool.put(conn)

    def _create_connection(self):
        try:
            # Ensure autocommit is True by default for pool consistency
            kwargs = self.kwargs.copy()
            kwargs.setdefault('autocommit', True)
            conn = pymysql.connect(**kwargs)
            with self.lock:
                self.allocated += 1
            return conn
        except Exception as e:
            logger.error(f"Erro ao criar conexao MySQL: {e}")
            return None

    def get_connection(self, timeout=5):
        # Try to get connection from queue
        try:
            conn = self.pool.get(block=False)
            # Validate connection
            try:
                conn.ping(reconnect=True)
                return conn
            except Exception:
                logger.warning("Conexao MySQL expirada ou corrompida. Criando nova.")
                with self.lock:
                    self.allocated -= 1
                try:
                    conn.close()
                except:
                    pass
        except queue.Empty:
            # Queue is empty, can we create new?
            with self.lock:
                if self.allocated < self.maxconn:
                    # Yes, we can allocate more
                    pass
                else:
                    # Must wait for one
                    conn = None
            
            if conn is None:
                try:
                    conn = self.pool.get(block=True, timeout=timeout)
                    try:
                        conn.ping(reconnect=True)
                        return conn
                    except Exception:
                        with self.lock:
                            self.allocated -= 1
                        try:
                            conn.close()
                        except:
                            pass
                except queue.Empty:
                    raise Exception("Timeout aguardando conexao MySQL disponivel no pool.")

        # Create new connection
        new_conn = self._create_connection()
        if new_conn:
            return new_conn
        else:
            raise Exception("Nao foi possivel obter conexao MySQL (falha ao criar nova conexao).")

    def return_connection(self, conn):
        if conn is None:
            return
        try:
            self.pool.put(conn, block=False)
        except queue.Full:
            # Drop the connection if pool is somehow full
            with self.lock:
                self.allocated -= 1
            try:
                conn.close()
            except:
                pass

    def close_all(self):
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
            except:
                pass
            with self.lock:
                self.allocated -= 1


class DatabasePool:
    _pools = {}
    _lock = threading.Lock()

    @classmethod
    def get_pg_pool(cls, name_key, db_config):
        with cls._lock:
            if name_key not in cls._pools:
                logger.info(f"Inicializando pool Postgres para: {name_key}")
                cls._pools[name_key] = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=10,
                    host=db_config.get("host", "127.0.0.1"),
                    port=db_config.get("port", 5432),
                    database=db_config.get("database", "netdisco"),
                    user=db_config.get("user", "netdisco"),
                    password=db_config.get("password", "netdisco123"),
                    connect_timeout=5
                )
            return cls._pools[name_key]

    @classmethod
    def get_mysql_pool(cls, name_key, db_config):
        with cls._lock:
            if name_key not in cls._pools:
                logger.info(f"Inicializando pool MySQL para: {name_key}")
                cls._pools[name_key] = ThreadSafeMySQLConnectionPool(
                    minconn=2,
                    maxconn=10,
                    host=db_config.get("host", "127.0.0.1"),
                    port=int(db_config.get("port", 3306)),
                    user=db_config.get("user", "librenms"),
                    password=db_config.get("password", "librenms"),
                    database=db_config.get("dbname", "librenms"),
                    connect_timeout=5
                )
            return cls._pools[name_key]

    @classmethod
    def close_all_pools(cls):
        with cls._lock:
            for name_key, pool in cls._pools.items():
                try:
                    if hasattr(pool, 'closeall'):
                        pool.closeall()
                    elif hasattr(pool, 'close_all'):
                        pool.close_all()
                except Exception as e:
                    logger.error(f"Erro ao fechar pool {name_key}: {e}")
            cls._pools.clear()


class PostgresConnectionContext:
    def __init__(self, pool_name, db_config):
        self.pool = DatabasePool.get_pg_pool(pool_name, db_config)
        self.conn = None

    def __enter__(self):
        self.conn = self.pool.getconn()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.pool.putconn(self.conn)


class MySQLConnectionContext:
    def __init__(self, pool_name, db_config):
        self.pool = DatabasePool.get_mysql_pool(pool_name, db_config)
        self.conn = None

    def __enter__(self):
        self.conn = self.pool.get_connection()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.pool.return_connection(self.conn)
