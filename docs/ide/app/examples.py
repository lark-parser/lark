
# Examples formattet this way:
#   "name": ("grammar", "demo-input")

examples = {

	# --- hello.lark ---
	"hello.lark": ("""
start: WORD "," WORD "!"

%import common.WORD   // imports from terminal library
%ignore " "           // Disregard spaces in text
""", "Hello, World!"),

	# --- calc.lark ---
"calc.lark": ("""
?start: sum
      | NAME "=" sum    -> assign_var

?sum: product
    | sum "+" product   -> add
    | sum "-" product   -> sub

?product: atom
    | product "*" atom  -> mul
    | product "/" atom  -> div

?atom: NUMBER           -> number
     | "-" atom         -> neg
     | NAME             -> var
     | "(" sum ")"

%import common.CNAME -> NAME
%import common.NUMBER
%import common.WS_INLINE
%ignore WS_INLINE""",
	"1 + 2 * 3 + 4"),

	# --- json.lark ---
	"json.lark": ("""
?start: value
?value: object
      | array
      | string
      | SIGNED_NUMBER      -> number
      | "true"             -> true
      | "false"            -> false
      | "null"             -> null
array  : "[" [value ("," value)*] "]"
object : "{" [pair ("," pair)*] "}"
pair   : string ":" value
string : ESCAPED_STRING
%import common.ESCAPED_STRING
%import common.SIGNED_NUMBER
%import common.WS
%ignore WS""",
"""
[
  {
    "_id": "5edb875cf3d764da55602437",
    "index": 0,
    "guid": "3dae2206-5d4d-41fe-b81d-dc8cdba7acaa",
    "isActive": false,
    "balance": "$2,872.54",
    "picture": "http://placehold.it/32x32",
    "age": 24,
    "eyeColor": "blue",
    "name": "Theresa Vargas",
    "gender": "female",
    "company": "GEEKOL",
    "email": "theresavargas@geekol.com",
    "phone": "+1 (930) 450-3445",
    "address": "418 Herbert Street, Sexton, Florida, 1375",
    "about": "Id minim deserunt laborum enim. Veniam commodo incididunt amet aute esse duis veniam occaecat nulla esse aute et deserunt eiusmod. Anim elit ullamco minim magna sint laboris. Est consequat quis deserunt excepteur in magna pariatur laborum quis eu. Ex quis tempor elit qui qui et culpa sunt sit esse mollit cupidatat. Fugiat cillum deserunt enim minim irure reprehenderit est. Voluptate nisi quis amet quis incididunt pariatur nostrud Lorem consectetur adipisicing voluptate.\\r\\n",
    "registered": "2016-11-19T01:02:42 -01:00",
    "latitude": -25.65267,
    "longitude": 104.19531,
    "tags": [
      "eiusmod",
      "reprehenderit",
      "anim",
      "sunt",
      "esse",
      "proident",
      "esse"
    ],
    "friends": [
      {
        "id": 0,
        "name": "Roth Herrera"
      },
      {
        "id": 1,
        "name": "Callie Christian"
      },
      {
        "id": 2,
        "name": "Gracie Whitfield"
      }
    ],
    "greeting": "Hello, Theresa Vargas! You have 6 unread messages.",
    "favoriteFruit": "banana"
  },
  {
    "_id": "5edb875c845eb08161a83e64",
    "index": 1,
    "guid": "a8ada2c1-e2c7-40d3-96b4-52c93baff7f0",
    "isActive": false,
    "balance": "$2,717.04",
    "picture": "http://placehold.it/32x32",
    "age": 23,
    "eyeColor": "green",
    "name": "Lily Ross",
    "gender": "female",
    "company": "RODEOMAD",
    "email": "lilyross@rodeomad.com",
    "phone": "+1 (941) 465-3561",
    "address": "525 Beekman Place, Blodgett, Marshall Islands, 3173",
    "about": "Aliquip duis proident excepteur eiusmod in quis officia consequat culpa eu et ut. Occaecat reprehenderit tempor mollit do eu magna qui et magna exercitation aliqua. Incididunt exercitation dolor proident eiusmod minim occaecat. Sunt et minim mollit et veniam sint ex. Duis ullamco elit aute eu excepteur reprehenderit officia.\\r\\n",
    "registered": "2019-11-02T04:06:42 -01:00",
    "latitude": 17.031701,
    "longitude": -42.657106,
    "tags": [
      "id",
      "non",
      "culpa",
      "reprehenderit",
      "esse",
      "elit",
      "sit"
    ],
    "friends": [
      {
        "id": 0,
        "name": "Ursula Maldonado"
      },
      {
        "id": 1,
        "name": "Traci Huff"
      },
      {
        "id": 2,
        "name": "Taylor Holt"
      }
    ],
    "greeting": "Hello, Lily Ross! You have 3 unread messages.",
    "favoriteFruit": "strawberry"
  }
]""")
}