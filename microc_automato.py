"""Autômato determinístico do MicroC: estados, símbolos e transições.

Este módulo é **deliberadamente ignorante de ``TokenKind``**. Se ele importasse
o enum de ``Lexer.py``, e ``Lexer.py`` importasse este módulo, teríamos import
circular — o Python quebraria dependendo de qual módulo fosse carregado
primeiro. A tradução ``Estado -> TokenKind`` mora em ``Lexer.py``, onde
``TokenKind`` já vive.

O efeito colateral é bom: o autômato pode ser lido e testado sem arrastar nada
do MicroC junto. Ele só sabe estados, símbolos e para onde ir.

Cobertura: identificadores, inteiros, operadores e delimitadores. Strings e
comentários **não** estão aqui — são rotinas manuais em ``Lexer.py``, porque
cada um exige uma posição de erro diferente da posição corrente do autômato
(ver a seção 2 do documento de design).
"""

from __future__ import annotations

import enum


class Estado(enum.Enum):
    """Estados do autômato.

    ``INICIO`` é o único estado de partida. Os demais são alcançados por
    consumo de caracteres, e a maioria é aceitadora — as exceções estão
    documentadas em ``ESTADOS_ACEITADORES``.
    """

    INICIO = enum.auto()

    IDENT = enum.auto()
    INT = enum.auto()

    MAIS = enum.auto()
    MENOS = enum.auto()
    ASTERISCO = enum.auto()
    BARRA = enum.auto()
    PORCENTO = enum.auto()

    MENOR = enum.auto()
    MENOR_IGUAL = enum.auto()
    MAIOR = enum.auto()
    MAIOR_IGUAL = enum.auto()
    IGUAL = enum.auto()
    IGUAL_IGUAL = enum.auto()
    EXCLAMACAO = enum.auto()
    EXCLAMACAO_IGUAL = enum.auto()
    E_COMERCIAL = enum.auto()
    E_LOGICO = enum.auto()
    BARRA_VERTICAL = enum.auto()
    OU_LOGICO = enum.auto()

    ABRE_PARENTESE = enum.auto()
    FECHA_PARENTESE = enum.auto()
    ABRE_CHAVE = enum.auto()
    FECHA_CHAVE = enum.auto()
    VIRGULA = enum.auto()
    PONTO_VIRGULA = enum.auto()


#: Símbolos de classe. Letras e dígitos colapsam em duas classes porque
#: identificadores e inteiros não distinguem *qual* letra ou dígito apareceu.
#: Operadores continuam sendo eles mesmos, porque '<' e '>' levam a estados
#: diferentes. Não há colisão: uma chave literal é sempre um caractere único.
LETRA = "LETRA"
DIGITO = "DIGITO"


def classificar(caractere: str) -> str:
    """Reduz um caractere ao símbolo que indexa a tabela de transições.

    O teste ``isascii()`` não é zelo excessivo. Sem ele, ``"é".isalpha()`` é
    ``True`` em Python, e ``Lexer("é")`` produziria um identificador — violando
    a regra de que o fonte MicroC é ASCII (enunciado, seção 3.4). Com ele, ``é``
    devolve ``"é"``, que não tem transição nenhuma, e o erro léxico cai
    naturalmente onde deve, sem nenhum ``if`` dedicado.
    """
    if caractere.isascii() and (caractere.isalpha() or caractere == "_"):
        return LETRA
    if caractere.isascii() and caractere.isdigit():
        return DIGITO
    return caractere


