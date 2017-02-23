//
// Numbers
//

DIGIT: "0".."9"

INT: DIGIT+
DECIMAL: INT ("." INT)?

// float = /-?\d+(\.\d+)?([eE][+-]?\d+)?/
FLOAT: "-"? DECIMAL (("e"|"E")("+"|"-")? INT)?


//
// Strings
//
ESCAPED_STRING: /".*?(?<!\\)"/


//
// Names (Variables)
//
LCASE_LETTER: "a".."z"
UCASE_LETTER: "A".."Z"

LETTER: UCASE_LETTER | LCASE_LETTER

CNAME: ("_"|LETTER) ("_"|LETTER|DIGIT)*


//
// Whitespace
//
WS_INLINE: (" "|/\t/)+
WS: /[ \t\f\r\n]/+

