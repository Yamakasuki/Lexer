# Como o lexer foi implementado

Guia de leitura do código da Etapa 1. O *porquê* de cada decisão de design está
em [`superpowers/specs/2026-08-20-lexer-microc-design.md`](superpowers/specs/2026-08-20-lexer-microc-design.md);
aqui o foco é *onde* cada coisa mora e *como* as peças se encaixam.

## Estratégia: mista

O enunciado (seção 5) aceita implementação manual, dirigida por tabela ou mista.
Usamos **mista**, e a linha divisória segue uma diferença real entre as categorias:

| Categoria | Reconhecida por | Por quê |
|---|---|---|
| Identificadores, inteiros, operadores, delimitadores | **Autômato por tabela** | São linguagens regulares simples que competem entre si pelo maior prefixo no mesmo ponto do texto. |
| Strings e comentários | **Rotinas manuais** | Cada um exige uma posição de erro que não é a posição corrente do autômato. |

A segunda linha é a justificativa inteira da divisão. O enunciado exige:

| Situação | Onde reportar o erro |
|---|---|
| `"abc` — EOF antes de fechar | na **aspa de abertura** |
| `"abc⏎` — quebra de linha | na **própria quebra** |
| `"\q"` — escape inválido | na **barra invertida** |
| `/* sem fim` | no **`/` inicial** |

Um autômato sabe apenas em que estado está *agora*. Para reportar "a aspa de
abertura" ele teria de carregar essa posição por dentro da tabela e desfazê-la na
saída. Uma variável local numa rotina manual resolve em linha reta.

## Os três arquivos

```
microc_cursor.py     Cursor — anda pelo texto, conta linha e coluna.
                     Depende de: nada.

microc_automato.py   Estado, classificar(), TABELA_TRANSICOES,
                     ESTADOS_ACEITADORES, transicao().
                     Depende de: nada.

Lexer.py             Contrato público (TokenKind, Token, LexerError — como
                     vieram no starter) + PALAVRAS_RESERVADAS +
                     ESTADO_PARA_TIPO + class Lexer.
                     Depende de: os dois acima.
```

`from Lexer import Lexer, LexerError, Token, TokenKind` continua funcionando,
que é a condição do enunciado para usar módulos auxiliares.

**Por que `microc_automato.py` não conhece `TokenKind`:** se ele importasse o
enum de `Lexer.py`, e `Lexer.py` importasse o autômato, teríamos import
circular. Mantendo o autômato falando só a língua dele — estados, símbolos,
transições — o ciclo some, e o módulo fica legível e testável sozinho. A
tradução `Estado → TokenKind` mora em `Lexer.py`, onde `TokenKind` já vive.

## Fluxo

```
Lexer.tokens()
   │
   ├─► _pular_ignoraveis()          espaços, // e /* */  (descartados)
   │
   ├─► fim do texto?  ──sim──►  Token(EOF, "", None, linha, coluna)
   │
   ├─► próximo é '"'? ──sim──►  _ler_string()            [manual]
   │
   └─────────────────────────►  _rodar_automato()        [tabela]
```

`_pular_ignoraveis()` roda **antes** do teste de fim. É isso que faz a posição do
EOF sair correta sem código dedicado: entrada vazia termina em 1:1, entrada
terminada em `\n` termina na linha seguinte coluna 1, e `/* ok */` termina em
1:9.

## O maior prefixo, sem retroceder o cursor

O algoritmo clássico consome caracteres e **retrocede** quando trava.
Retroceder exigiria desfazer a contagem de linha e coluna — a única parte
realmente delicada do `Cursor`.

Fazemos o inverso: `_rodar_automato()` olha adiante com `espiar(n)` **sem
consumir**, memorizando o último estado aceitador visitado e a que distância ele
ficou. Só no fim consome exatamente `tamanho_aceito` caracteres. O `Cursor`, por
isso, não tem `voltar()` — e não precisa ter.

Três exigências do enunciado viram consequência do algoritmo, não casos
especiais:

- **`<=` vence `<`.** A caminhada vai mais longe e sobrescreve o tamanho aceito.
  Idem `>=`, `==`, `!=`, `&&`, `||`.
- **`1abc` são dois tokens.** `INT` aceita o `1`; o `a` não tem transição saindo
  de `INT`; consumimos só o `1`. O mesmo vale para `0xff` → `INT_LITERAL(0)` +
  `IDENTIFIER("xff")`.
- **`&` isolado é erro na coluna certa.** `E_COMERCIAL` está fora de
  `ESTADOS_ACEITADORES` de propósito, então a caminhada termina sem aceitador
  algum e o erro usa a posição capturada antes de começar.

## Palavras reservadas

A tabela é consultada **depois** de o autômato consumir o identificador inteiro.
É isso que faz `intx`, `true1` e `_int` serem `IDENTIFIER`: o maior prefixo é o
identificador completo, e só ele é procurado. Como a busca é num `dict` comum,
`While` não casa com `while` — a sensibilidade a maiúsculas vem da comparação de
strings do Python, sem código extra.

## Caracteres não ASCII

Tratados em dois lugares, por caminhos diferentes:

- **No autômato:** `classificar()` testa `isascii()` antes de chamar `isalpha()`.
  Sem esse teste, `"é".isalpha()` é `True` em Python e `é` viraria identificador.
  Com ele, `é` não tem transição e o erro cai naturalmente.
- **Em comentários e strings:** `_exigir_ascii()`, porque o enunciado é explícito
  que "caracteres não ASCII continuam inválidos mesmo quando aparecem dentro de
  comentários".

## Sobre `\r`

Não recebe tratamento especial, e isso é deliberado. O enunciado nunca menciona
`\r`; diz apenas que o runner "lê arquivos em modo texto, normalizando as
terminações de linha usuais" (seção 2.3) — ou seja, `\r\n` já virou `\n` antes de
o lexer ver qualquer coisa. Como a seção 3.2 lista os descartáveis como "espaços,
tabulações e quebras de linha", e a seção 3.4 declara que "caractere que não
inicia token" é erro léxico, um `\r` avulso é erro. Não implementamos tolerância
que a especificação não pede.

## Como rodar

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q          # 24 testes públicos
python runner.py test.microc # imprime os tokens
```

### Nota para quem roda no Windows

O teste `test_runner_nao_imprime_prefixo_quando_ha_erro` compara a mensagem
`erro léxico em 1:8`, que tem acento. Em alguns consoles Windows o processo
filho escreve o stderr em UTF-8 enquanto o processo pai o decodifica com o
*locale* (`cp1252`), e o `é` chega como `Ã©` — o teste falha sem que haja nada
errado no lexer. Alinhe as duas pontas:

```powershell
$env:PYTHONUTF8 = "1"
python -m pytest -q
```

No CI (Ubuntu, locale UTF-8) as duas pontas já concordam e o problema não
aparece.
