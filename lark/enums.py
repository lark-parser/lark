import enum


@enum.unique
class Parser(enum.Enum):
  earley = enum.auto()
  lalr = enum.auto()
  cyk = enum.auto()


@enum.unique
class Lexer(enum.Enum):
  auto = enum.auto()
  standard = enum.auto()
  contextual = enum.auto()
  dynamic = enum.auto()
  dynamic_complete = enum.auto()

@enum.unique
class Ambiguity(enum.Enum):
  resolve = enum.auto()
  explicit = enum.auto()
  forest = enum.auto()
