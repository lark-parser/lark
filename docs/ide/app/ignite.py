# -*- coding: utf-8 -*-
from . import core as html5


@html5.tag
class Label(html5.Label):
	_parserTagName = "ignite-label"

	def __init__(self, *args, **kwargs):
		super(Label, self).__init__(style="label ignt-label", *args, **kwargs)


@html5.tag
class Input(html5.Input):
	_parserTagName = "ignite-input"

	def __init__(self, *args, **kwargs):
		super(Input, self).__init__(style="input ignt-input", *args, **kwargs)


@html5.tag
class Switch(html5.Div):
	_parserTagName = "ignite-switch"

	def __init__(self, *args, **kwargs):
		super(Switch, self).__init__(style="switch ignt-switch", *args, **kwargs)

		self.input = html5.Input(style="switch-input")
		self.appendChild(self.input)
		self.input["type"] = "checkbox"

		switchLabel = html5.Label(forElem=self.input)
		switchLabel.addClass("switch-label")
		self.appendChild(switchLabel)

	def _setChecked(self, value):
		self.input["checked"] = bool(value)

	def _getChecked(self):
		return self.input["checked"]


@html5.tag
class Check(html5.Input):
	_parserTagName = "ignite-check"

	def __init__(self, *args, **kwargs):
		super(Check, self).__init__(style="check ignt-check", *args, **kwargs)

		checkInput = html5.Input()
		checkInput.addClass("check-input")
		checkInput["type"] = "checkbox"
		self.appendChild(checkInput)

		checkLabel = html5.Label(forElem=checkInput)
		checkLabel.addClass("check-label")
		self.appendChild(checkLabel)


@html5.tag
class Radio(html5.Div):
	_parserTagName = "ignite-radio"

	def __init__(self, *args, **kwargs):
		super(Radio, self).__init__(style="radio ignt-radio", *args, **kwargs)

		radioInput = html5.Input()
		radioInput.addClass("radio-input")
		radioInput["type"] = "radio"
		self.appendChild(radioInput)

		radioLabel = html5.Label(forElem=radioInput)
		radioLabel.addClass("radio-label")
		self.appendChild(radioLabel)


@html5.tag
class Select(html5.Select):
	_parserTagName = "ignite-select"

	def __init__(self, *args, **kwargs):
		super(Select, self).__init__(style="select ignt-select", *args, **kwargs)

		defaultOpt = html5.Option()
		defaultOpt["selected"] = True
		defaultOpt["disabled"] = True
		defaultOpt.element.innerHTML = ""
		self.appendChild(defaultOpt)


@html5.tag
class Textarea(html5.Textarea):
	_parserTagName = "ignite-textarea"

	def __init__(self, *args, **kwargs):
		super(Textarea, self).__init__(style="textarea ignt-textarea", *args, **kwargs)


@html5.tag
class Progress(html5.Progress):
	_parserTagName = "ignite-progress"

	def __init__(self, *args, **kwargs):
		super(Progress, self).__init__(style="progress ignt-progress", *args, **kwargs)


@html5.tag
class Item(html5.Div):
	_parserTagName = "ignite-item"

	def __init__(self, title=None, descr=None, className=None, *args, **kwargs):
		super(Item, self).__init__(style="item ignt-item", *args, **kwargs)
		if className:
			self.addClass(className)

		self.fromHTML("""
			<div class="item-image ignt-item-image" [name]="itemImage">
			</div>
			<div class="item-content ignt-item-content" [name]="itemContent">
				<div class="item-headline ignt-item-headline" [name]="itemHeadline">
				</div>
			</div>
		""")

		if title:
			self.itemHeadline.appendChild(html5.TextNode(title))

		if descr:
			self.itemSubline = html5.Div()
			self.addClass("item-subline ignt-item-subline")
			self.itemSubline.appendChild(html5.TextNode(descr))
			self.appendChild(self.itemSubline)


@html5.tag
class Table(html5.Table):
	_parserTagName = "ignite-table"

	def __init__(self, *args, **kwargs):
		super(Table, self).__init__(*args, **kwargs)
		self.head.addClass("ignt-table-head")
		self.body.addClass("ignt-table-body")

	def prepareRow(self, row):
		assert row >= 0, "Cannot create rows with negative index"

		for child in self.body._children:
			row -= child["rowspan"]
			if row < 0:
				return

		while row >= 0:
			tableRow = html5.Tr()
			tableRow.addClass("ignt-table-body-row")
			self.body.appendChild(tableRow)
			row -= 1

	def prepareCol(self, row, col):
		assert col >= 0, "Cannot create cols with negative index"
		self.prepareRow(row)

		for rowChild in self.body._children:
			row -= rowChild["rowspan"]

			if row < 0:
				for colChild in rowChild._children:
					col -= colChild["colspan"]
					if col < 0:
						return

				while col >= 0:
					tableCell = html5.Td()
					tableCell.addClass("ignt-table-body-cell")
					rowChild.appendChild(tableCell)
					col -= 1

				return
	def fastGrid( self, rows, cols, createHidden=False ):
		colsstr = "".join(['<td class="ignt-table-body-cell"></td>' for i in range(0, cols)])
		tblstr = '<tbody [name]="body" class="ignt-table-body" >'

		for r in range(0, rows):
			tblstr += '<tr class="ignt-table-body-row %s">%s</tr>' %("is-hidden" if createHidden else "",colsstr)
		tblstr +="</tbody>"

		self.fromHTML(tblstr)
