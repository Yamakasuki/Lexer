# Design — Analisador léxico do MicroC (Etapa 1)

**Data:** 2026-08-20
**Disciplina:** Compiladores — PUC-Campinas, 2s/2026, Prof. Lucas Reis
**Prazo da etapa:** 06/09/2026, 23h59 (Brasília)

## 1. Objetivo e escopo

Transformar o texto de um programa MicroC em uma sequência de `Token`, conforme o
contrato fixado pelo `ENUNCIADO.pdf`. O lexer recebe **texto**, nunca um caminho de
arquivo — quem lê o arquivo é o `runner.py`, que já vem pronto.

Está **fora** de escopo nesta etapa: análise sintática, análise semântica e validação
do limite numérico da linguagem. Uma sequência decimal maior que 2⁶³−1 continua sendo
`INT_LITERAL` válido aqui; quem reclama disso é a análise semântica, mais adiante.

### 1.1 O que não pode mudar

`TokenKind` (nomes e números), `Token` (campos e `__str__`), `LexerError` (atributos
`message`, `line`, `column`) e `runner.py` são intocáveis. O único ponto de extensão é
`Lexer.tokens()`, hoje um `raise NotImplementedError`.

Também é proibido usar SLY, PLY ou gerador equivalente, e é proibido delegar todo o
reconhecimento a uma coleção global de expressões regulares. A escolha, o consumo e o
avanço dos tokens têm de ser nossos.

## 2. Estratégia: por que mista

O enunciado (seção 5) aceita implementação manual, dirigida por tabela, ou mista.
Escolhemos **mista**, e a linha divisória não é arbitrária — ela segue uma diferença
real entre as categorias léxicas:

| Categoria | Reconhecida por | Razão |
|---|---|---|
| Identificadores, inteiros, operadores, delimitadores | **Autômato por tabela** | São linguagens regulares simples, e todas competem entre si pelo maior prefixo no mesmo ponto do texto. |
| Strings, comentários de linha, comentários de bloco | **Rotinas manuais** | Cada uma exige uma posição de erro que **não** é a posição corrente do autômato, e comentários sequer produzem token. |

O ponto central da segunda linha merece detalhe, porque é a justificativa inteira da
divisão. Veja o que o enunciado (seção 4) exige:

| Situação | Onde o erro deve ser reportado |
|---|---|
| `"abc` — EOF antes de fechar | na **aspa de abertura** |
| `"abc⏎` — quebra de linha na string | na **própria quebra** |
| `"\q"` — escape inválido | na **barra invertida** |
| `/* sem fim` — bloco não terminado | no **`/` inicial** |

Um autômato sabe apenas em que estado está *agora*. Para reportar "a aspa de abertura"
ele teria de carregar, por dentro da tabela, a posição onde o lexema começou e de que
tipo ele era — ou seja, empurrar estado extra pela máquina para depois desfazê-lo na
saída. Uma rotina manual guarda essa posição em uma variável local e acabou. Forçar
strings e comentários para dentro da tabela tornaria a tabela maior *e* o código de
erro pior; não há ganho a colher.

## 3. Arquitetura

### 3.1 Três módulos

```
microc_cursor.py     Cursor — navega o texto e rastreia linha/coluna.
                     Depende de: nada.

microc_automato.py   Estado, classificar(), TABELA_TRANSICOES, ESTADOS_ACEITADORES
                     e transicao(). Dados puros do autômato. Depende de: nada.

Lexer.py             Contrato público (TokenKind, Token, LexerError — intocados)
                     + PALAVRAS_RESERVADAS + ESTADO_PARA_TIPO
                     + class Lexer (orquestração, scanners manuais, munch máximo).
                     Depende de: os dois módulos acima.
```

`from Lexer import Lexer, LexerError, Token, TokenKind` continua funcionando, que é a
condição imposta pelo enunciado para usar módulos auxiliares.

### 3.2 A restrição que determinou esse desenho

`microc_automato.py` é **deliberadamente ignorante de `TokenKind`**. Se ele importasse
`TokenKind` de `Lexer.py`, e `Lexer.py` importasse o autômato, teríamos import
circular — o Python quebraria dependendo de qual módulo fosse carregado primeiro.

A saída é fazer o autômato falar apenas a língua dele: estados, símbolos e transições.
A tradução `Estado → TokenKind` mora em `Lexer.py`, onde `TokenKind` já vive. O efeito
colateral é bom: o módulo do autômato passa a ser testável sozinho, sem arrastar nada
do MicroC junto.

