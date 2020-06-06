from . import html5, app


def start():
	html5.Body().appendChild(
		app.App()
	)

