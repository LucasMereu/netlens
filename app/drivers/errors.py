class NetworkDriverError(Exception):
    """Classe base para todas as excecoes de driver de rede no NetLens."""
    pass

class ConnectionError(NetworkDriverError):
    """Ocorre quando falha a conexao fisica/rede com o equipamento."""
    pass

class AuthenticationError(NetworkDriverError):
    """Ocorre quando as credenciais fornecidas sao rejeitadas."""
    pass

class TimeoutError(NetworkDriverError):
    """Ocorre quando uma operacao (leitura/conexao/comando) excede o tempo limite."""
    pass

class CommandError(NetworkDriverError):
    """Ocorre quando a CLI do equipamento retorna uma mensagem de erro para o comando enviado."""
    pass

class ParseError(NetworkDriverError):
    """Ocorre quando falha a analise/parsing de uma saida de comando."""
    pass

class UnsupportedOperationError(NetworkDriverError):
    """Ocorre quando uma operacao nao e suportada pelas capacidades do equipamento."""
    pass

class ValidationError(NetworkDriverError):
    """Ocorre quando falha a validacao de estado apos aplicacao do comando."""
    pass

class UnsupportedDeviceError(NetworkDriverError):
    """Ocorre quando o fabricante ou plataforma do equipamento nao possui driver correspondente."""
    pass