### 3.3 Fluxo de dados

```
texto-fonte
    │
    ▼
Lexer.tokens()  ──loop──►  _pular_ignoraveis()      espaços, //, /* */
    │                            │
    │                            ▼
    │                      fim do texto? ──sim──►  Token(EOF, "", None, linha, coluna)
    │                            │não
    │                            ▼
    │                      próximo char é '"' ? ──sim──►  _ler_string()      [manual]
    │                            │não
    │                            ▼
    └──────────────────────  _rodar_automato()                               [tabela]
```

## 4. `microc_cursor.py` — o Cursor

Responsabilidade única: saber onde estamos no texto e manter linha/coluna corretas.

```python
class Cursor:
    def __init__(self, texto: str) -> None
    @property
    def linha(self) -> int
    @property
    def coluna(self) -> int
    def fim(self) -> bool
    def espiar(self, adiante: int = 0) -> str   # '' quando passa do fim
    def avancar(self) -> str                    # consome 1 caractere e o devolve
    def posicao(self) -> tuple[int, int]        # (linha, coluna) atuais
```

**Regra de posição** (enunciado, seção 2.3): linha e coluna começam em 1. Consumir
`\n` incrementa a linha e devolve a coluna para 1. Qualquer outro caractere —
inclusive tabulação — incrementa a coluna em 1.

**`espiar()` devolve `''` no fim**, e não uma exceção, porque quase todo chamador quer
perguntar "o que vem depois?" sem antes perguntar "ainda tem alguma coisa?". String
vazia nunca casa com nada, então o fim do texto se comporta como um caractere que não
tem transição — exatamente a semântica desejada.

**O Cursor não tem `voltar()`.** Isso é intencional e a seção 6.2 explica como o munch
máximo funciona sem retrocesso de cursor.

**Sobre `\r`:** tratado como espaço em branco descartável, avançando coluna sem trocar
de linha. Na prática ele nunca chega aqui — `runner.py` lê em modo texto e o Python
normaliza `\r\n` para `\n`. A regra existe para quem construir `Lexer(...)` direto com
uma string lida de outra forma no Windows.

## 5. `microc_automato.py` — a tabela

### 5.1 Classificação de caracteres

Uma tabela indexada por *todo* caractere possível seria enorme e ilegível. Em vez
disso, cada caractere vira um **símbolo**:

```python
def classificar(c: str) -> str:
    if c.isascii() and (c.isalpha() or c == "_"):
        return "LETRA"
    if c.isascii() and c.isdigit():
        return "DIGITO"
    return c            # o próprio caractere, para operadores e delimitadores
```

Letras e dígitos colapsam em duas classes (é o que identificadores e inteiros
precisam); operadores continuam sendo eles mesmos, porque `<` e `>` levam a estados
diferentes. Não há colisão possível: uma chave literal é sempre um caractere único, e
nenhum caractere único é a string `"LETRA"`.

O `isascii()` importa: sem ele, `Lexer("é")` classificaria `é` como `LETRA` (porque
`"é".isalpha()` é `True` em Python) e produziria um identificador — violando a regra de
que o fonte MicroC é ASCII. Com ele, `é` devolve `"é"`, que não tem transição nenhuma,
e o erro cai naturalmente onde deve.

### 5.2 Estados

| Estado | Aceita? | Token |
|---|---|---|
| `INICIO` | não | — |
| `IDENT` | sim | `IDENTIFIER` (sujeito à consulta de palavras reservadas) |
| `INT` | sim | `INT_LITERAL` |
| `MAIS` `MENOS` `ASTERISCO` `BARRA` `PORCENTO` | sim | `PLUS` `MINUS` `STAR` `SLASH` `PERCENT` |
| `MENOR` / `MENOR_IGUAL` | sim | `LESS` / `LESS_EQUAL` |
| `MAIOR` / `MAIOR_IGUAL` | sim | `GREATER` / `GREATER_EQUAL` |
| `IGUAL` / `IGUAL_IGUAL` | sim | `ASSIGN` / `EQUAL_EQUAL` |
| `EXCLAMACAO` / `EXCLAMACAO_IGUAL` | sim | `LOGICAL_NOT` / `NOT_EQUAL` |
| `E_COMERCIAL` | **não** | — |
| `E_LOGICO` | sim | `LOGICAL_AND` |
| `BARRA_VERTICAL` | **não** | — |
| `OU_LOGICO` | sim | `LOGICAL_OR` |
| `ABRE_PARENTESE` `FECHA_PARENTESE` `ABRE_CHAVE` `FECHA_CHAVE` `VIRGULA` `PONTO_VIRGULA` | sim | `LEFT_PAREN` … `SEMICOLON` |

