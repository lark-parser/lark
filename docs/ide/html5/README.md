# ViUR html5

**html5** is a DOM-abstraction layer and API that is used to create client-side Web-Apps running in the browser and written in Python.

Look [here](https://www.viur.dev/blog/html5-library) for a short introduction.

## About

This API and framework is used to implement HTML5 web-apps using the Python programming language. The framework is an abstraction layer for a DOM running in [Pyodide](https://github.com/iodide-project/pyodide), a Python 3 interpreter compiled to web-assembly.

It provides

- class abstraction for all HTML5-DOM-elements, e.g. `html5.Div()`
- a built-in HTML parser and executor to generate DOM objects from HTML-code
- helpers for adding/removing classes, arrange children, handling events etc.

The most prominent software completely established on this library is [ViUR-vi](https://github.com/viur-framework/viur-vi/), the visual administration interface for ViUR-based applications.

[ViUR](https://www.viur.dev) is a free software development framework for the [Google App Engine](https://appengine.google.com).

## Quick Start

**Warning: This section is incomplete, a working example will follow soon!**

```python
import html5

class Game(html5.Div):
	def __init__(self):
		super().__init__(
        """
            <label>
                Your Name:
                <input [name]="myInput" type="text" placeholder="Name">
            </label>
            
            <h1>Hello <span [name]="mySpan" class="name">Enter Name</span>!</h1>
        """)
		self.sinkEvent("onChange")

	def onChange(self, event):
		if html5.utils.doesEventHitWidgetOrChildren(event, self.myInput):
			self.mySpan.appendChild(self.myInput["value"], replace=True)

Game()
```

## Contributing

We take a great interest in your opinion about ViUR. We appreciate your feedback and are looking forward to hear about your ideas. Share your visions or questions with us and participate in ongoing discussions.

- [ViUR website](https://www.viur.dev)
- [#ViUR on freenode IRC](https://webchat.freenode.net/?channels=viur)
- [ViUR on GitHub](https://github.com/viur-framework)
- [ViUR on Twitter](https://twitter.com/weloveViUR)

## Credits

ViUR is developed and maintained by [Mausbrand Informationssysteme GmbH](https://www.mausbrand.de/en), from Dortmund in Germany. We are a software company consisting of young, enthusiastic software developers, designers and social media experts, working on exciting projects for different kinds of customers. All of our newer projects are implemented with ViUR, from tiny web-pages to huge company intranets with hundreds of users.

Help of any kind to extend and improve or enhance this project in any kind or way is always appreciated.

## License

Copyright (C) 2012-2020 by Mausbrand Informationssysteme GmbH.

Mausbrand and ViUR are registered trademarks of Mausbrand Informationssysteme GmbH.

You may use, modify and distribute this software under the terms and conditions of the GNU Lesser General Public License (LGPL). See the file LICENSE provided within this package for more information.
