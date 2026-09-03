# Guia introdutório — Lexer do MicroC (Etapa 1)

> Este documento assume que você nunca viu este projeto. Ele parte do zero: o
> que foi pedido, os conceitos necessários para ler o código, e depois cada
> arquivo, bloco a bloco, com exemplos de execução passo a passo.
>
> Para o *porquê* condensado das decisões de design, veja também
> [`IMPLEMENTACAO.md`](IMPLEMENTACAO.md) e
> [`superpowers/specs/2026-08-20-lexer-microc-design.md`](superpowers/specs/2026-08-20-lexer-microc-design.md).
> Este guia é mais longo e didático de propósito — é o ponto de entrada para
> quem está vendo o projeto pela primeira vez.

## Sumário

1. [Contexto: o que é este projeto](#1-contexto-o-que-é-este-projeto)
2. [O que foi pedido (o enunciado)](#2-o-que-foi-pedido-o-enunciado)
3. [O que veio pronto vs. o que foi implementado](#3-o-que-veio-pronto-vs-o-que-foi-implementado)
4. [Conceitos necessários antes do código](#4-conceitos-necessários-antes-do-código)
5. [Mapa da solução](#5-mapa-da-solução)
6. [`microc_cursor.py`, bloco a bloco](#6-microc_cursorpy-bloco-a-bloco)
7. [`microc_automato.py`, bloco a bloco](#7-microc_automatopy-bloco-a-bloco)
8. [`Lexer.py`, bloco a bloco](#8-lexerpy-bloco-a-bloco)
9. [Exemplo ponta a ponta: `int x = 42;`](#9-exemplo-ponta-a-ponta-int-x--42)
10. [Como rodar e testar](#10-como-rodar-e-testar)
11. [Conformidade com o enunciado](#11-conformidade-com-o-enunciado)
12. [Decisões que valem atenção](#12-decisões-que-valem-atenção)

---

## 1. Contexto: o que é este projeto

Este é o **Projeto MicroC — Etapa 1**, da disciplina de Compiladores (PUC
Campinas, 2s/2026). MicroC é uma linguagem de programação pequena, inventada
para o curso, parecida com um subconjunto de C (`int`, `bool`, `if`, `while`,
`print`, operadores aritméticos/relacionais/lógicos, etc.).

Um compilador é construído em etapas. Esta é a primeira: o **analisador
léxico** (ou *lexer*). O pipeline completo do projeto é:

```
arquivo .microc → texto-fonte → Lexer → sequência de Token → (próximas etapas: parser, semântica, ...)
```

**O que um lexer faz, em uma frase:** ele lê o texto-fonte caractere a
caractere e o transforma em uma lista de "palavras" com significado —
chamadas **tokens** — descartando pelo caminho tudo que é só formatação
(espaços, comentários). É a mesma ideia de segmentar uma frase em palavras
antes de analisar sua gramática: o parser (próxima etapa, fora do escopo
desta) vai trabalhar em cima da lista de tokens, nunca do texto bruto.

Por exemplo, o texto-fonte:

```c
int x = 42;
```

vira a sequência de tokens (cada um sabendo seu tipo, seu texto original, seu
valor interpretado, e onde no arquivo ele começa):

```
<10, KW_INT, 'int', None, 1, 1>
<1, IDENTIFIER, 'x', 'x', 1, 5>
<34, ASSIGN, '=', None, 1, 7>
<2, INT_LITERAL, '42', 42, 1, 9>
<45, SEMICOLON, ';', None, 1, 11>
<-1, EOF, '', None, 2, 1>
```

Note que os espaços entre `int`, `x`, `=` e `42` **não geram token nenhum** —
eles só servem para separar os tokens vizinhos, e desaparecem depois de
cumprir esse papel.

---

## 2. O que foi pedido (o enunciado)

O `ENUNCIADO.pdf` na raiz do repositório é o documento oficial. Aqui vai o
resumo do que ele exige, seção por seção — a "prova" que o código precisa
passar.

### 2.1 O enum `TokenKind` é fixo

O enunciado define **exatamente** estes tokens, com estes números — eles são
uma interface pública que a próxima etapa (parser) vai consumir, então não
podem ser escolhidos livremente pelo grupo:

| Categoria | Membros | Números |
|---|---|---|
| Especiais | `EOF` | -1 |
| Literais/identificador | `IDENTIFIER`, `INT_LITERAL`, `STRING_LITERAL` | 1–3 |
| Palavras reservadas | `KW_INT`, `KW_BOOL`, `KW_VOID`, `KW_TRUE`, `KW_FALSE`, `KW_IF`, `KW_ELSE`, `KW_WHILE`, `KW_RETURN`, `KW_PRINT` | 10–19 |
| Operadores | `PLUS` `MINUS` `STAR` `SLASH` `PERCENT` `LESS` `LESS_EQUAL` `GREATER` `GREATER_EQUAL` `EQUAL_EQUAL` `NOT_EQUAL` `LOGICAL_AND` `LOGICAL_OR` `LOGICAL_NOT` `ASSIGN` | 20–34 |
| Delimitadores | `LEFT_PAREN` `RIGHT_PAREN` `LEFT_BRACE` `RIGHT_BRACE` `COMMA` `SEMICOLON` | 40–45 |

**Não existe token para espaço, quebra de linha ou comentário** — o
enunciado é explícito: esses elementos são consumidos e descartados antes do
próximo token.

### 2.2 A estrutura `Token`

```python
@dataclass(frozen=True)
class Token:
    kind: TokenKind
    lexeme: str
    value: int | str | bool | None
    line: int
    column: int
```

- `lexeme` é a grafia **exata** do token no fonte (ex.: para o literal `0042`,
  o lexeme é a string `"0042"`, com os zeros).
- `value` é a interpretação do lexeme, só quando faz sentido ter uma:
  - `IDENTIFIER` → o próprio nome, como string;
  - `INT_LITERAL` → o inteiro Python correspondente (`"0042"` → `42`, zero à
    esquerda desaparece só no *value*, o lexeme continua com eles);
  - `STRING_LITERAL` → o conteúdo decodificado, sem aspas;
  - `KW_TRUE` / `KW_FALSE` → `True` / `False` (bool do Python);
  - todos os outros → `None`.
- `frozen=True` significa **imutável**: depois de criado, um `Token` não pode
  ter nenhum campo reatribuído (tentar isso lança
  `dataclasses.FrozenInstanceError`).

### 2.3 Posições (linha e coluna)

- Ambas começam em **1**.
- Cada espaço/tab avança a coluna em 1.
- Uma quebra `\n` avança a linha e **reinicia a coluna em 1**.
- Linha/coluna de um token apontam para o **primeiro caractere do lexema**.
- O `EOF` tem lexema vazio, valor `None`, e fica na posição **imediatamente
  depois do último caractere real**. Duas consequências diretas:
  - entrada vazia → `EOF` em `1:1`;
  - entrada terminada em `\n` → `EOF` na linha seguinte, coluna 1.
- O `runner.py` (fornecido, não implementado pelo grupo) já lê o arquivo em
  modo texto, o que normaliza `\r\n`/`\r` para `\n` antes do lexer ver
  qualquer coisa.

### 2.4 Regras de reconhecimento

- **Maior prefixo ("maximal munch"):** em cada posição, o lexer deve
  consumir o **maior** trecho de texto que ainda forma um token válido. É
  por isso que `<=` precisa vencer `<`, `==` vencer `=`, `&&` vencer um `&`
  solto, etc. — todos são exigidos explicitamente pelo enunciado.
- **Identificadores:** `[A-Za-z_][A-Za-z0-9_]*`. Depois de consumir o
  identificador **inteiro**, consulta-se a tabela de palavras reservadas.
  Há distinção entre maiúsculas/minúsculas: `while` é palavra reservada,
  `While` é `IDENTIFIER`.
- **Inteiros:** só dígitos decimais. O sinal **não** faz parte do literal —
  `-10` é dois tokens (`MINUS` + `INT_LITERAL 10`). Zero à esquerda não muda
  a base (`0042` é decimal 42). `0b101` **não** é um literal especial de
  outra base — lexicamente é `INT_LITERAL 0` seguido de `IDENTIFIER b101`.
- **Espaços/comentários:** espaço, tab e `\n` separam tokens e são
  descartados. `//` inicia comentário de linha (até `\n` ou EOF). `/* ... */`
  inicia comentário de bloco, que **não aninha** e termina no primeiro `*/`.
  EOF dentro de um bloco é erro léxico.
- **Strings:** o `lexeme` inclui as aspas e os escapes tal como escritos; o
  `value` exclui as aspas e decodifica os escapes. Só 4 escapes existem:
  `\n`, `\t`, `\"`, `\\` — qualquer outro é erro. Quebra de linha ou EOF
  antes de fechar a string também é erro. Um `//` ou `/*` **dentro** de uma
  string é só conteúdo, não inicia comentário. Duas strings adjacentes (como
  em `print("a" "b")`) geram **dois tokens** — concatená-las é trabalho do
  parser, numa etapa futura.
- **Caracteres inválidos:** o fonte é ASCII. Caractere não-ASCII, caractere
  que não inicia nenhum token, e ocorrências **isoladas** de `&` ou `|` (sem
  o par completar `&&`/`||`) são todos erro léxico — o lexer nunca pode
  ignorar silenciosamente um caractere inválido.

### 2.5 Erros

- Representados pela exceção `LexerError(message, line, column)`, com
  `str(erro)` no formato `erro léxico em linha:coluna: descrição`.
- Posições exigidas para casos específicos:

  | Situação | Posição do erro |
  |---|---|
  | String não terminada (EOF antes do fechamento) | a aspa de **abertura** |
  | Quebra de linha dentro de string | a própria quebra |
  | Escape inválido | a barra invertida |
  | Comentário de bloco não terminado | o `/` **inicial** |

- O `runner.py`: roda `Lexer(source).scan()`; se der erro, **não** imprime
  tokens parciais — escreve o diagnóstico em `stderr` e sai com código 1.
  Erros de uso (argumentos errados) ou leitura de arquivo saem com código 2.

### 2.6 Estratégias permitidas

O enunciado aceita três abordagens de organização interna — o resultado
final é fixo, a estrutura interna é escolha do grupo:

- **manual** — decisões e laços explícitos por categoria;
- **dirigida por tabela** — autômato com estados/transições como estrutura
  de dados;
- **mista** — autômato para as categorias regulares, rotinas manuais para o
  que for conveniente.

**Proibido:** usar gerador de lexer pronto (SLY, PLY ou equivalente), ou
delegar todo o reconhecimento a uma coleção global de expressões regulares.

### 2.7 Formato de saída

```
<numero, NOME, repr(lexeme), repr(value), linha, coluna>
```

`repr()` só é usado na hora de **imprimir** (não é campo do `Token`) — ele
garante que aspas, barras e quebras de linha dentro do lexema/valor fiquem
visíveis numa única linha de saída, em vez de quebrar a formatação.

---

## 3. O que veio pronto vs. o que foi implementado

O "starter" (material inicial fornecido) já trazia:

| Arquivo | O que já vinha pronto |
|---|---|
| `Lexer.py` | O enum `TokenKind`, a dataclass `Token`, a exceção `LexerError`, e as assinaturas de `Lexer.__init__`/`tokens()`/`scan()` — **vazias**, com `raise NotImplementedError` no lugar do reconhecimento. |
| `runner.py` | Completo — lê o arquivo, chama o lexer, imprime ou reporta erro. **Não podia ser alterado.** |
| `tests/test.py` | 24 testes públicos em pytest, cobrindo o contrato inteiro. **Não podia ser alterado.** |
| `test.microc` | Um programa de exemplo pequeno. |
| `README.md`, `requirements-dev.txt`, `pyproject.toml`, `.github/workflows/classroom.yml` | Configuração de ambiente e CI. |

O que o grupo **implementou** (esta branch):

| Arquivo | Conteúdo |
|---|---|
| `microc_cursor.py` | **Novo.** Navegação sobre o texto-fonte com contagem de linha/coluna. |
| `microc_automato.py` | **Novo.** Estados, classificação de caracteres e tabela de transições do autômato. |
| `Lexer.py` | O corpo de `Lexer.__init__`/`tokens()` mais todas as rotinas privadas de reconhecimento. `TokenKind`, `Token` e `LexerError` continuam **exatamente** como vieram (é proibido mudá-los). |

A confirmação de que `runner.py`, `tests/test.py` e `test.microc` não foram
tocados está no histórico do git (`git diff <commit-inicial> <commit-final>`
não lista esses arquivos).

---

## 4. Conceitos necessários antes do código

Se algum destes termos for novo, vale ler esta seção antes da 6–8 — o código
usa todos eles.

### Autômato finito, estado, transição

Um **autômato finito** é uma máquina abstrata com um número fixo de
**estados** (posições em que ela pode estar) e **transições** (regras do
tipo "se eu estou no estado A e o próximo caractere é X, eu vou para o
estado B"). Ela sempre começa num estado inicial e "anda" consumindo
caracteres um a um.

Exemplo bem pequeno — reconhecer só o operador `<=`:

```
estado MENOR ---'='---> estado MENOR_IGUAL
   ^
   |
'<' (a partir do estado INICIO)
```

Um **estado aceitador** é um estado em que, se a entrada acabar ali, o que
foi consumido até agora forma um token válido. No exemplo acima, tanto
`MENOR` (depois de só `<`) quanto `MENOR_IGUAL` (depois de `<=`) são
aceitadores — é isso que permite `<` sozinho ser um token válido (`LESS`) e
`<=` também (`LESS_EQUAL`).

### Maior prefixo ("maximal munch")

Quando mais de um estado aceitador é alcançável a partir da mesma posição
(como no exemplo acima), a regra do enunciado (§3.1) é: vence o **mais
longo**. Por isso `<=` (2 caracteres) tem prioridade sobre `<` (1 caractere)
— não é um caso especial de código, é uma regra geral que qualquer autômato
"guloso" (que sempre tenta ir mais longe antes de decidir) satisfaz
naturalmente.

### Lookahead vs. backtracking

Existem duas formas clássicas de implementar maior prefixo:

- **Backtracking (retroceder):** consome caractere a caractere avançando o
  cursor de verdade; quando trava, "desfaz" (volta) até o último ponto em
  que era um token válido. Problema: desfazer exige desfazer também a
  contagem de linha/coluna, que é chata de reverter corretamente (uma
  quebra de linha consumida por engano precisa "devolver" a coluna certa).
- **Lookahead (espiar adiante):** só *olha* os próximos caracteres sem
  consumi-los de verdade (`espiar(n)`), guardando qual foi o último ponto
  aceitador visto. Só no final, decide quanto consumir de fato.

Este projeto usa lookahead — é por isso que `Cursor` (seção 6) não tem
método `voltar()`: ele nunca precisa desfazer nada, porque nunca consome
"a mais" para começar.

### `enum.Enum`

Um jeito de dar nomes a um conjunto fixo de valores relacionados (como
`TokenKind.KW_INT` valendo `10`). Cada membro é único e comparável por
identidade (`is`).

### `@dataclass(frozen=True)`

Gera automaticamente `__init__`, `__eq__`, `__repr__` etc. para uma classe
que só guarda dados. `frozen=True` bloqueia reatribuição de campos depois de
criado — é o que torna `Token` imutável, como o enunciado exige.

### Geradores (`yield`)

Uma função com `yield` no corpo não roda tudo de uma vez: cada `yield`
"pausa" a função e devolve um valor para quem está iterando, retomando de
onde parou na próxima iteração. `Lexer.tokens()` é assim: produz um `Token`
por vez, sob demanda, em vez de montar a lista inteira antes de devolver
qualquer coisa.

---

## 5. Mapa da solução

A estratégia escolhida foi a **mista** (uma das três permitidas pelo
enunciado, §5):

```
                    ┌─────────────────────┐
                    │   microc_cursor.py   │   Cursor: anda pelo texto,
                    │   (sem dependências) │   conta linha/coluna.
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  microc_automato.py   │   Estado, classificar(),
                    │  (sem dependências)   │   tabela de transições.
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │       Lexer.py        │   TokenKind/Token/LexerError
                    │                       │   (contrato, intocado) +
                    │                       │   orquestração + rotinas
                    │                       │   manuais (strings, comentários)
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │      runner.py        │   Lê arquivo, chama o lexer,
                    │      (starter)        │   imprime ou reporta erro.
                    └───────────────────────┘
```

A divisão entre "o que vai no autômato" e "o que vira rotina manual" segue
um critério concreto, não gosto pessoal:

| Categoria | Onde mora | Motivo |
|---|---|---|
| Identificadores, inteiros, operadores, delimitadores | **Autômato** (`microc_automato.py`) | São linguagens regulares simples, cujo reconhecimento é só "andar de estado em estado". |
| Strings, comentários | **Rotina manual** (dentro de `Lexer.py`) | Cada uma precisa reportar erro numa posição que **não é** a posição corrente do autômato (tabela da seção 2.5) — ex.: erro de escape aponta para a barra invertida, não para onde o autômato "está" no momento do erro. Carregar essas posições dentro da tabela de transições exigiria empurrar estado extra pela máquina só para desfazer depois; uma variável local numa função comum resolve direto. |

**Por que `microc_automato.py` não importa `TokenKind`:** se ele
importasse `TokenKind` de `Lexer.py`, e `Lexer.py` importasse o autômato de
volta, teríamos um **import circular** (Python trava, porque cada módulo
depende do outro terminar de carregar primeiro). A solução foi manter o
autômato falando só a própria língua — `Estado`, símbolos, transições — sem
saber que "token" existe. A tradução `Estado → TokenKind` mora em
`Lexer.py`, o único lugar onde os dois conceitos podem coexistir.

---

## 6. `microc_cursor.py`, bloco a bloco

Este módulo não sabe nada sobre MicroC — só sabe andar por uma `string`
genérica e informar linha/coluna. É a camada mais baixa de toda a solução.

```python
class Cursor:
    def __init__(self, texto: str) -> None:
        self._texto = texto
        self._indice = 0
        self._linha = 1
        self._coluna = 1
```

Guarda o texto inteiro, um índice (posição atual, começando em 0 — índice
interno de string em Python, diferente de linha/coluna que começam em 1
para o usuário), e a posição "humana" atual.

```python
    def posicao(self) -> tuple[int, int]:
        return self._linha, self._coluna

    def fim(self) -> bool:
        return self._indice >= len(self._texto)
```

`posicao()` devolve onde está o *próximo* caractere a ser lido (ainda não
consumido). `fim()` diz se já não sobra nada.

```python
    def espiar(self, adiante: int = 0) -> str:
        indice = self._indice + adiante
        if indice >= len(self._texto):
            return ""
        return self._texto[indice]
```

`espiar(n)` olha o caractere `n` posições à frente **sem consumir nada**.
`espiar()` (sem argumento) é o caractere atual. Se `n` cair fora do texto,
devolve `""` em vez de lançar erro — decisão deliberada: `""` nunca vai
casar com nenhum símbolo válido na tabela de transições do autômato, então
"acabou o texto" já se comporta sozinho como "não há transição daqui", sem
precisar de um `if self._cursor.fim()` extra espalhado por todo lugar que
usa `espiar`.

```python
    def avancar(self) -> str:
        caractere = self._texto[self._indice]
        self._indice += 1
        if caractere == "\n":
            self._linha += 1
            self._coluna = 1
        else:
            self._coluna += 1
        return caractere
```

`avancar()` é o único método que **de fato consome** um caractere — atualiza
linha/coluna conforme a regra do enunciado (§2.3) e devolve o caractere
consumido. Chamar com o texto já esgotado lança `IndexError` — por design:
quem chama sempre já testou `fim()` antes, então esse caso nunca deveria
acontecer na prática.

Note que **não existe `voltar()`**. Isso é intencional (ver seção 4,
lookahead vs. backtracking): o algoritmo de maior prefixo do lexer usa só
`espiar()` para decidir até onde ir, e só chama `avancar()` a quantidade
exata de vezes necessária no final. O cursor nunca "erra para frente" e
precisa se corrigir.

---

## 7. `microc_automato.py`, bloco a bloco

Este módulo define o autômato propriamente dito: estados, como classificar
um caractere, e a tabela de transições.

```python
class Estado(enum.Enum):
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
```

`INICIO` é o único ponto de partida de qualquer token. Todos os outros
estados são alcançados consumindo algum caractere a partir de outro estado.
Repare que existe um estado por *situação*, não por *token final* — por
exemplo, `MENOR` (só `<` até agora) e `MENOR_IGUAL` (já `<=`) são estados
diferentes porque o autômato precisa saber, a cada passo, exatamente onde
está.

```python
LETRA = "LETRA"
DIGITO = "DIGITO"

def classificar(caractere: str) -> str:
    if caractere.isascii() and (caractere.isalpha() or caractere == "_"):
        return LETRA
    if caractere.isascii() and caractere.isdigit():
        return DIGITO
    return caractere
```

A tabela de transições não indexa por *caractere exato* nos casos de
identificador/inteiro (senão precisaria de 26+26+10+1 entradas repetidas
para cada letra/dígito possível). Em vez disso, `classificar()` reduz
qualquer letra ASCII ou `_` ao símbolo genérico `LETRA`, e qualquer dígito
ASCII ao símbolo `DIGITO`. Para todo o resto (operadores, delimitadores,
caracteres inválidos), devolve o próprio caractere — já que `<`, `>`, `(`
etc. levam cada um a um estado diferente e não fazem sentido colapsar.

O `isascii()` antes de `isalpha()`/`isdigit()` não é redundância: em Python,
`"é".isalpha()` é `True` (Python reconhece letras acentuadas como letras
Unicode). Sem esse teste, `é` seria classificado como `LETRA` e viraria
identificador — violando a regra do enunciado de que o fonte é só ASCII
(§3.4). Com o teste, `é` não casa com `LETRA` nem `DIGITO`, cai no `return
caractere` (devolve `"é"` mesmo), que não é chave de nenhuma transição — o
autômato trava sem aceitar nada, e o erro léxico certo acontece sozinho.

```python
TABELA_TRANSICOES: dict[Estado, dict[str, Estado]] = {
    Estado.INICIO: {
        LETRA: Estado.IDENT,
        DIGITO: Estado.INT,
        "+": Estado.MAIS, "-": Estado.MENOS, "*": Estado.ASTERISCO,
        "/": Estado.BARRA, "%": Estado.PORCENTO,
        "<": Estado.MENOR, ">": Estado.MAIOR, "=": Estado.IGUAL, "!": Estado.EXCLAMACAO,
        "&": Estado.E_COMERCIAL, "|": Estado.BARRA_VERTICAL,
        "(": Estado.ABRE_PARENTESE, ")": Estado.FECHA_PARENTESE,
        "{": Estado.ABRE_CHAVE, "}": Estado.FECHA_CHAVE,
        ",": Estado.VIRGULA, ";": Estado.PONTO_VIRGULA,
    },
    Estado.IDENT: {LETRA: Estado.IDENT, DIGITO: Estado.IDENT},
    Estado.INT: {DIGITO: Estado.INT},
    Estado.MENOR: {"=": Estado.MENOR_IGUAL},
    Estado.MAIOR: {"=": Estado.MAIOR_IGUAL},
    Estado.IGUAL: {"=": Estado.IGUAL_IGUAL},
    Estado.EXCLAMACAO: {"=": Estado.EXCLAMACAO_IGUAL},
    Estado.E_COMERCIAL: {"&": Estado.E_LOGICO},
    Estado.BARRA_VERTICAL: {"|": Estado.OU_LOGICO},
}
```

Lendo essa tabela como "de → por → para":

- A partir de `INICIO`, cada primeiro caractere possível de um token leva a
  um estado próprio.
- `IDENT` "absorve" tanto letras quanto dígitos (identificador pode ter
  dígito depois da primeira letra: `x2` é válido). `INT` absorve **só**
  dígitos — é essa assimetria (não simetria!) que faz `1abc` virar dois
  tokens: a caminhada entra em `INT` no `1`, tenta consumir o `a`, não
  encontra transição de `INT` por `LETRA`, e trava.
- As últimas 6 linhas são os "segundos caracteres" dos operadores de dois
  símbolos: só a partir de `MENOR` existe transição por `=` (para
  `MENOR_IGUAL`); só a partir de `E_COMERCIAL` existe transição por outro
  `&` (para `E_LOGICO`); etc. Qualquer estado que não aparece como chave
  externa (por exemplo `MAIS`, `ABRE_PARENTESE`) é final — não sai
  transição nenhuma dali, o que faz sentido, já que `+` e `(` são sempre
  tokens de um caractere só.

```python
ESTADOS_ACEITADORES: frozenset[Estado] = frozenset({
    Estado.IDENT, Estado.INT,
    Estado.MAIS, Estado.MENOS, Estado.ASTERISCO, Estado.BARRA, Estado.PORCENTO,
    Estado.MENOR, Estado.MENOR_IGUAL, Estado.MAIOR, Estado.MAIOR_IGUAL,
    Estado.IGUAL, Estado.IGUAL_IGUAL, Estado.EXCLAMACAO, Estado.EXCLAMACAO_IGUAL,
    Estado.E_LOGICO, Estado.OU_LOGICO,
    Estado.ABRE_PARENTESE, Estado.FECHA_PARENTESE, Estado.ABRE_CHAVE, Estado.FECHA_CHAVE,
    Estado.VIRGULA, Estado.PONTO_VIRGULA,
})
```

Esta é a peça mais importante para entender a regra "`&`/`|` isolado é
erro" (§3.4 do enunciado). Repare no que **falta** aqui: `INICIO`,
`E_COMERCIAL` e `BARRA_VERTICAL`.

- `INICIO` de fora: faz sentido — chegar ao estado inicial sem consumir nada
  não é um token.
- `E_COMERCIAL` (depois de um único `&`) e `BARRA_VERTICAL` (depois de um
  único `|`) de fora: **é aqui que a regra "isolado é erro" vira consequência
  do autômato**, sem precisar de nenhum `if` dedicado tipo "se for `&` e o
  próximo não for `&`, erro". Se depois de `&` vier outro `&`, a caminhada
  chega em `E_LOGICO` (que É aceitador) e tudo bem. Se vier qualquer outra
  coisa, a caminhada trava em `E_COMERCIAL` — que nunca foi aceitador — e o
  lexer nunca registrou nenhum estado aceitador visitado. Isso *é*
  exatamente a condição de erro léxico usada mais adiante.

```python
def transicao(estado: Estado, simbolo: str) -> Estado | None:
    return TABELA_TRANSICOES.get(estado, {}).get(simbolo)
```

Só uma função de consulta segura (`.get` em vez de indexação `[]`, que
lançaria `KeyError` para estado/símbolo sem entrada). Devolve `None` quando
não há para onde ir — é o sinal de "a caminhada trava aqui".

---

## 8. `Lexer.py`, bloco a bloco

### 8.1 O contrato público (inalterado)

```python
class TokenKind(enum.Enum):
    EOF = -1
    IDENTIFIER = 1
    ...

@dataclass(frozen=True)
class Token:
    kind: TokenKind
    lexeme: str
    value: int | str | bool | None
    line: int
    column: int

    def __str__(self) -> str:
        return (
            f"<{self.kind.value}, {self.kind.name}, {self.lexeme!r}, "
            f"{self.value!r}, {self.line}, {self.column}>"
        )

class LexerError(Exception):
    def __init__(self, message, line, column):
        super().__init__(message)
        self.message, self.line, self.column = message, line, column

    def __str__(self) -> str:
        return f"erro léxico em {self.line}:{self.column}: {self.message}"
```

Este bloco veio pronto do starter e não pode ser alterado (nomes/números do
`TokenKind`, campos de `Token`). O único ponto sutil é `Token.__str__`: é
onde o formato `<numero, NOME, repr(lexeme), repr(value), linha, coluna>`
exigido pelo enunciado (§6) é montado — `!r` no f-string chama `repr()`
automaticamente.

### 8.2 As tabelas de apoio (implementadas)

```python
PALAVRAS_RESERVADAS: dict[str, TokenKind] = {
    "int": TokenKind.KW_INT, "bool": TokenKind.KW_BOOL, "void": TokenKind.KW_VOID,
    "true": TokenKind.KW_TRUE, "false": TokenKind.KW_FALSE,
    "if": TokenKind.KW_IF, "else": TokenKind.KW_ELSE, "while": TokenKind.KW_WHILE,
    "return": TokenKind.KW_RETURN, "print": TokenKind.KW_PRINT,
}
```

Um dicionário Python comum. A distinção maiúscula/minúscula (`while` é
palavra-chave, `While` não) vem de graça: comparação de string em Python já
é sensível a caixa, sem código extra.

```python
ESTADO_PARA_TIPO: dict[Estado, TokenKind] = {
    Estado.IDENT: TokenKind.IDENTIFIER,
    Estado.INT: TokenKind.INT_LITERAL,
    Estado.MAIS: TokenKind.PLUS,
    ... # um por estado aceitador do autômato
}
```

A "ponte" entre o mundo do autômato (`Estado`) e o contrato público
(`TokenKind`). Mora aqui — e não em `microc_automato.py` — só para evitar
import circular (seção 5).

```python
ESPACOS = " \t\n"
ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
```

`ESPACOS`: exatamente os três caracteres que o enunciado nomeia como
descartáveis (§3.2) — nota que **`\r` não está aqui** (ver seção 12).
`ESCAPES`: os 4 únicos escapes válidos dentro de string (§3.3), mapeando a
letra depois da barra para o caractere real que ela representa.

### 8.3 `Lexer.__init__` e `tokens()` — a orquestração

```python
class Lexer:
    def __init__(self, source: str):
        self.source = source
        self._cursor = Cursor(source)

    def tokens(self) -> Iterator[Token]:
        self._cursor = Cursor(self.source)
        while True:
            self._pular_ignoraveis()
            if self._cursor.fim():
                linha, coluna = self._cursor.posicao()
                yield Token(TokenKind.EOF, "", None, linha, coluna)
                return
            if self._cursor.espiar() == '"':
                yield self._ler_string()
            else:
                yield self._rodar_automato()

    def scan(self) -> list[Token]:
        return list(self.tokens())
```

`tokens()` é um **gerador** (tem `yield`): cada iteração do `while` produz
no máximo um `Token`. O laço, em português:

1. Descarta tudo que for espaço/comentário (`_pular_ignoraveis`).
2. Se acabou o texto, produz o `EOF` **e retorna** — o `return` dentro de um
   gerador encerra a iteração, garantindo que nenhum token venha depois do
   `EOF` em nenhum caminho de execução (requisito do enunciado, §2.1 e
   checklist item 5).
3. Senão, decide entre string (começa com `"`, tratada por rotina manual) e
   "todo o resto" (tratado pelo autômato).

O passo 1 rodar **antes** do teste de fim é o que faz a posição do `EOF`
sair certa sem nenhum cálculo dedicado: depois de descartar tudo que for
descartável, o cursor já está exatamente na posição pós-último-caractere —
seja ela `1:1` (entrada vazia), linha seguinte coluna 1 (entrada terminada
em `\n`), ou qualquer outra.

`self._cursor = Cursor(self.source)` é recriado a cada chamada de
`tokens()` — sem isso, rodar o mesmo `Lexer` duas vezes devolveria uma
sequência vazia na segunda vez (o cursor já estaria no fim).

`scan()` é só um atalho: `list(...)` sobre o gerador, consumindo tudo de
uma vez. Importante: se alguma chamada levantar `LexerError` no meio, o
`list()` propaga a exceção **sem devolver nada** — não existe uma lista
parcial "vazando" para quem chamou. É isso que garante "erros não deixam
tokens parciais" (checklist item 6).

### 8.4 `_rodar_automato` — o núcleo de maior prefixo

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
            break
        proximo = transicao(estado, classificar(caractere))
        if proximo is None:
            break
        estado = proximo
        adiante += 1
        if estado in ESTADOS_ACEITADORES:
            ultimo_aceitador = estado
            tamanho_aceito = adiante

    if ultimo_aceitador is None:
        raise LexerError(self._descrever_caractere_invalido(), linha, coluna)

    lexema = "".join(self._cursor.avancar() for _ in range(tamanho_aceito))
    return self._montar_token(ultimo_aceitador, lexema, linha, coluna)
```

Este é o algoritmo de "maior prefixo" (seção 4) escrito em código. Ele nunca
chama `avancar()` dentro do laço de decisão — só `espiar(adiante)`, cada vez
olhando um caractere mais à frente. A cada passo que **chega num estado
aceitador**, ele atualiza `ultimo_aceitador` e `tamanho_aceito` — mesmo que
a caminhada continue depois. No final, ele consome (`avancar()`) exatamente
`tamanho_aceito` caracteres, nem mais nem menos.

**Trace completo de `"<="`:**

| passo | `adiante` antes | caractere espiado | estado atual | próximo estado | é aceitador? | `ultimo_aceitador` | `tamanho_aceito` |
|---|---|---|---|---|---|---|---|
| 1 | 0 | `'<'` | `INICIO` | `MENOR` | sim | `MENOR` | 1 |
| 2 | 1 | `'='` | `MENOR` | `MENOR_IGUAL` | sim | `MENOR_IGUAL` | 2 |
| 3 | 2 | `''` (fim) | `MENOR_IGUAL` | — (break) | — | `MENOR_IGUAL` | 2 |

Resultado: consome 2 caracteres, produz `LESS_EQUAL`. Note o passo 2
**sobrescrevendo** o que o passo 1 tinha guardado — é exatamente aí que
`<=` vence `<` sem nenhum `if` especial. O mesmo mecanismo cobre `>=`,
`==`, `!=`, `&&`, `||`.

**Trace de `"1abc"`** (mostra por que vira dois tokens):

| passo | caractere | estado atual | próximo | aceitador? |
|---|---|---|---|---|
| 1 | `'1'` (DIGITO) | `INICIO` | `INT` | sim → `tamanho_aceito=1` |
| 2 | `'a'` (LETRA) | `INT` | **sem transição** → break | — |

A primeira chamada de `_rodar_automato` consome só `"1"` (`INT_LITERAL`). O
cursor fica parado bem antes do `a`. Na **próxima** iteração do laço em
`tokens()`, uma nova chamada de `_rodar_automato` começa do zero a partir do
`a`, e dessa vez `IDENT` aceita letras e dígitos igualmente, consumindo
`"abc"` inteiro como `IDENTIFIER`.

**Trace de `"&"` sozinho** (mostra o erro):

| passo | caractere | estado atual | próximo | aceitador? |
|---|---|---|---|---|
| 1 | `'&'` | `INICIO` | `E_COMERCIAL` | **não** (fora de `ESTADOS_ACEITADORES`) |
| 2 | `''` (fim) | `E_COMERCIAL` | — (break) | — |

`ultimo_aceitador` nunca foi definido (continua `None`), então o `if
ultimo_aceitador is None` no fim dispara `LexerError` usando `linha, coluna`
capturados **no início** da função — ou seja, a posição do próprio `&`.

```python
def _descrever_caractere_invalido(self) -> str:
    caractere = self._cursor.espiar()
    if not caractere.isascii():
        return f"caractere não ASCII {caractere!r} (o fonte MicroC é ASCII)"
    if caractere == "&":
        return "'&' isolado; o operador lógico do MicroC é '&&'"
    if caractere == "|":
        return "'|' isolado; o operador lógico do MicroC é '||'"
    return f"caractere inesperado {caractere!r}"
```

Só escolhe a mensagem de erro mais específica possível para o caractere que
travou logo na primeira posição — não afeta a posição do erro (essa já foi
capturada antes), só o texto de `message`.

### 8.5 `_montar_token` — de estado final para `Token`

```python
def _montar_token(self, estado: Estado, lexema: str, linha: int, coluna: int) -> Token:
    tipo = ESTADO_PARA_TIPO[estado]

    if tipo is TokenKind.IDENTIFIER:
        tipo = PALAVRAS_RESERVADAS.get(lexema, TokenKind.IDENTIFIER)

    valor: int | str | bool | None
    if tipo is TokenKind.IDENTIFIER:
        valor = lexema
    elif tipo is TokenKind.INT_LITERAL:
        valor = int(lexema)
    elif tipo is TokenKind.KW_TRUE:
        valor = True
    elif tipo is TokenKind.KW_FALSE:
        valor = False
    else:
        valor = None

    return Token(tipo, lexema, valor, linha, coluna)
```

Dois passos:

1. Traduz o `Estado` final para `TokenKind` via `ESTADO_PARA_TIPO`. Se o
   resultado bruto for `IDENTIFIER`, consulta `PALAVRAS_RESERVADAS` — e
   **só agora**, depois que o identificador inteiro já foi consumido pelo
   autômato. É isso que garante que `intx`, `true1`, `_int` não sejam
   confundidos com `int`/`true` por prefixo: o maior prefixo *é* o
   identificador completo, e é só ele que entra na busca.
2. Calcula o `value` conforme a categoria final (regra da §2.2 do
   enunciado). `int(lexema)` converte `"0042"` para `42` — o Python já lida
   com zero à esquerda em base 10 sem precisar de tratamento manual; os
   zeros continuam existindo no `lexema`, só não no `value`.

### 8.6 Espaços e comentários

```python
def _pular_ignoraveis(self) -> None:
    while not self._cursor.fim():
        caractere = self._cursor.espiar()
        if caractere in ESPACOS:
            self._cursor.avancar()
        elif caractere == "/" and self._cursor.espiar(1) == "/":
            self._pular_comentario_de_linha()
        elif caractere == "/" and self._cursor.espiar(1) == "*":
            self._pular_comentario_de_bloco()
        else:
            return
```

Um laço só, porque as três coisas (espaço, `//`, `/* */`) podem se alternar
livremente numa mesma entrada (ex.: `" \t// x\n/* y */ z"`). Ele nunca
produz `Token` — só avança o cursor — e devolve o controle assim que
encontra o começo de um token de verdade.

```python
def _pular_comentario_de_linha(self) -> None:
    self._cursor.avancar()  # primeira '/'
    self._cursor.avancar()  # segunda '/'
    while not self._cursor.fim() and self._cursor.espiar() != "\n":
        self._exigir_ascii()
        self._cursor.avancar()
```

Consome `//` e depois tudo até (mas **sem** consumir) o `\n`, ou até o fim
do arquivo. Deixar o `\n` para a próxima volta do laço externo
(`_pular_ignoraveis`) centraliza a lógica "consumir `\n` avança linha" num
único lugar (dentro de `Cursor.avancar`), em vez de duplicá-la aqui.

```python
def _pular_comentario_de_bloco(self) -> None:
    linha, coluna = self._cursor.posicao()  # antes de consumir qualquer coisa
    self._cursor.avancar()  # '/'
    self._cursor.avancar()  # '*'
    while True:
        if self._cursor.fim():
            raise LexerError("comentário de bloco não terminado", linha, coluna)
        if self._cursor.espiar() == "*" and self._cursor.espiar(1) == "/":
            self._cursor.avancar()
            self._cursor.avancar()
            return
        self._exigir_ascii()
        self._cursor.avancar()
```

A posição `linha, coluna` é capturada **antes** de consumir o `/` inicial —
por isso, se o bloco nunca fechar, o erro aponta para o delimitador de
abertura (exigência do enunciado, §4), não para onde o `fim()` foi
*detectado* (que seria sempre o final do arquivo, perdendo a informação de
onde o comentário começou). Não há contagem de aninhamento — a busca para
no primeiro `*/` que aparecer, como pede §3.2 ("comentários de bloco não
são aninhados").

```python
def _exigir_ascii(self) -> None:
    caractere = self._cursor.espiar()
    if not caractere.isascii():
        linha, coluna = self._cursor.posicao()
        raise LexerError(f"caractere não ASCII {caractere!r} ...", linha, coluna)
```

Chamada tanto dentro dos comentários quanto dentro de strings. É necessária
porque, uma vez que o texto de um comentário ou string é "conteúdo bruto"
(nunca passa pelo autômato, que é quem normalmente barra não-ASCII via
`classificar`), alguém precisa continuar aplicando a regra "não-ASCII é
erro mesmo dentro de comentário/string" (§3.2 e §3.4) manualmente.

### 8.7 `_ler_string`

```python
def _ler_string(self) -> Token:
    linha, coluna = self._cursor.posicao()  # a aspa de abertura
    partes_lexema = [self._cursor.avancar()]  # consome a aspa
    partes_valor: list[str] = []

    while True:
        if self._cursor.fim():
            raise LexerError("string não terminada", linha, coluna)
        caractere = self._cursor.espiar()

        if caractere == "\n":
            quebra_linha, quebra_coluna = self._cursor.posicao()
            raise LexerError("quebra de linha dentro de string", quebra_linha, quebra_coluna)

        self._exigir_ascii()

        if caractere == '"':
            partes_lexema.append(self._cursor.avancar())
            break

        if caractere == "\\":
            barra_linha, barra_coluna = self._cursor.posicao()
            partes_lexema.append(self._cursor.avancar())  # a barra
            if self._cursor.fim():
                raise LexerError("string não terminada", linha, coluna)
            grafia = self._cursor.espiar()
            if grafia not in ESCAPES:
                raise LexerError(f"sequência de escape inválida '\\{grafia}'", barra_linha, barra_coluna)
            partes_lexema.append(self._cursor.avancar())
            partes_valor.append(ESCAPES[grafia])
            continue

        partes_lexema.append(self._cursor.avancar())
        partes_valor.append(caractere)

    return Token(TokenKind.STRING_LITERAL, "".join(partes_lexema), "".join(partes_valor), linha, coluna)
```

Duas listas crescem em paralelo: `partes_lexema` (grafia original, com
aspas e barras) e `partes_valor` (conteúdo decodificado, sem aspas). Elas
não têm o mesmo tamanho no final — um escape como `\n` acrescenta **dois**
caracteres ao lexema (`\` e `n`) mas só **um** ao valor (a quebra de linha
real).

**Trace de `"\"a\\n\""` (fonte literal: aspas, `a`, barra invertida, `n`, aspas):**

| passo | caractere visto | ação | `partes_lexema` | `partes_valor` |
|---|---|---|---|---|
| 0 | — | consome `"` de abertura | `['"']` | `[]` |
| 1 | `a` | conteúdo comum | `['"', 'a']` | `['a']` |
| 2 | `\` | início de escape; espia `n` a seguir, está em `ESCAPES` | `['"', 'a', '\\']` | `['a']` |
| 2b | (mesmo passo) | consome o `n`, traduz via `ESCAPES["n"]` | `['"', 'a', '\\', 'n']` | `['a', '\n']` |
| 3 | `"` | fecha a string | `[..., '"']` | `['a', '\n']` |

Resultado: `lexeme = '"a\\n"'` (a barra invertida **literal**, preservada) e
`value = "a\n"` (uma quebra de linha **real**, um único caractere) — exatamente
a distinção que o enunciado pede em §2.2/§3.3.

As três posições de erro exigidas pelo enunciado (§4) mapeiam direto para
três `raise` diferentes nesta função:

- `if self._cursor.fim()` (duas ocorrências) → usa `linha, coluna`
  capturados **na abertura da string**, guardados desde o topo da função;
- `if caractere == "\n"` → usa a posição **da própria quebra**, capturada
  no momento em que ela é vista (ainda não consumida);
- `if grafia not in ESCAPES` → usa `barra_linha, barra_coluna`, capturados
  **antes** de consumir a barra invertida, independente de qual caractere
  vier depois dela.

Por fim: marcadores de comentário (`//`, `/*`) dentro da string nunca são
tratados como comentário, porque `_ler_string` lê caractere a caractere sem
nunca chamar `_pular_ignoraveis` — ela só sai desse laço ao encontrar a
aspa de fechamento, quebra de linha, ou EOF.

---

## 9. Exemplo ponta a ponta: `int x = 42;`

Juntando tudo, para o fonte `int x = 42;`:

| chamada em `tokens()` | o que acontece | token produzido |
|---|---|---|
| 1 | `_pular_ignoraveis` não acha nada para pular; `_rodar_automato` caminha `i→n→t` por `IDENT`, trava no espaço; consulta `PALAVRAS_RESERVADAS["int"]` | `<10, KW_INT, 'int', None, 1, 1>` |
| 2 | pula o espaço; `_rodar_automato` caminha `x` por `IDENT`, trava no espaço; `"x"` não é palavra reservada | `<1, IDENTIFIER, 'x', 'x', 1, 5>` |
| 3 | pula o espaço; `_rodar_automato` vê `=`, tenta continuar mas o próximo é espaço (não `=`), então só `IGUAL` é aceito | `<34, ASSIGN, '=', None, 1, 7>` |
| 4 | pula o espaço; `_rodar_automato` caminha `4→2` por `INT`, trava no `;` | `<2, INT_LITERAL, '42', 42, 1, 9>` |
| 5 | `_rodar_automato` vê `;`, único caractere de `PONTO_VIRGULA` | `<45, SEMICOLON, ';', None, 1, 11>` |
| 6 | `_pular_ignoraveis` não acha nada (fim do texto); `_cursor.fim()` é verdadeiro | `<-1, EOF, '', None, 2, 1>` |

Este é literalmente o exemplo que o próprio enunciado usa na seção 6 — e a
saída bate caractere por caractere (confirmado rodando `python runner.py`
sobre esse texto).

---

## 10. Como rodar e testar

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q            # os 24 testes públicos em tests/test.py
python runner.py test.microc   # imprime a lista de tokens do exemplo dado
```

No Windows, se o teste que compara a mensagem acentuada `erro léxico`
falhar por causa de codificação (processo filho em UTF-8, terminal em
cp1252), rode com `$env:PYTHONUTF8 = "1"` antes — não é um bug no lexer,
é descasamento de encoding entre processos (detalhado em
[`IMPLEMENTACAO.md`](IMPLEMENTACAO.md)).

---

## 11. Conformidade com o enunciado

Checagem feita lendo o `ENUNCIADO.pdf` inteiro e testando manualmente (além
da suíte pública) os casos mais específicos de cada seção:

| Exigência | Status |
|---|---|
| Enum `TokenKind` com nomes/números exatos | ✅ |
| `Token` imutável com os 5 campos corretos | ✅ |
| Posições 1-based, EOF na posição pós-último caractere | ✅ |
| Maior prefixo (`<=`, `>=`, `==`, `!=`, `&&`, `\|\|` vencem prefixo) | ✅ |
| `0b101` → `INT_LITERAL(0)` + `IDENTIFIER(b101)` | ✅ |
| Sinal fora do literal (`-10` → `MINUS`+`INT_LITERAL`) | ✅ |
| Distinção maiúsculas/minúsculas em palavras reservadas | ✅ |
| Espaços/comentários descartados, sem token próprio | ✅ |
| Comentário de bloco não aninha; EOF dentro é erro | ✅ |
| Strings: lexema com escapes, valor decodificado, 2 tokens para strings adjacentes | ✅ |
| Não-ASCII e `&`/`\|` isolados são erro léxico | ✅ |
| Posições de erro exatas (abertura de string/bloco, quebra de linha, barra invertida) | ✅ |
| `runner.py`: sem tokens parciais em erro, stderr + exit 1/2 | ✅ |
| Nenhum gerador de lexer nem regex global usado | ✅ (nenhum `import re` no projeto) |
| Formato de saída `<numero, NOME, repr(lexeme), repr(value), linha, coluna>` | ✅ |
| Interface (`from Lexer import ...`), `runner.py`, `tests/test.py` intocados | ✅ |
| 24/24 testes públicos passando | ✅ |

Nenhuma falha encontrada. Dois pontos ficam fora do que dá para verificar só
lendo o repositório (não são problemas, só dependências externas):

- confirmar que a versão de Python do Classroom bate com a fixada no CI
  (`3.12`, em `.github/workflows/classroom.yml`);
- os testes ocultos da correção podem exercitar interpretações de zona
  cinzenta do enunciado (ver seção 12) de um jeito diferente do que foi
  assumido aqui.

---

## 12. Decisões que valem atenção

- **`\r` avulso é erro léxico**, não é tratado como espaço em branco. O
  enunciado nunca menciona `\r` diretamente; diz só que o `runner.py` "lê
  arquivos em modo texto, normalizando as terminações de linha usuais"
  (§2.3), e que "caractere que não inicia token" é erro (§3.4). A leitura
  adotada foi: se o `runner` já normaliza antes do lexer ver o texto, um
  `\r` que sobra é porque alguém chamou o `Lexer` diretamente com uma
  string "crua" contendo `\r\n` — e nesse caso ele deve falhar, não ser
  tolerado silenciosamente. É uma interpretação **documentada e
  defensável**, mas é uma interpretação; vale conferir se bate com os
  testes ocultos.
- `ENUNCIADO.pdf` está versionado no repositório. Não atrapalha nada
  tecnicamente, mas não é estritamente "necessário" pelo checklist do
  enunciado (item 8) — é só o PDF do próprio enunciado, então é inofensivo.
- Nenhum módulo do projeto usa a biblioteca `re` (expressões regulares) em
  lugar nenhum — o enunciado só proíbe usá-la para *todo* o reconhecimento,
  mas aqui ela nem aparece para tarefas auxiliares. Mais conservador do que
  o mínimo exigido.