As duas linhas em negrito carregam a regra "ocorrências isoladas de `&` ou `|` são
erros léxicos" (enunciado, seção 3.4) **como propriedade do autômato**, não como um
`if`: `E_COMERCIAL` é alcançável mas não aceitador, logo um `&` solitário termina a
caminhada sem nenhum estado aceitador visitado — e a seção 6.2 mostra que isso é
precisamente a condição de erro.

### 5.3 Transições

```
INICIO   LETRA→IDENT   DIGITO→INT
         '+'→MAIS   '-'→MENOS   '*'→ASTERISCO   '/'→BARRA   '%'→PORCENTO
         '<'→MENOR  '>'→MAIOR   '='→IGUAL       '!'→EXCLAMACAO
         '&'→E_COMERCIAL        '|'→BARRA_VERTICAL
         '('→ABRE_PARENTESE     ')'→FECHA_PARENTESE
         '{'→ABRE_CHAVE         '}'→FECHA_CHAVE
         ','→VIRGULA            ';'→PONTO_VIRGULA

IDENT          LETRA→IDENT   DIGITO→IDENT
INT            DIGITO→INT
MENOR          '='→MENOR_IGUAL
MAIOR          '='→MAIOR_IGUAL
IGUAL          '='→IGUAL_IGUAL
EXCLAMACAO     '='→EXCLAMACAO_IGUAL
E_COMERCIAL    '&'→E_LOGICO
BARRA_VERTICAL '|'→OU_LOGICO
```

Estados sem linha própria são finais: não sai transição deles.

O módulo expõe a consulta como função, para que `Lexer.py` não precise conhecer o
formato interno da tabela:

```python
def transicao(estado: Estado, simbolo: str) -> Estado | None:
    """Estado seguinte, ou None se a caminhada trava aqui."""
    return TABELA_TRANSICOES.get(estado, {}).get(simbolo)
```

**Por que `BARRA` (`/`) é um estado normal:** quando o autômato roda, `_pular_ignoraveis`
já descartou `//` e `/*`. Uma barra que chega até aqui é necessariamente o operador de
divisão. Comentário nunca compete com `SLASH` porque eles nem se encontram.

## 6. `Lexer.py` — orquestração

### 6.1 Laço principal

```python
def tokens(self) -> Iterator[Token]:
    while True:
        self._pular_ignoraveis()
        if self._cursor.fim():
            yield Token(TokenKind.EOF, "", None, *self._cursor.posicao())
            return
        if self._cursor.espiar() == '"':
            yield self._ler_string()
        else:
            yield self._rodar_automato()
```

O `return` logo após o `EOF` é o que garante o item 5 do checklist do enunciado
("todos os caminhos terminam em um único EOF").

A posição do `EOF` sai de graça: como `_pular_ignoraveis()` roda **antes** do teste de
fim, o cursor já está depois de todo espaço e comentário final. Confira contra os
casos do teste público:

| Fonte | Cursor após ignoráveis | EOF esperado |
|---|---|---|
| `""` (vazio) | linha 1, coluna 1 | (1, 1) ✓ |
| `"x"` | linha 1, coluna 2 | (1, 2) ✓ |
| `"x\n"` | linha 2, coluna 1 | (2, 1) ✓ |
| `"/* ok */"` | linha 1, coluna 9 | (1, 9) ✓ |

### 6.2 Munch máximo sem retroceder o cursor

O algoritmo clássico caminha consumindo caracteres, memoriza o último estado aceitador
e **retrocede** o cursor quando trava. Retroceder exigiria desfazer linha/coluna, o que
complicaria o Cursor por um ganho nenhum.

Fazemos o contrário: **olhamos adiante sem consumir**, e só no fim consumimos
exatamente o tanto que foi aceito.