#: Tabela de transições: ``estado atual -> símbolo -> próximo estado``.
#: Estados ausentes como chave externa são finais: não sai transição deles.
TABELA_TRANSICOES: dict[Estado, dict[str, Estado]] = {
    Estado.INICIO: {
        LETRA: Estado.IDENT,
        DIGITO: Estado.INT,
        "+": Estado.MAIS,
        "-": Estado.MENOS,
        "*": Estado.ASTERISCO,
        # Uma barra só chega aqui quando não é início de comentário: quem roda
        # antes do autômato (`Lexer._pular_ignoraveis`) já descartou '//' e '/*'.
        # Comentário e SLASH nunca competem porque nem chegam a se encontrar.
        "/": Estado.BARRA,
        "%": Estado.PORCENTO,
        "<": Estado.MENOR,
        ">": Estado.MAIOR,
        "=": Estado.IGUAL,
        "!": Estado.EXCLAMACAO,
        "&": Estado.E_COMERCIAL,
        "|": Estado.BARRA_VERTICAL,
        "(": Estado.ABRE_PARENTESE,
        ")": Estado.FECHA_PARENTESE,
        "{": Estado.ABRE_CHAVE,
        "}": Estado.FECHA_CHAVE,
        ",": Estado.VIRGULA,
        ";": Estado.PONTO_VIRGULA,
    },
    # Identificador absorve letras e dígitos; inteiro absorve só dígitos.
    # É essa assimetria que faz "1abc" virar INT_LITERAL(1) + IDENTIFIER(abc):
    # o 'a' não tem para onde ir a partir de INT, a caminhada trava, e o lexer
    # consome apenas o que foi aceito.
    Estado.IDENT: {LETRA: Estado.IDENT, DIGITO: Estado.IDENT},
    Estado.INT: {DIGITO: Estado.INT},
    # Operadores de dois caracteres. O munch máximo do lexer garante que estes
    # vençam seus prefixos de um caractere, sem precisar de caso especial.
    Estado.MENOR: {"=": Estado.MENOR_IGUAL},
    Estado.MAIOR: {"=": Estado.MAIOR_IGUAL},
    Estado.IGUAL: {"=": Estado.IGUAL_IGUAL},
    Estado.EXCLAMACAO: {"=": Estado.EXCLAMACAO_IGUAL},
    Estado.E_COMERCIAL: {"&": Estado.E_LOGICO},
    Estado.BARRA_VERTICAL: {"|": Estado.OU_LOGICO},
}


#: Estados que encerram um lexema válido.
#:
#: ``E_COMERCIAL`` e ``BARRA_VERTICAL`` estão FORA desta lista de propósito. É
#: assim que "ocorrências isoladas de & ou | são erros léxicos" (enunciado,
#: seção 3.4) vira uma **propriedade do autômato** em vez de um ``if``: um '&'
#: solitário alcança ``E_COMERCIAL``, que não aceita, então a caminhada termina
#: sem nenhum estado aceitador visitado — exatamente a condição de erro.
#:
#: ``INICIO`` também está fora, pelo mesmo mecanismo: um caractere que não abre
#: token nenhum não sai de ``INICIO`` e cai na mesma condição de erro.
ESTADOS_ACEITADORES: frozenset[Estado] = frozenset(
    {
        Estado.IDENT,
        Estado.INT,
        Estado.MAIS,
        Estado.MENOS,
        Estado.ASTERISCO,
        Estado.BARRA,
        Estado.PORCENTO,
        Estado.MENOR,
        Estado.MENOR_IGUAL,
        Estado.MAIOR,
        Estado.MAIOR_IGUAL,
        Estado.IGUAL,
        Estado.IGUAL_IGUAL,
        Estado.EXCLAMACAO,
        Estado.EXCLAMACAO_IGUAL,
        Estado.E_LOGICO,
        Estado.OU_LOGICO,
        Estado.ABRE_PARENTESE,
        Estado.FECHA_PARENTESE,
        Estado.ABRE_CHAVE,
        Estado.FECHA_CHAVE,
        Estado.VIRGULA,
        Estado.PONTO_VIRGULA,
    }
)


def transicao(estado: Estado, simbolo: str) -> Estado | None:
    """Devolve o estado seguinte, ou ``None`` se a caminhada trava aqui.

    Expor a consulta como função (em vez de deixar quem chama indexar a tabela)
    mantém o formato interno de ``TABELA_TRANSICOES`` como detalhe deste módulo.
    """
    return TABELA_TRANSICOES.get(estado, {}).get(simbolo)
