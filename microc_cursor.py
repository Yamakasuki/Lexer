"""Navegação sobre o texto-fonte, com rastreamento de linha e coluna.

Este módulo não sabe nada sobre MicroC: ele só anda por uma string e informa
onde está. Manter essa ignorância é proposital — é o que permite testá-lo
sozinho e o que evita import circular com ``Lexer.py``.

A regra de posição vem da seção 2.3 do enunciado: linha e coluna começam em 1,
consumir ``\\n`` incrementa a linha e devolve a coluna para 1, e qualquer outro
caractere — inclusive tabulação — incrementa a coluna em 1.
"""

from __future__ import annotations


class Cursor:
    """Aponta para uma posição do texto-fonte e sabe avançar sobre ela.

    Uso típico::

        cursor = Cursor("int x")
        cursor.espiar()      # 'i', sem consumir
        cursor.avancar()     # 'i', consumindo
        cursor.posicao()     # (1, 2)

    Não existe ``voltar()``, e isso é uma decisão de design, não um esquecimento.
    O algoritmo de maior prefixo do lexer (ver ``Lexer._rodar_automato``) olha
    adiante com ``espiar(n)`` sem consumir, e só depois consome exatamente o
    tanto que foi aceito. Sem retrocesso, o cursor nunca precisa desfazer
    contagem de linha ou coluna — o que seria a única parte realmente delicada.
    """

    def __init__(self, texto: str) -> None:
        self._texto = texto
        self._indice = 0
        self._linha = 1
        self._coluna = 1

    @property
    def linha(self) -> int:
        return self._linha

    @property
    def coluna(self) -> int:
        return self._coluna

    def posicao(self) -> tuple[int, int]:
        """Devolve ``(linha, coluna)`` do caractere ainda não consumido."""
        return self._linha, self._coluna

    def fim(self) -> bool:
        """Informa se todo o texto já foi consumido."""
        return self._indice >= len(self._texto)

    def espiar(self, adiante: int = 0) -> str:
        """Devolve o caractere ``adiante`` posições à frente, sem consumir.

        Fora do texto, devolve string vazia em vez de levantar exceção. Isso não
        é tolerância preguiçosa: string vazia nunca casa com nenhum símbolo da
        tabela de transições, então o fim do texto passa a se comportar
        naturalmente como "caractere sem transição". Quem chama pode perguntar
        "o que vem depois?" sem antes perguntar "ainda tem alguma coisa?".
        """
        indice = self._indice + adiante
        if indice >= len(self._texto):
            return ""
        return self._texto[indice]

    def avancar(self) -> str:
        """Consome um caractere, atualiza linha/coluna e o devolve.

        Chamar com o texto esgotado levanta ``IndexError``. Quem chama deve
        testar ``fim()`` antes — no lexer isso sempre acontece, porque cada
        rotina já precisa distinguir "acabou o texto" para reportar o erro
        certo.
        """
        caractere = self._texto[self._indice]
        self._indice += 1
        if caractere == "\n":
            self._linha += 1
            self._coluna = 1
        else:
            self._coluna += 1
        return caractere