```python
def _rodar_automato(self) -> Token:
    linha, coluna = self._cursor.posicao()
    estado = Estado.INICIO
    adiante = 0
    ultimo_aceitador: Estado | None = None
    tamanho_aceito = 0

    while True:
        caractere = self._cursor.espiar(adiante)
        if caractere == "":
            break                                   # fim do texto: não há transição
        proximo = transicao(estado, classificar(caractere))
        if proximo is None:
            break                                   # a caminhada travou
        estado = proximo
        adiante += 1
        if estado in ESTADOS_ACEITADORES:
            ultimo_aceitador = estado
            tamanho_aceito = adiante                # memoriza o maior prefixo válido

    if ultimo_aceitador is None:
        raise LexerError(self._mensagem_de_erro(), linha, coluna)

    lexema = "".join(self._cursor.avancar() for _ in range(tamanho_aceito))
    return self._montar_token(ultimo_aceitador, lexema, linha, coluna)
```

Três exigências do enunciado que este laço satisfaz **sem caso especial**:

- **`<=` vence `<`.** A caminhada simplesmente vai mais longe, e `tamanho_aceito` é
  sobrescrito. Vale igual para `>=`, `==`, `!=`, `&&`, `||`.
- **`1abc` são dois tokens.** `INT` aceita `1`; o `a` não tem transição saindo de
  `INT`, a caminhada trava, e consumimos só o `1`. A chamada seguinte começa em `abc`.
  Mesmo mecanismo para `0xff` → `INT_LITERAL(0)` + `IDENTIFIER("xff")`.
- **`&` isolado é erro na coluna certa.** `E_COMERCIAL` não é aceitador, então
  `ultimo_aceitador` continua `None` e o erro usa `linha, coluna` — capturados **antes**
  da caminhada, portanto apontando o início do lexema.

### 6.3 Montagem do token

```python
PALAVRAS_RESERVADAS = {
    "int": KW_INT, "bool": KW_BOOL, "void": KW_VOID, "true": KW_TRUE,
    "false": KW_FALSE, "if": KW_IF, "else": KW_ELSE, "while": KW_WHILE,
    "return": KW_RETURN, "print": KW_PRINT,
}
```

A consulta acontece **depois** de consumir o identificador inteiro, como manda a seção
3.1 do enunciado. É isso que faz `intx`, `true1` e `_int` serem `IDENTIFIER`: o maior
prefixo é o identificador completo, e só ele é procurado na tabela. Como a busca é em
um `dict` comum, `While` não casa com `while` — a distinção entre maiúsculas e
minúsculas é herdada da comparação de strings do Python, sem código extra.

Valores por categoria (enunciado, seção 2.2):

| Categoria | `value` |
|---|---|
| `IDENTIFIER` | o próprio lexema |
| `INT_LITERAL` | `int(lexema)` — `"0042"` vira `42`, e os zeros sobrevivem só no lexema |
| `STRING_LITERAL` | conteúdo decodificado, sem aspas |
| `KW_TRUE` / `KW_FALSE` | `True` / `False` |
| demais | `None` |

### 6.4 `_pular_ignoraveis()` — espaços e comentários

Um único laço, porque as três coisas se alternam livremente
(`" \t// x\n/* y */ z"`):

```
repita:
    espaço, tab, \n ou \r      → consome, continua
    '/' seguido de '/'         → consome até \n (exclusive) ou fim, validando
                                 ASCII de cada caractere; continua
    '/' seguido de '*'         → consome bloco (abaixo), continua
    qualquer outra coisa       → para
```

O comentário de linha **pode terminar no EOF** sem `\n` — é o teste
`test_comentario_de_linha_pode_terminar_no_eof`. Ele não consome o `\n`; deixa para a
iteração seguinte do laço, que o trata como espaço em branco e atualiza a linha.

O comentário de bloco guarda a posição do `/` inicial antes de consumir qualquer coisa:

```
inicio = cursor.posicao()          # posição do '/' — usada se der erro
consome '/', '*'
repita:
    se fim            → LexerError("comentário de bloco não terminado", *inicio)
    se não ASCII      → LexerError("caractere não ASCII", *cursor.posicao())
    se '*' seguido de '/' → consome os dois e termina
    senão             → consome um caractere
```

Blocos **não aninham** (enunciado, seção 3.2): terminamos no primeiro `*/`, sem contar
níveis. Note que `/*/` não fecha — depois de consumir `/*`, sobra apenas `/`, e nunca
aparece o par `*/`.

A validação ASCII dentro do comentário não é zelo excessivo: o enunciado diz
explicitamente que "caracteres não ASCII continuam inválidos mesmo quando aparecem
dentro de comentários".

### 6.5 `_ler_string()`

```
linha, coluna = cursor.posicao()   # a ASPA DE ABERTURA — guardada antes de tudo
consome a aspa
repita:
    se fim             → LexerError("string não terminada", linha, coluna)
    se caractere '\n'  → LexerError("quebra de linha em string", *cursor.posicao())
    se não ASCII       → LexerError("caractere não ASCII", *cursor.posicao())
    se caractere '"'   → consome e termina
    se caractere '\\'  → posicao_barra = cursor.posicao()
                         consome a barra
                         se fim → LexerError("string não terminada", linha, coluna)
                         se o próximo não está em ESCAPES
                             → LexerError("escape inválido", *posicao_barra)
                         consome, acumula no lexema a grafia e no valor o decodificado
    senão              → consome, acumula em ambos
```

Três posições de erro diferentes, cada uma capturada no momento certo — é exatamente
por isso que esta rotina não está no autômato.

```python
ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
```

Qualquer outro escape é erro. O **lexema preserva a grafia original** (com as aspas e a
barra invertida literal) enquanto o **valor guarda o caractere decodificado** — a
distinção que o teste `test_strings_preservam_lexema_e_decodificam_escapes` verifica.

Marcadores de comentário dentro de string são só conteúdo (`"// nao e comentario"`
é uma string, não um comentário) — o que sai de graça, porque `_pular_ignoraveis`
nunca roda no meio de uma string.

## 7. Erros

Todos os erros são `LexerError`, com `message`, `line`, `column`. A redação da
mensagem é livre; a **classe e a posição** é que são verificadas.

| Situação | Posição |
|---|---|
| Caractere que não inicia token (`@`) | o caractere |
| Caractere não ASCII (`é`), inclusive em comentário | o caractere |
| `&` ou `|` isolados | o caractere |
| Escape inválido em string | a **barra invertida** |
| Quebra de linha em string | a **quebra** |
| EOF dentro de string | a **aspa de abertura** |
| Comentário de bloco não terminado | o **`/` inicial** |

`tokens()` é um gerador, mas `scan()` materializa tudo em lista antes de devolver.
É isso que faz o `runner.py` cumprir o item 6 do checklist ("erros não deixam tokens
parciais em stdout"): a exceção estoura dentro de `scan()`, antes de qualquer `print`.
Não precisamos fazer nada de especial — só não capturar a exceção no caminho.

## 8. Testes

**Alvo primário:** os 13 testes públicos de `tests/test.py`, que não serão alterados.

**Testes próprios:** um arquivo novo `tests/test_extras.py` (o `pyproject.toml` já
coleta `test_*.py`) cobrindo casos que os públicos não exercitam mas os ocultos podem:

- `Cursor` isolado — linha/coluna após tabulação, `\n`, sequências mistas
- `microc_automato` isolado — transições e conjunto de aceitadores
- comentário de bloco fechando imediatamente (`/**/`), e `/*/` que **não** fecha
- não ASCII dentro de comentário de linha e de bloco
- string terminando com barra invertida antes do EOF
- todas as palavras reservadas, e cada uma com sufixo (`ifx`, `elsee`)
- inteiro maior que 2⁶³−1
- todos os operadores e delimitadores, um a um

**Método:** TDD. Para cada comportamento, rodar o teste que falha, implementar o
mínimo, ver passar. Os testes públicos já falham hoje com `NotImplementedError` — eles
são a lista de pendências inicial.

**Ambiente:** o CI roda Python 3.12; a máquina local tem 3.14.4. Nada no design usa
recurso posterior ao 3.10 (`X | Y` em anotação já está protegido por
`from __future__ import annotations`, que o starter traz).

## 9. Entrega

Desenvolvimento no fork `origin` (`Yamakasuki/Lexer`). O remote `classroom`
(`PUC-Campinas-Compiladores-2s26/Lexer`) **só recebe push com aval explícito** — e é
ele que vale a nota: o enunciado diz que entrega por outro canal não substitui a do
Classroom. O upstream do branch aponta para `origin`, então `git push` sem argumentos
é seguro.

Antes do push final, revalidar o checklist da seção 8 do enunciado, com destaque para:
`TokenKind`/`Token`/formato de saída inalterados, um único `EOF` em todos os caminhos,
e nenhum arquivo desnecessário no repositório.
